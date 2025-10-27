# ragstream/app/preprocessing.py
from __future__ import annotations
from typing import Dict

def preprocess_prompt(text: str) -> Dict[str, str]:
    # stub: minimal normalization; replace with your Tasks 1–4 later
    norm = " ".join(text.split())
    return {"task": norm, "preview_text": norm}
