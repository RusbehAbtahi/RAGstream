#!/usr/bin/env python3
import json, argparse, random, sys
from pathlib import Path

DEF_INPUT = Path("/home/rusbeh_ab/project/RAGstream/training/slm_a2/data/raw/A2_dataset_list.json")
DEF_OUTDIR = Path("/home/rusbeh_ab/project/RAGstream/training/slm_a2/data/processed")
VAL_FRACTION = 0.2
RAND_SEED = 42  # reproducible split

# Minimal pass-through: keep your target labels as written.
# We only rename "RESPONSE DEPTH" -> "response_depth" key in the assistant output object.
# Everything else is preserved.

def load_items(p: Path):
    text = p.read_text(encoding="utf-8").lstrip()
    items = []
    if text.startswith("["):
        # JSON array
        try:
            items = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"ERROR: Cannot parse JSON array: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # JSONL (one object per line)
        for ln, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"JSON error at line {ln}: {e}", file=sys.stderr)
    return items

def to_user_content(task, purpose, context):
    # Inputs may be empty; that’s fine.
    def clean(s):
        return "" if s is None else str(s).strip()
    t = clean(task)
    p = clean(purpose)
    c = clean(context)
    # Keep labels explicit so the model learns the structure reliably
    parts = []
    parts.append(f"TASK: {t}")
    parts.append(f"PURPOSE: {p}")
    parts.append(f"CONTEXT: {c}")
    return "\n".join(parts)

def make_assistant_json(rec):
    # Build the target JSON object (not the chat wrapper).
    # Map uppercase keys to lowercase; fix "RESPONSE DEPTH".
    # Leave values as-is (no canonicalization), per your request.
    system   = rec.get("SYSTEM", "")
    audience = rec.get("AUDIENCE", "")
    tone     = rec.get("TONE", "")
    depth    = rec.get("RESPONSE DEPTH", rec.get("RESPONSE_DEPTH", ""))
    conf     = rec.get("CONFIDENCE", "")

    out_obj = {
        "system": system,
        "audience": audience,
        "tone": tone,
        "response_depth": depth,
        "confidence": conf,
    }
    return out_obj

def convert(items):
    examples = []
    for obj in items:
        # Input fields (may be missing)
        task    = obj.get("TASK", "")
        purpose = obj.get("PURPOSE", "")
        context = obj.get("CONTEXT", "")

        user_msg = {
            "role": "user",
            "content": to_user_content(task, purpose, context)
        }
        assistant_obj = make_assistant_json(obj)
        assistant_msg = {
            "role": "assistant",
            # Assistant content must be a STRING; embed JSON via dumps
            "content": json.dumps(assistant_obj, ensure_ascii=False)
        }
        examples.append({"messages": [user_msg, assistant_msg]})
    return examples

def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")

def main():
    ap = argparse.ArgumentParser(description="Convert A2 original JSON to OpenAI SFT JSONL (chat format).")
    ap.add_argument("--input",  type=Path, default=DEF_INPUT, help="Path to A2_dataset_list.json (array or JSONL).")
    ap.add_argument("--outdir", type=Path, default=DEF_OUTDIR,   help="Output directory for processed files.")
    ap.add_argument("--val",    type=float, default=VAL_FRACTION, help="Validation fraction (default 0.2).")
    args = ap.parse_args()

    if not args.input.exists():
        print(f"Input not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    items = load_items(args.input)
    if not items:
        print("No items loaded.", file=sys.stderr)
        sys.exit(1)

    examples = convert(items)

    # Stable split
    random.Random(RAND_SEED).shuffle(examples)
    n = len(examples)
    n_val = max(1, int(round(args.val * n)))
    val = examples[:n_val]
    train = examples[n_val:]

    args.outdir.mkdir(parents=True, exist_ok=True)
    out_train = args.outdir / "openai_train.jsonl"
    out_val   = args.outdir / "openai_val.jsonl"

    write_jsonl(out_train, train)
    write_jsonl(out_val, val)

    print(f"Wrote: {out_train} ({len(train)} lines)")
    print(f"Wrote: {out_val} ({len(val)} lines)")
    # Quick sanity echo of one example
    print("\nExample (first train row):")
    print(json.dumps(train[0], ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
