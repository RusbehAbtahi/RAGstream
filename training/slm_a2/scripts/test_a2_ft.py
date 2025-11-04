#!/usr/bin/env python3
"""
test_a2_ft.py — Smoke-test for your A2 fine-tuned model.

What this script does:
1) Loads OPENAI_API_KEY from the environment (fails fast if missing).
2) Locates your fine-tuned model id (default path below; or pass --model).
3) Builds a single "messages" payload in the same style you trained:
   the user message contains TASK, PURPOSE, and CONTEXT (plain text).
4) Calls Chat Completions with a JSON Schema "response_format" so the
   model MUST return a JSON object with exactly these 5 keys:
     - system, audience, tone, response_depth, confidence
5) Parses and pretty-prints the JSON result, plus basic token usage.

Run examples:
  python3 test_a2_ft.py
  python3 test_a2_ft.py --model ft:gpt-4.1-mini-2025-04-14:personal:a2-promptshaper-v1:CYGp1QTF
  python3 test_a2_ft.py --no-schema   # (debug-only) without schema enforcement
"""

import os       # Standard library: access environment variables (OPENAI_API_KEY)
import json     # Standard library: decode/encode JSON strings
import sys      # Standard library: exit with error codes and print to stderr
import argparse # Standard library: parse command-line flags (e.g., --model)
from pathlib import Path  # Standard library: robust filesystem paths

# ---- Third-party SDK: OpenAI client -----------------------------------------
# The "openai" package exposes the high-level Python client and API entrypoints.
# Class: OpenAI — a lightweight client; you instantiate it and then call
#          .chat.completions.create(...) to perform a Chat Completion request.
# Method: chat.completions.create(model=..., messages=[...], ...)
#   - model (str): model name/id. Here we use your fine-tuned model id.
#   - messages (list[dict]): chat turns (role/content). For training parity,
#       we send ONE user turn with "TASK/PURPOSE/CONTEXT" concatenated.
#   - response_format (dict): optional structured outputs (JSON schema) to force
#       the model to emit valid JSON for {system,audience,tone,response_depth,confidence}.
try:
    from openai import OpenAI
except Exception as e:
    sys.stderr.write(
        "ERROR: OpenAI SDK not installed. Install with:\n"
        "  pip install --upgrade openai\n"
    )
    sys.exit(1)

# ---- Defaults (adjust paths if you relocate things) --------------------------
ROOT = Path("/home/rusbeh_ab/project/RAGstream")
MODEL_ID_FILE = ROOT / "training/slm_a2/data/processed/finetuned_model_id.txt"

# A minimal probe that matches your training style: the user message contains
# TASK/PURPOSE/CONTEXT in plain text. Feel free to change these values when testing.
DEFAULT_TASK = "JUST AUDIT THE FORMAT of PROMPT"
DEFAULT_PURPOSE = "sanity check"
DEFAULT_CONTEXT = "AFS"

# ---- JSON Schema to ENFORCE the 5 fields (Structured Outputs) ----------------
# This schema tells the API to only accept outputs that match the below object
# (no extra keys; all five required as strings).
A2_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "system":         {"type": "string"},
        "audience":       {"type": "string"},
        "tone":           {"type": "string"},
        "response_depth": {"type": "string"},
        "confidence":     {"type": "string"},
    },
    "required": ["system", "audience", "tone", "response_depth", "confidence"],
}

def load_model_id(cli_model: str | None) -> str:
    """
    Returns the fine-tuned model id to use.
    Priority:
      1) --model CLI flag if provided
      2) finetuned_model_id.txt (default path)
    """
    if cli_model:
        return cli_model.strip()
    if not MODEL_ID_FILE.exists():
        sys.stderr.write(f"ERROR: Model id file not found: {MODEL_ID_FILE}\n"
                         f"Pass --model ft:... explicitly.\n")
        sys.exit(2)
    model = MODEL_ID_FILE.read_text(encoding="utf-8").strip()
    if not model:
        sys.stderr.write(f"ERROR: Model id file is empty: {MODEL_ID_FILE}\n")
        sys.exit(2)
    return model

def build_messages(task: str, purpose: str, context: str) -> list[dict]:
    """
    Constructs the single user message in your training style:
    We put TASK/PURPOSE/CONTEXT into one 'user' turn (plain text).
    Returns a list of messages suitable for Chat Completions.
    """
    content = f"TASK: {task}\nPURPOSE: {purpose}\nCONTEXT: {context}"
    return [{"role": "user", "content": content}]

