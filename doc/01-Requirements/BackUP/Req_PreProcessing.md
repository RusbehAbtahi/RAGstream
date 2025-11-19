# PreProcessing — Final Requirements (RAGstream)

> **Goal:** deterministically convert a user’s free-form “prompt spec” into a canonical, auditable `SuperPrompt.body`, enforce MUST attributes with defaults, capture unknowns cleanly, and regenerate a **stage snapshot** (`prompt_ready`) for the GUI. No retrieval or rendering blocks are produced here.

---

## 1) Canonical Attribute Sets

### 1.1 Full attribute set (eligible to live in `body`)

SYSTEM, AUDIENCE, PURPOSE, TONE, CONFIDENCE, RESPONSE DEPTH, TASK, CONTEXT, CONSTRAINTS, OUTPUT FORMAT, REFERENCE MATERIALS, EXAMPLE, CHECKLIST, OUT OF SCOPE, DETERMINISTIC RULES, DETERMINISTIC CODES, KNOWLEDGE GRAPH PINS, RETRIEVED ELEMENTS, ATTACHMENTS.

* **Note:** “RETRIEVED ELEMENTS” and “ATTACHMENTS” are populated by later stages; they do not satisfy CONTEXT here.

### 1.2 MUST attributes (enforced; defaults if missing)

SYSTEM, TASK, CONTEXT, CONSTRAINTS, OUTPUT FORMAT, AUDIENCE, PURPOSE, TONE.

---

## 2) Inputs & Outputs

### Input

* Raw user prompt text (may be one block or multi-section).
* Active prompt-schema JSON (see §3).
* Optional user decision cache (confirmations of past mappings).

### Output (mutations on `sp`)

* `sp.body` updated with canonical keys → strings or `None` (never delete keys).
* `sp.extras` updated with:

  * `normalized_map`: list of `{original_key, normalized_key, method}`.
  * `unknown_attributes`: list of `{key, text}` not mapped.
  * `auto_filled`: list of MUST keys filled from defaults.
  * `decisions`: user approvals/overrides captured this run.
  * `config_hash` and any `config_warning`.
* Stage bookkeeping: `sp.history_of_stages += ["preprocessed"]`, `sp.stage = "preprocessed"`.
* `sp.prompt_ready` **regenerated** as the GUI snapshot for this stage (see §8).

---

## 3) Single JSON Config (source of truth)

**File (example):** `config/prompt_schema.json`

**Sections:**

* `version`: string.
* `canonical_keys`: array of lowercase canonical keys (the full set in §1.1).
* `must_keys`: array (subset of `canonical_keys`).
* `defaults`: object `{ key: default_text }` for MUSTs (and any others you want defaults for).
* `aliases`: object `{ "llm role": "system", "goal": "purpose", ... }`.
* `bilingual`: object of language maps (e.g., `{"de":{"aufgabe":"task","zweck":"purpose","zielgruppe":"audience"}}`).
* `templates`: paraphrase cues per key (e.g., `{"task":["user request","user prompt","wishes","thing to be done"]}`).
* `keyword_cues`: `{ "system":["role","persona"], "output format":["format","json","markdown"], ... }`.
* `typo_max_distance`: small integer (e.g., `2`) for tiny-typo tolerance.
* `modes`: `{ "strict_mode": true|false }`.
* `tone_presets`: mapping of tone names → plain-English behaviors (consumed later by A2; just stored here).

**Validation on load:**

* Ensure every `must_key` ∈ `canonical_keys`.
* If the file is missing/invalid, load baked-in safe defaults, set `config_warning`, and continue.

---

## 4) Deterministic Mapping Ladder (apply in order; stop on first hit)

0. **Normalize** header text

* Unicode normalize (NFKC), lowercase, trim, collapse whitespace, strip punctuation, transliterate accents (e.g., ä→ae).

1. **Exact match**

* If normalized header equals a canonical key → map.

2. **Alias table**

* Deterministic synonyms (e.g., “llm role”→system, “goal”→purpose).

3. **Tiny-typo tolerance**

* Edit distance ≤ `typo_max_distance` to any canonical key (e.g., “taks”→task).

4. **Bilingual dictionary**

* Curated language map (e.g., de→en: “aufgabe”→task, “zweck”→purpose).

5. **Tiny-typo + bilingual combo**

* Fix small typos, then apply bilingual map (e.g., “auofgabe”→“aufgabe”→task).

6. **Phrase templates**

* Map common paraphrases when that canonical key is otherwise absent (e.g., “user prompt”, “wishes” → task).

