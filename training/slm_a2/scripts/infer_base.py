import argparse, torch
from transformers import AutoTokenizer, AutoModelForCausalLM

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-id", default="Qwen/Qwen2.5-0.5B")  # or local path
    ap.add_argument("--prompt", default="Summarize: RAGstream is a manual-first RAG pipeline with a preprocessor.")
    ap.add_argument("--max-new-tokens", type=int, default=256)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--top-p", type=float, default=0.9)
    ap.add_argument("--do-sample", action="store_true", default=True)
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    tok = AutoTokenizer.from_pretrained(args.model_id, use_fast=True, trust_remote_code=True)
    if tok.pad_token_id is None and tok.eos_token is not None:
        tok.pad_token = tok.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        low_cpu_mem_usage=True,
        torch_dtype=dtype if device == "cuda" else None,
        trust_remote_code=True,
    ).to(device)
    model.eval()

    # Prefer chat template (Instruct models), fallback to plain text (base).
    try:
        if hasattr(tok, "apply_chat_template"):
            inputs = tok.apply_chat_template(
                [{"role": "user", "content": args.prompt}],
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt"
            )
        else:
            inputs = tok(args.prompt, return_tensors="pt")
    except Exception:
        inputs = tok(args.prompt, return_tensors="pt")

    inputs = {k: v.to(device) for k, v in inputs.items()}

    gen_kwargs = {
        "max_new_tokens": args.max_new_tokens,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "do_sample": args.do_sample,
        "eos_token_id": tok.eos_token_id,
        "pad_token_id": tok.pad_token_id,
    }

    with torch.no_grad():
        out = model.generate(**inputs, **gen_kwargs)

    # Show only generated continuation
    prompt_len = inputs["input_ids"].shape[1]
    generated = out[0][prompt_len:]
    text = tok.decode(generated, skip_special_tokens=True)
    print("\n=== RESPONSE ===\n" + text.strip())

if __name__ == "__main__":
    main()
