from transformers import AutoTokenizer, AutoModelForCausalLM

m = "Qwen/Qwen2.5-0.5B-Instruct"
tok = AutoTokenizer.from_pretrained(m, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(m, trust_remote_code=True).eval()

if tok.pad_token_id is None and tok.eos_token_id is not None:
    tok.pad_token = tok.eos_token  # minimal safety for generation

messages = [{"role": "system", "content": "You are a helpful, factual assistant. Answer concisely."},
{"role": "user", "content": "Who was Buster Keaton? Answer in one sentence."}]
input_ids = tok.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_tensors="pt")

out = model.generate(
    input_ids=input_ids,
    max_new_tokens=148,
    do_sample=True, temperature=0.2, top_p=0.9,
    eos_token_id=tok.eos_token_id,
    pad_token_id=tok.pad_token_id,
)

generated = out[0, input_ids.shape[1]:]  # strip the prompt; keep only the answer
print(tok.decode(generated, skip_special_tokens=True).strip())