7. **Keyword cues**

* If header contains strong cue words from config, map accordingly.

8. **Else: unknown**

* Nothing matched → treat as unknown (see §5).

For every mapping, append to `sp.extras["normalized_map"]` with the method used.

---

## 5) Unknowns & User Gating (creativity without chaos)

* Collect all unmapped items into `sp.extras["unknown_attributes"] = [{key, text}]`.
* By default, **do not** include unknowns in `body` or in `prompt_ready`.
* In the GUI, present a 3-option gate:

  1. **Cancel** to fix now.
  2. **Proceed without unknowns**.
  3. **Proceed and include unknowns** as a final **CUSTOM ATTRIBUTES** block in `prompt_ready` (verbatim).

     * Unknowns never satisfy MUSTs.
* **Strict mode:** if `modes.strict_mode=true`, block the next stage until the user chooses (1) or (3).

---

## 6) MUST Enforcement

* After mapping, check `must_keys`. For any missing:

  * Set `sp.body[key] = defaults[key]` (or `""` if no default provided).
  * Append the key to `sp.extras["auto_filled"]`.
* Unknowns never count toward MUST completeness.

---

## 7) Duplicates, Conflicts, Order

* If a canonical key appears multiple times:

  * Choose a fixed policy and keep it: **last-wins** (recommended for simplicity), or **merge with a blank line**.
  * Record the policy once in `sp.extras["policy"]`.
* Preserve original header order (if spans are available) in `sp.extras["source_spans"]` for auditability.

---

## 8) `prompt_ready` at the PreProcessing Stage (GUI snapshot)

* The controller **regenerates** `sp.prompt_ready` from the canonical `sp.body` on every run of this stage:

  * Include all **MUST** keys (with user text or defaults).
  * Include any **optional** keys that are non-empty.
  * Exclude retrieval elements and attachments (not available yet).
  * Exclude unknowns by default; include them only if the user chose option (3) in §5 under **CUSTOM ATTRIBUTES**.
* This is a **live snapshot** for the GUI, not the final, fully composed prompt (later stages will add S_CTX and attachments).

---

## 9) Optional Semantic Fallback (LLM/ML), gated & auditable

* **Use only if enabled in config** and the ladder in §4 fails.
* Ask a small/cheap model (or local embedding check) for a **single** best canonical suggestion.
* Auto-map only above a high confidence threshold; otherwise present the suggestion for user confirmation.
* Log `{original_key, suggested_key, method:"semantic", confidence}` and cache approved decisions for future runs.
* If semantic fallback is used, set a flag (e.g., `sp.extras["semantic_used"]=true`).

---

## 10) Idempotency & Determinism

* Same input + same config ⇒ byte-identical `sp.body`, `normalized_map`, `unknown_attributes`, and `prompt_ready`.
* No randomness; fixed thresholds and tie-breaks.
* No network calls unless semantic fallback is explicitly enabled.

---

## 11) Performance & Limits

* Linear in number of headers; tiny edit-distance checks bounded by `|canonical_keys|`.
* For very long prompts, scan only header lines; keep body text verbatim under each key.
* Cap the number of unknowns captured; if truncated, add a note to `sp.extras`.

---

## 12) Errors & Warnings

* Missing/invalid config → load baked-in defaults, set `config_warning`, continue.
* Empty input → fill MUSTs from defaults; warn that no user headers were found.
* Conflicting candidates → tie-break priority: **alias > bilingual > tiny-typo > templates > keyword**; log the chosen path in `normalized_map`.

---

## 13) Security & Privacy

* Default: offline/deterministic.
* If semantic fallback is enabled, restrict to an approved local/small model; log that it was used.

---

## 14) Controller Integration (what happens around this stage)

* UI button **PreProcessing** calls controller → `preprocess(user_text, sp, active_config)`.
* Controller updates `sp.body`, `sp.extras`, `sp.stage`, `sp.history_of_stages`.
* Controller regenerates `sp.prompt_ready` (per §8) and updates the GUI text area.
* Controller displays the unknowns gate (3 options) and records any decisions back into `sp.extras`.

---

## 15) Acceptance Checks (quick, testable)

* “LLM ROLE” maps to `system` (alias).
* “Die HAuptafffgäube” maps to `task` (tiny-typo + bilingual).
* Missing `tone` is filled from defaults and listed in `auto_filled`.
* Unknown “Metaphore” appears in `unknown_attributes` and is not included unless the user chooses to include CUSTOM ATTRIBUTES.
* Re-running with the same config reproduces all structures byte-for-byte.