def call_model(client: OpenAI, model_id: str, messages: list[dict], use_schema: bool) -> dict:
    """
    Calls chat.completions.create and returns:
      {
        "raw": <full response dict-like>,
        "labels": <parsed JSON object with 5 keys (if schema on) or best-effort parse>,
        "usage": <usage dict or None>
      }

    - If 'use_schema' is True, we pass response_format with A2_JSON_SCHEMA,
      so the model MUST return valid JSON for the five fields.
    - If 'use_schema' is False, we still try to json.loads(...) the content;
      if it isn't valid JSON, we return the raw string.
    """
    # Payload for Chat Completions:
    payload = {
        "model": model_id,
        "messages": messages,
    }

    if use_schema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "A2Labels",
                "schema": A2_JSON_SCHEMA
            }
        }

    resp = client.chat.completions.create(**payload)  # API call
    # The top-level object is a "ChatCompletion" with fields:
    #  - choices: list of completions (normally length 1 here)
    #  - usage: token usage (prompt/completion/total) when available
    #  - id, created, model, etc.

    choice = resp.choices[0]
    # choice.message is the assistant's content turn:
    #   .role (always "assistant" here)
    #   .content (str) — for structured outputs, this is a JSON string
    content = choice.message.content

    labels = None
    if use_schema:
        # With schema enforcement, content SHOULD be valid JSON.
        try:
            labels = json.loads(content)
        except Exception:
            # Extremely rare with schema, but we guard anyway.
            labels = {"_parse_error": "Response was not valid JSON", "raw": content}
    else:
        # No schema: try to parse JSON anyway, else return raw string.
        try:
            labels = json.loads(content)
        except Exception:
            labels = {"_raw_text": content}

    # "usage" is often included for billing insight (tokens consumed).
    usage = getattr(resp, "usage", None)
    # Convert pydantic-like object to plain dict when present.
    if usage:
        try:
            usage = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
        except Exception:
            # If the SDK structure differs, fall back to repr.
            usage = repr(usage)

    return {"raw": resp, "labels": labels, "usage": usage}

def main():
    parser = argparse.ArgumentParser(description="Test your A2 fine-tuned model.")
    parser.add_argument("--model", default=None, help="Fine-tuned model id (overrides file).")
    parser.add_argument("--task", default=DEFAULT_TASK, help="TASK text.")
    parser.add_argument("--purpose", default=DEFAULT_PURPOSE, help="PURPOSE text.")
    parser.add_argument("--context", default=DEFAULT_CONTEXT, help="CONTEXT text.")
    parser.add_argument("--no-schema", action="store_true",
                        help="Disable JSON schema enforcement (debug only).")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not api_key.startswith("sk-"):
        sys.stderr.write(
            "ERROR: OPENAI_API_KEY is missing/invalid.\n"
            "Export it in your shell (and ~/.bashrc) before running:\n"
            "  export OPENAI_API_KEY='sk-...'\n"
        )
        sys.exit(3)

    model_id = load_model_id(args.model)
    print(f"[info] Using model: {model_id}")
    print(f"[info] Schema enforcement: {'OFF' if args.no_schema else 'ON'}")

    # Instantiate the OpenAI client:
    #   - The constructor reads API credentials from the environment by default,
    #     but we pass api_key explicitly for clarity.
    client = OpenAI(api_key=api_key)

    # Prepare the single user message with TASK/PURPOSE/CONTEXT:
    messages = build_messages(task=args.task, purpose=args.purpose, context=args.context)

    # Call the fine-tuned model:
    result = call_model(
        client=client,
        model_id=model_id,
        messages=messages,
        use_schema=(not args.no_schema)
    )

    # Pretty-print the structured labels and basic usage:
    print("\n=== Parsed Labels ===")
    print(json.dumps(result["labels"], ensure_ascii=False, indent=2))

    print("\n=== Token Usage (if available) ===")
    print(json.dumps(result["usage"], ensure_ascii=False, indent=2))

    # Optional: basic sanity checks for empty fields
    if isinstance(result["labels"], dict):
        missing = [k for k in ("system","audience","tone","response_depth","confidence")
                   if k not in result["labels"]]
        if missing:
            print(f"\n[warn] Missing keys in output: {missing}")

if __name__ == "__main__":
    main()
