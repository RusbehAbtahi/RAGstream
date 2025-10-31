# -*- coding: utf-8 -*-
"""
clean_and_window_384.py

Goal
----
Build training-ready (prompt, target) pairs with a strict TOTAL token budget of 384
for the Qwen tokenizer. Labels (target JSON) are NEVER truncated. When the input
(TASK/CONTEXT) is too long, we SPLIT ONLY THE INPUT into overlapping windows so the
model eventually sees the entire text across multiple samples.

What "384 tokens" means here
----------------------------
"384" is the total sequence length the model sees at once:
  TOTAL = len(prompt_tokens) + len(target_tokens) + (EOS if present)
We reserve exact space for the labels first, then use the remaining budget for the
prompt. If labels alone would exceed 384 (very rare), we fall back to "single-key"
targets (system-only, audience-only, ...) to keep supervision intact.

Outputs
-------
Writes windowed splits to:
  training/slm_a2/data/processed_win384/{train,val,test}.jsonl

Each JSONL row:
{
  "id": "a2_000123_w03_tgtALL",         # base id + window index + target-slice tag
  "prompt": "<INSTRUCTION + windowed TASK/CONTEXT>",
  "target": "{\"system\": \"...\", ...}",  # STRICT JSON (compact)
  "meta": {
     "prompt_tokens": 318,
     "target_tokens": 64,
     "total_tokens": 383,
     "window_index": 3,
     "windows_total": 8
  }
}

Keep it simple: no decorators, plain helpers, readable flow.
"""

import json
import math
import random
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Tuple

from transformers import AutoTokenizer


# ----------------------------- simple config ---------------------------------

MODEL_ID = "Qwen/Qwen2.5-0.5B"
TOKEN_LIMIT = 384           # hard cap for (prompt + target + EOS)
WINDOW_OVERLAP = 0.50       # 50% overlap between input windows
SEED = 42
PROJECT_ROOT = Path("/home/rusbeh_ab/project/RAGstream").resolve()

RAW_PATH = PROJECT_ROOT / "training" / "slm_a2" / "data" / "raw" / "A2_dataset_list.json"
OUT_DIR = PROJECT_ROOT / "training" / "slm_a2" / "data" / "processed_win384"

# Instruction text is constant for every example; INPUT windows change
INSTRUCTION = (
    "### Instruction\n"
    "You are A2 pass-1. Read the text below and output a STRICT JSON object\n"
    "with any of these keys if present: system, audience, purpose, tone, confidence, response_depth.\n"
    "Do not add extra keys. Do not add explanations."
)

# Simple, explicit key map
KEY_MAP: Dict[str, str] = {
    "SYSTEM": "system",
    "AUDIENCE": "audience",
    "PURPOSE": "purpose",
    "TONE": "tone",
    "CONFIDENCE": "confidence",
    "RESPONSE DEPTH": "response_depth",
    "RESPONSE_DEPTH": "response_depth",
    "TASK": "task",
    "CONTEXT": "context",
}


# ----------------------------- tiny helpers ----------------------------------

def canon_key(k: str) -> str:
    if not k:
        return ""
    u = k.strip().upper().replace("_", " ")
    return KEY_MAP.get(u, k.strip().lower())


def norm_text(s: Any) -> str:
    if s is None:
        return ""
    return str(s).replace("\r\n", "\n").strip()


