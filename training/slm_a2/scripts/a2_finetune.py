#!/usr/bin/env python3
"""
A2 fine-tune helper: upload -> fine-tune -> poll -> save model id.

What this script does (high level):
1) Reads OPENAI_API_KEY from env and fails fast if missing.
2) Uploads your processed JSONL files with purpose="fine-tune".
3) Creates a fine-tuning job on GPT-4.1-mini (you can switch to 4.1-nano).
4) Polls the job until it finishes (succeeded/failed/cancelled).
5) Prints and saves the fine-tuned model id to a text file for later use.

Refs:
- Pricing & fine-tuning rates (training/input/output): see OpenAI pricing. 
- Fine-tuning workflow: upload JSONL -> create job -> poll -> use model id.
"""

import os, time, sys, json
from pathlib import Path

# --------- CONFIG: adjust paths/models if needed ---------
ROOT = Path("/home/rusbeh_ab/project/RAGstream")
TRAIN_PATH = ROOT / "training/slm_a2/data/processed/openai_train.jsonl"
VAL_PATH   = ROOT / "training/slm_a2/data/processed/openai_val.jsonl"
OUT_DIR    = ROOT / "training/slm_a2/data/processed"
MODEL_BASE = "gpt-4.1-mini-2025-04-14"   # switch to "gpt-4.1-nano-2025-04-14" if you prefer cheaper/lighter
MODEL_TAG  = "A2-PromptShaper-v1"        # appears as suffix on your FT model
MODEL_ID_FILE = OUT_DIR / "finetuned_model_id.txt"

# --------- SDK init (requires: pip install openai>=1.0.0) ---------
try:
    from openai import OpenAI
except Exception as e:
    sys.exit("OpenAI SDK missing. Install with: pip install --upgrade openai")

api_key = os.getenv("OPENAI_API_KEY")
if not api_key or not api_key.startswith("sk-"):
    sys.exit("ERROR: OPENAI_API_KEY missing or invalid. Export it, then re-run.")

client = OpenAI(api_key=api_key)

def upload_file(path: Path) -> str:
    """
    Uploads a local file to OpenAI with purpose="fine-tune".
    Returns the server-side file_id used when creating the FT job.
    """
    if not path.exists():
        sys.exit(f"ERROR: File not found: {path}")
    with path.open("rb") as f:
        up = client.files.create(file=f, purpose="fine-tune")
    print(f"[upload] {path.name} -> {up.id}")
    return up.id

def create_ft_job(train_file_id: str, val_file_id: str | None) -> str:
    """
    Creates a fine-tuning job against MODEL_BASE.
    Returns the job_id so we can poll status.
    """
    payload = {
        "model": MODEL_BASE,
        "training_file": train_file_id,
        "suffix": MODEL_TAG
    }
    if val_file_id:
        payload["validation_file"] = val_file_id

    job = client.fine_tuning.jobs.create(**payload)
    print(f"[create] job_id={job.id} model={MODEL_BASE}")
    return job.id

def poll_job(job_id: str, sleep_s: int = 10) -> dict:
    """
    Polls the job every sleep_s seconds until it is finished.
    Returns the final job object (dict-like).
    """
    while True:
        job = client.fine_tuning.jobs.retrieve(job_id)
        status = getattr(job, "status", None)
        # Optional: print intermediate metrics/events if available
        print(f"[poll] {job_id} status={status}")
        if status in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(sleep_s)

def extract_ft_model_id(job_obj) -> str | None:
    """
    After success, OpenAI returns the fine-tuned model id (like 'ft:gpt-...').
    We fetch it from the job object. Different SDK versions expose it slightly
    differently; we try the common attributes/paths.
    """
    # Newer SDKs often include job_obj.fine_tuned_model
    ft = getattr(job_obj, "fine_tuned_model", None)
    if ft:
        return ft
    # Sometimes it’s in job_obj.result or job_obj.model; try a few fallbacks
    for key in ("result", "model", "fineTunedModel"):
        if hasattr(job_obj, key):
            val = getattr(job_obj, key)
            if isinstance(val, str) and val.startswith("ft:"):
                return val
            if isinstance(val, dict) and "fine_tuned_model" in val:
                return val["fine_tuned_model"]
    # Last resort: raw dict inspection
    try:
        raw = json.loads(job_obj.json())
        for k in ("fine_tuned_model", "result", "model"):
            v = raw.get(k)
            if isinstance(v, str) and v.startswith("ft:"):
                return v
            if isinstance(v, dict) and "fine_tuned_model" in v:
                return v["fine_tuned_model"]
    except Exception:
        pass
    return None

def main():
    print("[check] Using model:", MODEL_BASE)
    # 1) Upload
    train_id = upload_file(TRAIN_PATH)
    val_id = upload_file(VAL_PATH)

    # 2) Create FT job
    job_id = create_ft_job(train_id, val_id)

    # 3) Poll until finish
    final = poll_job(job_id, sleep_s=15)

    # 4) Extract the new fine-tuned model id
    ft_model_id = extract_ft_model_id(final)
    if not ft_model_id:
        print("[warn] Could not auto-detect fine-tuned model id from final job object.")
        print("       Inspect the job JSON below and copy the model id manually:")
        try:
            print(final.json())
        except Exception:
            print(final)
        sys.exit(2)

    # 5) Persist to file for your app to read later
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_ID_FILE.write_text(ft_model_id, encoding="utf-8")
    print(f"[done] Fine-tuned model: {ft_model_id}")
    print(f"[done] Saved to: {MODEL_ID_FILE}")

if __name__ == "__main__":
    main()
