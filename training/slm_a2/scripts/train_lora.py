# -*- coding: utf-8 -*-
"""
train_lora.py

Purpose
-------
Train a tiny LoRA adapter on top of the base Qwen model for A2 pass-1.
We use your processed dataset:
  training/slm_a2/data/processed/{train,val,test}.jsonl

Simple, flat OOP (one trainer class). No decorators. No nested classes.

What this script does (high level)
----------------------------------
1) Loads Qwen tokenizer + model (CPU ok).
2) Reads JSONL rows. Each row has:
      { "id": "...",
        "input":  {"task": "...", "context": "..."},
        "labels": {"system": "...", "tone": "...", ... (subset)}
      }
3) Builds a prompt (what we give to the model) and a target JSON (what the
   model should generate). We compute loss only on the target part.
4) Trains LoRA weights and saves them under:
      training/slm_a2/models_local/<run_name>/
5) Evaluates on the validation set and prints the loss.

Run
---
# Activate your venv first
#   cd ~/project/RAGstream/training/slm_a2
#   source .venv/bin/activate
# Then run:
#   python scripts/train_lora.py
"""

import json
import math
import time
from pathlib import Path
from typing import List, Dict, Any

import torch
from torch.utils.data import Dataset, DataLoader
from torch.optim import AdamW

from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
)

from peft import (
    LoraConfig,
    get_peft_model,
)

# -----------------------------
# User-adjustable config (simple)
# -----------------------------
class TrainConfig:
    def __init__(self) -> None:
        # Paths
        self.project_root = Path("/home/rusbeh_ab/project/RAGstream").resolve()
        self.data_dir = self.project_root / "training" / "slm_a2" / "data" / "processed_win384"
        self.out_root = self.project_root / "training" / "slm_a2" / "models_local"

        # Base model id (already cached by you)
        self.model_id = "Qwen/Qwen2.5-0.5B"

        # Tokenization / sequence
        self.max_length = 384   # truncate long samples; keep simple
        self.pad_to_multiple_of = 8

        # Optimization
        self.epochs = 2
        self.batch_size = 1       # CPU-friendly; increase if you have RAM
        self.grad_accum = 8       # effective batch size = batch_size * grad_accum
        self.lr = 2e-4
        self.weight_decay = 0.0
        self.max_grad_norm = 1.0
        self.seed = 42

        # LoRA (small, safe defaults)
        self.lora_r = 8
        self.lora_alpha = 16
        self.lora_dropout = 0.05
        # Common target modules for Qwen-style architectures
        self.lora_targets = ["q_proj", "v_proj", "o_proj"]

        # Device (CPU or CUDA if available)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Run name
        ts = time.strftime("%Y%m%d_%H%M", time.localtime())
        self.run_name = f"a2_lora_{ts}"


def set_seed(seed: int) -> None:
    """Deterministic-ish setup for repeatability."""
    import random
    import numpy as np
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


