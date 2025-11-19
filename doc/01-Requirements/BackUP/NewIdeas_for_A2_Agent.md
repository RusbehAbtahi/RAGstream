# NewIdeas_for_A2_Agent_PromptShaper

## purpose

A2 shapes a user’s prompt into stable meta-headers that the pipeline can trust when the user did not set them explicitly. Target fields: system, audience, tone, confidence, depth. A2 runs twice and uses one single SLM for both passes.

## execution order

1. pass-1 (after preprocessing, before retrieval): decide headers from task, context, purpose, and the user prompt.
2. pass-2 (later in the pipeline): same model, same weights; a conservative refinement step may adjust depth, tone, or confidence. Role/audience change only if there is a clear contradiction. Training currently covers pass-1 only.

## model choice

Single SLM for both passes: Qwen2.5-0.5B-Instruct, fine-tuned with LoRA in PyTorch. One adapter, one set of weights, CPU-friendly.

## output contract

A2 returns a strict JSON object with closed label sets:

* system: fixed ontology (about 100 roles, versioned)
* audience: small, closed list (for example: internal developer, manager, general reader)
* tone: eight MBTI-style writing modes used as operational styles (Ti, Te, Ni, Ne, Si, Se, Fi, Fe)
* confidence: low, medium, high
* depth: Overview, Detailed, Exhaustiv

A calibrated acceptance threshold is applied to the model’s certainty. User preference: accept only ≥0.75 certainty; otherwise fall back to defaults.

## inputs by pass

* pass-1 inputs today: task, context, purpose, and the user prompt.
* pass-2 inputs today: same model and weights; refinement is guided conservatively by deterministic gates. No S_ctx data is used for training at this stage.

## deterministic policy

* defaults exist for every field and are applied whenever certainty < threshold.
* confidence is bounded by simple gates; do not label high when evidence is clearly limited.
* inference uses low temperature for repeatability.

## training data (current reality)

* source: exported real prompts from the last two years (what we actually have).
* each training pair: full user prompt plus the agreed headers (system, audience, tone, confidence, depth).
* tone labels use the eight functions as writing styles with observable cues (concise definitions maintained separately).
* label spaces are closed; out-of-ontology items map to defaults.

## fine-tuning method

* supervised LoRA on Qwen2.5-0.5B-Instruct in PyTorch.
* compact dataset is acceptable because outputs are short and structured; additional pairs can be created via careful paraphrases and then reviewed.
* one adapter serves both passes; inputs differ, weights do not.

## evaluation and calibration

* measure JSON validity, per-field accuracy, fallback rate, and stability under small paraphrases.
* set and periodically review the acceptance threshold (initially 0.75 per user preference).
* log decisions and confusion across roles and tones to keep the ontology clean.

## continual improvement

* periodic updates: add newly approved prompt→headers pairs to a curated dataset; run a short LoRA update to produce a new adapter version.
* replay a small canonical set during each update to prevent drift; promote only if metrics meet gates; otherwise roll back.

## governance

* one SLM only; no model switching between passes.
* closed ontologies and deterministic defaults ensure predictable behavior.
* training currently does not use S_ctx; when such data exists in the future, it may be added with a small, targeted top-up fine-tune.
* all changes to ontologies, thresholds, or adapters are versioned and documented.
