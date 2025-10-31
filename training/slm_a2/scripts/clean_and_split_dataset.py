# -*- coding: utf-8 -*-
"""
clean_and_split_dataset.py

Purpose
-------
Read the raw A2 dataset (list of dicts), normalize keys and text, build simple
(input, labels) records, deduplicate, and write JSONL splits to:
  training/slm_a2/data/processed/{train,val,test}.jsonl

Design
------
- Minimal, readable Python (no frameworks).
- Deterministic behavior (fixed random seed).
- Only light cleaning; no ontology mapping yet.
- TASK or CONTEXT: one is sufficient; both are used if present.
- Labels: we include only the keys that have non-empty strings. Missing labels
  are simply omitted (the training loop can mask them later).

Run
---
python /home/rusbeh_ab/project/RAGstream/training/slm_a2/scripts/clean_and_split_dataset.py
"""

from __future__ import annotations

import json
import random
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Global key map (simple and explicit)
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


class DatasetProcessor:
    """
    End-to-end processor:
      1) Read raw JSON list from data/raw/A2_dataset_list.json
      2) Canonicalize keys and text
      3) Build (input, labels) items
      4) Deduplicate exact duplicates
      5) Split into train/val/test (80/10/10)
      6) Write JSONL files to data/processed/
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.raw_path = project_root / "training" / "slm_a2" / "data" / "raw" / "A2_dataset_list.json"
        self.out_dir = project_root / "training" / "slm_a2" / "data" / "processed"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.random_seed = 42  # deterministic

    # ---------- tiny helpers (instance methods; no decorators) ----------

    def canon_key(self, key: str) -> str:
        """Map raw keys to canonical lowercase names."""
        if not key:
            return ""
        upper = key.strip().upper().replace("_", " ")
        return KEY_MAP.get(upper, key.strip().lower())

    def normalize_text(self, s: Any) -> str:
        """Convert to string, normalize newlines, trim."""
        if s is None:
            return ""
        return str(s).replace("\r\n", "\n").strip()

    def build_input_and_labels(self, rec: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, str]]:
        """
        input  = {task, context}  (one is enough; keep both if present)
        labels = subset of {system, audience, purpose, tone, confidence, response_depth}
        """
        task = self.normalize_text(rec.get("task", ""))
        context = self.normalize_text(rec.get("context", ""))
        input_obj = {"task": task, "context": context}

        labels: Dict[str, str] = {}
        for k in ("system", "audience", "purpose", "tone", "confidence", "response_depth"):
            v = self.normalize_text(rec.get(k, ""))
            if v:
                labels[k] = v
        return input_obj, labels

    def record_fingerprint(self, input_obj: Dict[str, str], labels: Dict[str, str]) -> str:
        """Stable hash to drop exact duplicates after normalization."""
        parts: List[str] = [
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

    # ---------- main steps ----------

    def load_raw(self) -> List[Dict[str, Any]]:
        with self.raw_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("Raw dataset must be a JSON list of dictionaries.")
        return data

    def canon_record(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Map keys and normalize values."""
        out: Dict[str, Any] = {}
        for k, v in raw.items():
            out[self.canon_key(k)] = self.normalize_text(v)
        return out

    def _write_jsonl(self, path: Path, records: List[Dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def process(self) -> None:
        raw_list = self.load_raw()

        seen = set()
        items: List[Dict[str, Any]] = []
        next_id = 1

        for raw in raw_list:
            if not isinstance(raw, dict):
                continue

            canon = self.canon_record(raw)
            input_obj, labels = self.build_input_and_labels(canon)

            # Require at least one of task/context
            if not input_obj["task"] and not input_obj["context"]:
                continue

            fp = self.record_fingerprint(input_obj, labels)
            if fp in seen:
                continue
            seen.add(fp)

            items.append({
                "id": f"a2_{next_id:06d}",
                "input": input_obj,
                "labels": labels,
            })
            next_id += 1

        random.Random(self.random_seed).shuffle(items)
        n = len(items)
        n_train = int(0.8 * n)
        n_val = int(0.1 * n)
        n_test = n - n_train - n_val

        train = items[:n_train]
        val = items[n_train:n_train + n_val]
        test = items[n_train + n_val:]

        self._write_jsonl(self.out_dir / "train.jsonl", train)
        self._write_jsonl(self.out_dir / "val.jsonl", val)
        self._write_jsonl(self.out_dir / "test.jsonl", test)

        print(f"Total items: {n}  |  train: {len(train)}  val: {len(val)}  test: {len(test)}")
        print(f"Wrote: {self.out_dir/'train.jsonl'}")
        print(f"Wrote: {self.out_dir/'val.jsonl'}")
        print(f"Wrote: {self.out_dir/'test.jsonl'}")


def main() -> None:
    project_root = Path("/home/rusbeh_ab/project/RAGstream").resolve()
    DatasetProcessor(project_root).process()


if __name__ == "__main__":
    main()