# -----------------------------
# Data utilities
# -----------------------------
def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read a JSONL file into a list of dicts."""
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def build_prompt_and_target(item: Dict[str, Any]) -> Dict[str, str]:
    """
    Accepts EITHER:
      win384 schema: {"prompt": "...", "target": "..."}
      old schema:    {"input": {"task","context"}, "labels": {...}}
    Returns {"prompt": str, "target": str}
    """
    # New (windowed) format
    if "prompt" in item and "target" in item:
        return {"prompt": item["prompt"], "target": item["target"]}

    # Old format (fallback)
    in_task = (item.get("input") or {}).get("task", "").strip()
    in_context = (item.get("input") or {}).get("context", "").strip()
    labels_dict = (item.get("labels") or {})

    lines = []
    lines.append("### Instruction")
    lines.append("You are A2 pass-1. Read the text below and output a STRICT JSON object")
    lines.append("with any of these keys if present: system, audience, purpose, tone, confidence, response_depth.")
    lines.append("Do not add extra keys. Do not add explanations.")

    if in_task:
        lines.append("\n### TASK")
        lines.append(in_task)
    if in_context:
        lines.append("\n### CONTEXT")
        lines.append(in_context)

    prompt_text = "\n".join(lines).strip()
    ordered = {k: labels_dict[k] for k in sorted(labels_dict.keys())}
    target_text = json.dumps(ordered, ensure_ascii=False)
    return {"prompt": prompt_text, "target": target_text}


class A2JsonlDataset(Dataset):
    """
    PyTorch Dataset:
      - tokenizes prompt + target into one sequence
      - masks the prompt tokens (loss = -100) so loss applies only to target
    """

    def __init__(self, rows: List[Dict[str, Any]], tokenizer, max_length: int) -> None:
        self.rows = rows
        self.tok = tokenizer
        self.max_length = max_length

        # Qwen tokenizers sometimes have no pad token set; use EOS for padding
        if self.tok.pad_token_id is None:
            self.tok.pad_token = self.tok.eos_token

        # Pre-encode all samples once (small dataset; keeps code simple)
        self.encoded: List[Dict[str, torch.Tensor]] = []
        for ex in self.rows:
            pair = build_prompt_and_target(ex)
            prompt = pair["prompt"]
            target = pair["target"]

            # Tokenize prompt and target separately to know the split point
            prompt_ids = self.tok(prompt, add_special_tokens=False)["input_ids"]
            target_ids = self.tok(target, add_special_tokens=False)["input_ids"]

            # Build full sequence: [BOS] prompt + target [EOS]
            # Using eos at end helps the model terminate cleanly
            full_ids = prompt_ids + target_ids
            eos_id = self.tok.eos_token_id
            if eos_id is not None:
                full_ids.append(eos_id)

            # Truncate if too long (simple, straight)
            full_ids = full_ids[: self.max_length]

            # Labels: copy input_ids, then mask prompt part with -100 so loss
            # is computed only for target+eos. We mask the BOS and prompt.
            labels = full_ids.copy()
            # prompt length covers only prompt_ids (no BOS)
            prompt_len = min(len(prompt_ids), len(full_ids))
            for i in range(prompt_len):
                labels[i] = -100

            self.encoded.append({
                "input_ids": torch.tensor(full_ids, dtype=torch.long),
                "labels": torch.tensor(labels, dtype=torch.long),
                "attention_mask": torch.ones(len(full_ids), dtype=torch.long),
            })

    def __len__(self) -> int:
        return len(self.encoded)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        return self.encoded[idx]


def collate_batch(features: List[Dict[str, torch.Tensor]], pad_id: int, pad_to_multiple_of: int) -> Dict[str, torch.Tensor]:
    """
    Simple collator: right-pad input_ids, labels, attention_mask to the same length.
    """
    max_len = max(len(f["input_ids"]) for f in features)
    # Optional: round up to multiple of N for tensor cores; here it just keeps shapes tidy
    if pad_to_multiple_of and (max_len % pad_to_multiple_of != 0):
        max_len = ((max_len // pad_to_multiple_of) + 1) * pad_to_multiple_of

    input_ids, labels, attn = [], [], []
    for f in features:
        L = len(f["input_ids"])
        pad_n = max_len - L

        ids = torch.cat([f["input_ids"], torch.full((pad_n,), pad_id, dtype=torch.long)])
        lbs = torch.cat([f["labels"], torch.full((pad_n,), -100, dtype=torch.long)])
        am  = torch.cat([f["attention_mask"], torch.zeros(pad_n, dtype=torch.long)])

        input_ids.append(ids)
        labels.append(lbs)
        attn.append(am)

    batch = {
        "input_ids": torch.stack(input_ids, dim=0),
        "labels": torch.stack(labels, dim=0),
        "attention_mask": torch.stack(attn, dim=0),
    }
    return batch


# -----------------------------
# Trainer (flat, readable)
# -----------------------------
class A2LoraTrainer:
    """
    Minimal trainer with:
      - manual train loop (readable)
      - val evaluation for early insight
      - LoRA save at the end
    """

    def __init__(self, cfg: TrainConfig) -> None:
        self.cfg = cfg
        set_seed(cfg.seed)

        # Load tokenizer/model
        self.tok = AutoTokenizer.from_pretrained(cfg.model_id, use_fast=True)
        if self.tok.pad_token_id is None:
            self.tok.pad_token = self.tok.eos_token

        self.base_model = AutoModelForCausalLM.from_pretrained(
            cfg.model_id,
            low_cpu_mem_usage=True,
        )

        # Attach LoRA
        lora = LoraConfig(
            r=cfg.lora_r,
            lora_alpha=cfg.lora_alpha,
            lora_dropout=cfg.lora_dropout,
            target_modules=cfg.lora_targets,
            bias="none",
            task_type="CAUSAL_LM",
        )
        self.model = get_peft_model(self.base_model, lora)
        self.model.config.use_cache = False
        self.model.to(cfg.device)

        # Data
        self.train_rows = read_jsonl(cfg.data_dir / "train.jsonl")
        self.val_rows   = read_jsonl(cfg.data_dir / "val.jsonl")

        self.train_ds = A2JsonlDataset(self.train_rows, self.tok, cfg.max_length)
        self.val_ds   = A2JsonlDataset(self.val_rows,   self.tok, cfg.max_length)

        self.train_loader = DataLoader(
            self.train_ds,
            batch_size=cfg.batch_size,
            shuffle=True,
            collate_fn=lambda feats: collate_batch(
                feats, pad_id=self.tok.pad_token_id, pad_to_multiple_of=cfg.pad_to_multiple_of
            ),
        )
        self.val_loader = DataLoader(
            self.val_ds,
            batch_size=cfg.batch_size,
            shuffle=False,
            collate_fn=lambda feats: collate_batch(
                feats, pad_id=self.tok.pad_token_id, pad_to_multiple_of=cfg.pad_to_multiple_of
            ),
        )

        # Optimizer (only LoRA params are trainable)
        trainable_params = [p for p in self.model.parameters() if p.requires_grad]
        self.optimizer = AdamW(trainable_params, lr=cfg.lr, weight_decay=cfg.weight_decay)

        # Output dir
        self.out_dir = (cfg.out_root / cfg.run_name).resolve()
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def train(self) -> None:
        self.model.train()
        step = 0
        accum = 0
        running_loss = 0.0

        for epoch in range(self.cfg.epochs):
            for batch in self.train_loader:
                batch = {k: v.to(self.cfg.device) for k, v in batch.items()}

                outputs = self.model(
                    input_ids=batch["input_ids"],
                    attention_mask=batch["attention_mask"],
                    labels=batch["labels"],
                )
                loss = outputs.loss / self.cfg.grad_accum
                loss.backward()

                running_loss += loss.item()
                accum += 1

                if accum == self.cfg.grad_accum:
                    torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.cfg.max_grad_norm)
                    self.optimizer.step()
                    self.optimizer.zero_grad(set_to_none=True)
                    step += 1
                    accum = 0

                    if step % 10 == 0:
                        avg_loss = running_loss / 10.0
                        print(f"[epoch {epoch+1}] step {step:05d}  train_loss={avg_loss:.4f}")
                        running_loss = 0.0

            # quick val at epoch end
            val_loss = self.evaluate()
            print(f"[epoch {epoch+1}] val_loss={val_loss:.4f}  (ppl={math.exp(val_loss):.2f})")

        # Save LoRA adapters (small files) + tokenizer (for later inference)
        self.model.save_pretrained(self.out_dir)
        self.tok.save_pretrained(self.out_dir)
        print(f"Saved LoRA adapters to: {self.out_dir}")

    @torch.no_grad()
    def evaluate(self) -> float:
        self.model.eval()
        total_loss = 0.0
        total_count = 0

        for batch in self.val_loader:
            batch = {k: v.to(self.cfg.device) for k, v in batch.items()}
            outputs = self.model(
                input_ids=batch["input_ids"],
                attention_mask=batch["attention_mask"],
                labels=batch["labels"],
            )
            total_loss += outputs.loss.item() * batch["input_ids"].size(0)
            total_count += batch["input_ids"].size(0)

        self.model.train()
        return total_loss / max(1, total_count)


def main() -> None:
    cfg = TrainConfig()
    print("Device:", cfg.device)
    print("Saving to:", (cfg.out_root / cfg.run_name).as_posix())

    trainer = A2LoraTrainer(cfg)
    trainer.train()


if __name__ == "__main__":
    main()