def record_fingerprint(input_obj: Dict[str, str], labels: Dict[str, str]) -> str:
    """Stable hash to drop exact duplicates BEFORE windowing."""
    parts = [
        "TASK:", input_obj.get("task", ""),
        "CONTEXT:", input_obj.get("context", ""),
        "LABELS:",
        labels.get("system", ""),
        labels.get("audience", ""),
        labels.get("purpose", ""),
        labels.get("tone", ""),
        labels.get("confidence", ""),
        labels.get("response_depth", ""),
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def read_raw(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Raw dataset must be a JSON list of dicts.")
    return data


def canonize_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in raw.items():
        out[canon_key(k)] = norm_text(v)
    return out


def build_input_labels(canon: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, str]]:
    task = norm_text(canon.get("task", ""))
    context = norm_text(canon.get("context", ""))
    input_obj = {"task": task, "context": context}
    labels: Dict[str, str] = {}
    for k in ("system", "audience", "purpose", "tone", "confidence", "response_depth"):
        v = norm_text(canon.get(k, ""))
        if v:
            labels[k] = v
    return input_obj, labels


def make_prompt_text(task: str, context: str) -> str:
    """Build the full prompt string from instruction + TASK/CONTEXT."""
    parts = [INSTRUCTION]
    if task:
        parts.append("\n### TASK")
        parts.append(task)
    if context:
        parts.append("\n### CONTEXT")
        parts.append(context)
    return "\n".join(parts).strip()


def make_target_json(labels: Dict[str, str], keys: List[str] = None) -> str:
    """Turn labels into compact JSON. If keys is provided, include only those."""
    if keys is None:
        keys = sorted(labels.keys())
    payload = {k: labels[k] for k in keys if k in labels}
    return json.dumps(payload, ensure_ascii=False)


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ----------------------------- windowing core --------------------------------
def window_inputs_with_fixed_labels(
    tok,
    full_prompt_text: str,
    instr_text: str,
    label_json: str,
    max_len: int,
    overlap: float,
) -> List[Tuple[str, str, Dict[str, int]]]:
    """
    Return a list of (prompt_text_window, label_json, meta) tuples.

    Rules:
    - NEVER cut the label_json.
    - ONLY split the INPUT portion (TASK/CONTEXT); INSTRUCTION is constant.
    - If labels alone would exceed max_len, return [] so caller can fall back.
    """
    eos_id = tok.eos_token_id
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token  # safe default

    # Tokenize fixed parts
    instr_ids = tok(instr_text, add_special_tokens=False)["input_ids"]
    full_ids = tok(full_prompt_text, add_special_tokens=False)["input_ids"]
    content_ids = full_ids[len(instr_ids):]  # tokens after INSTRUCTION

    # Label tail (must always fit)
    target_ids = tok(label_json, add_special_tokens=False)["input_ids"]
    target_tail = target_ids + ([eos_id] if eos_id is not None else [])

    if len(target_tail) >= max_len:
        return []

    # Budget for prompt = max_len - labels
    prompt_budget = max_len - len(target_tail)
    instr_len_tokens = len(instr_ids)
    content_window_size = max(0, prompt_budget - instr_len_tokens)

    # Build windows safely (no index errors)
    if content_window_size <= 0:
        windows = [[]]  # instruction-only window
    elif len(content_ids) <= content_window_size:
        windows = [content_ids]
    else:
        W = content_window_size
        S = max(1, int(round(W * (1.0 - overlap))))  # e.g., 50% overlap → stride ≈ W/2
        limit = max(0, len(content_ids) - W + 1)
        windows = [content_ids[i:i+W] for i in range(0, limit, S)]
        # ensure tail window is included
        tail = content_ids[-W:] if (W > 0 and content_ids) else []
        if tail and (not windows or windows[-1] != tail):
            windows.append(tail)
        if not windows:
            windows = [[]]

    out: List[Tuple[str, str, Dict[str, int]]] = []
    total_windows = len(windows)

    for idx, win in enumerate(windows, 1):
        prompt_ids = instr_ids + win
        total_tokens = len(prompt_ids) + len(target_tail)

        # Final safety: if we somehow exceed max_len, clip the window head
        if total_tokens > max_len:
            overflow = total_tokens - max_len
            if overflow > 0 and len(win) >= overflow:
                prompt_ids = instr_ids + win[:-overflow]
                total_tokens = len(prompt_ids) + len(target_tail)
            if total_tokens > max_len:
                # still too long -> skip this window
                continue

        prompt_text = tok.decode(prompt_ids, skip_special_tokens=True)
        meta = {
            "prompt_tokens": len(prompt_ids),
            "target_tokens": len(target_tail),
            "total_tokens": total_tokens,
            "window_index": idx,
            "windows_total": total_windows,
        }
        out.append((prompt_text, label_json, meta))

    # If nothing made it, at least return instruction + labels
    if not out:
        prompt_text = tok.decode(instr_ids, skip_special_tokens=True)
        out = [(prompt_text, label_json, {
            "prompt_tokens": len(instr_ids),
            "target_tokens": len(target_tail),
            "total_tokens": len(instr_ids) + len(target_tail),
            "window_index": 1,
            "windows_total": 1,
        })]

    return out


# ----------------------------- main build ------------------------------------

def main() -> None:
    random.Random(SEED).seed(SEED)

    tok = AutoTokenizer.from_pretrained(MODEL_ID, use_fast=True)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token  # safe default

    raw = read_raw(RAW_PATH)

    # 1) Canonicalize + dedupe BEFORE windowing
    uniq_items: List[Dict[str, Any]] = []
    seen = set()
    for row in raw:
        if not isinstance(row, dict):
            continue
        canon = canonize_row(row)
        input_obj, labels = build_input_labels(canon)

        # require at least TASK or CONTEXT
        if not input_obj["task"] and not input_obj["context"]:
            continue
        # require at least one label (we don't train on empty targets)
        if not labels:
            continue

        fp = record_fingerprint(input_obj, labels)
        if fp in seen:
            continue
        seen.add(fp)

        uniq_items.append({"input": input_obj, "labels": labels})

    # 2) Shuffle and split (80/10/10)
    random.shuffle(uniq_items)
    n = len(uniq_items)
    n_train = int(0.8 * n)
    n_val = int(0.1 * n)
    train_rows = uniq_items[:n_train]
    val_rows = uniq_items[n_train:n_train + n_val]
    test_rows = uniq_items[n_train + n_val:]

    # 3) For each split, build windowed prompt/target pairs under 384 tokens
    def build_split(rows: List[Dict[str, Any]], split_name: str) -> List[Dict[str, Any]]:
        out_rows: List[Dict[str, Any]] = []
        skipped_too_long_labels = 0
        exploded_from_label_fallback = 0
        next_id = 1

        for rec in rows:
            task = rec["input"]["task"]
            context = rec["input"]["context"]
            labels = rec["labels"]

            # Full prompt text (instruction + sections). We'll window only the content.
            full_prompt_text = make_prompt_text(task, context)

            # First try with ALL labels together
            tgt_all = make_target_json(labels)  # sorted keys
            windows = window_inputs_with_fixed_labels(
                tok, full_prompt_text, INSTRUCTION, tgt_all, TOKEN_LIMIT, WINDOW_OVERLAP
            )

            label_variant = "tgtALL"
            label_keys_used = sorted(labels.keys())

            if not windows:
                # Fallback: split labels across multiple samples (e.g., system-only, then others)
                single_keys = sorted(labels.keys())
                per_key_windows: List[Tuple[str, str, Dict[str, int], str]] = []
                for k in single_keys:
                    tgt_one = make_target_json(labels, keys=[k])
                    w = window_inputs_with_fixed_labels(
                        tok, full_prompt_text, INSTRUCTION, tgt_one, TOKEN_LIMIT, WINDOW_OVERLAP
                    )
                    if not w:
                        # Even one label didn't fit -> skip this example (extremely rare)
                        skipped_too_long_labels += 1
                        per_key_windows = []
                        break
                    # attach which key we used, for id tag
                    for item in w:
                        per_key_windows.append((item[0], item[1], item[2], f"tgt{k.upper()}"))

                if not per_key_windows:
                    continue  # nothing could fit

                windows = [ (p, t, m) for (p, t, m, _tag) in per_key_windows ]
                label_variant = "tgtSPLIT"
                label_keys_used = single_keys
                exploded_from_label_fallback += 1

            # Emit rows (one per window)
            total_windows = len(windows)
            for w_idx, (ptext, tjson, meta) in enumerate(windows, start=1):
                row_id = f"{split_name}_{next_id:06d}_w{w_idx:02d}_{label_variant}"
                out_rows.append({
                    "id": row_id,
                    "prompt": ptext,
                    "target": tjson,
                    "meta": meta
                })
            next_id += 1

        # small summary for this split
        print(f"[{split_name}] items_in={len(rows)}  windows_out={len(out_rows)}"
              f"  label_fallbacks={exploded_from_label_fallback}"
              f"  skipped_too_long_labels={skipped_too_long_labels}")
        return out_rows

    train_out = build_split(train_rows, "train")
    val_out   = build_split(val_rows,   "val")
    test_out  = build_split(test_rows,  "test")

    # 4) Write JSONL
    out_train = OUT_DIR / "train.jsonl"
    out_val   = OUT_DIR / "val.jsonl"
    out_test  = OUT_DIR / "test.jsonl"
    write_jsonl(out_train, train_out)
    write_jsonl(out_val,   val_out)
    write_jsonl(out_test,  test_out)

    # 5) Final summary
    print("----------------------------------------------------------------")
    print(f"Total unique base items: {n}  (train {len(train_rows)}, val {len(val_rows)}, test {len(test_rows)})")
    print(f"Wrote: {out_train}")
    print(f"Wrote: {out_val}")
    print(f"Wrote: {out_test}")
    print("Each row respects the 384-token cap with labels preserved intact.")
    print("Prompt windows cover the full TASK/CONTEXT across overlapping slices.")
    print("Use these files for training instead of the earlier non-windowed split.")
    print("----------------------------------------------------------------")


if __name__ == "__main__":
    main()
