# Requirements_RAG_Pipeline.md

Goal: define the 8-step RAG pipeline (A0…A5 + Prompt Builder), how each stage mutates `SuperPrompt`, which parts are deterministic vs LLM/hybrid, and how the stages fit together in both manual (GUI buttons) and auto mode. This document assumes the data model in `super_prompt.py` and the agent stack described in `Requirements_AgentStack.md`.

---

## 1. Scope and assumptions

1. The pipeline is a single linear chain of stages, driven either:

   * manually via the 8 GUI buttons in `ui_streamlit_2.py`, or
   * automatically by the controller in the same order.
2. The canonical state carrier is `SuperPrompt` (class in `ragstream/orchestration/super_prompt.py`). All stages are **memoryless**: they take `(SuperPrompt, config)` as input, mutate it in a controlled way, and return it; no stage keeps its own long-lived internal memory.
3. Retrieval and reranking are fully **deterministic**, running on CPU-only embeddings + cross-encoder as agreed. All other “A-agents” use the neutral agent stack (`AgentFactory`, `AgentPrompt`, `llm_client`) defined in `Requirements_AgentStack.md`.
4. The pipeline is designed so that constants (N0, N1, …) are **configurable** via JSON/YAML; no hard-coded “magic numbers” are allowed in code.

---

## 2. Stage overview

### 2.1 Order of stages (GUI / controller)

Button sequence (manual mode), which is also the execution order in auto mode:

1. A0_PreProcessing
2. A2_PromptShaper
3. Retrieval
4. ReRanker
5. A3_NLI_Gate
6. A4_Condenser
7. A5_Format_Enforcer
8. Prompt_Builder

`SuperPrompt.stage` uses the fixed vocabulary:

* `"raw"` → initial
* `"preprocessed"` → after A0_PreProcessing
* `"a2"` → after A2_PromptShaper
* `"retrieval"` → after Retrieval
* `"reranked"` → after ReRanker
* `"a3"` → after A3_NLI_Gate
* `"a4"` → after A4_Condenser
* `"a5"` → after A5_Format_Enforcer (Prompt_Builder does not introduce a new stage).

`SuperPrompt.history_of_stages` is append-only and records each stage name as it completes.

### 2.2 Stage summary table

| Step | Name               | `stage` value  | Kind           | LLM usage                             | Agent role (Axis 4)                  | Main responsibility                                                                                                                                     |
| ---- | ------------------ | -------------- | -------------- | ------------------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | A0_PreProcessing   | `preprocessed` | Function/Agent | Deterministic + optional LLM fallback | Extractor + Chooser (if LLM enabled) | Canonicalize user prompt into `sp.body`, enforce MUST fields, build `prompt_ready`.                                                                     |
| 2    | A2_PromptShaper    | `a2`           | Agent          | LLM-only                              | Chooser                              | Classify `system`, `audience`, `tone`, `depth`, `confidence` from task/context/purpose.                                                                 |
| 3    | Retrieval          | `retrieval`    | Function       | No LLM                                | –                                    | Vector retrieval from conversation history + long-term memory, populate `base_context_chunks` and `views_by_stage["retrieval"]`.                        |
| 4    | ReRanker           | `reranked`     | Function       | No LLM                                | –                                    | Cross-encoder reranking of top candidates, write `views_by_stage["reranked"]`.                                                                          |
| 5    | A3_NLI_Gate        | `a3`           | Agent          | Hybrid                                | Chooser                              | LLM-based keep/drop decision on candidate chunks (relevance, contradiction, duplicates), write `views_by_stage["a3"]` and update `final_selection_ids`. |
| 6    | A4_Condenser       | `a4`           | Agent          | LLM-only                              | Writer                               | Condense selected chunks into `S_CTX_MD`, enforce token budget, finalize `final_selection_ids`.                                                         |
| 7    | A5_Format_Enforcer | `a5`           | Agent          | LLM-only                              | Writer/Extractor                     | Normalize instructions and output format rules in `sp.body`/`extras` so final answer obeys structure.                                                   |
| 8    | Prompt_Builder     | (stays `a5`)   | Function       | No LLM                                | –                                    | Render `System_MD`, `Prompt_MD`, `S_CTX_MD`, `Attachments_MD`, final `prompt_ready` from `SuperPrompt`.                                                 |

---

## 3. Common data model and invariants

All stages use the same `SuperPrompt` invariants:

1. `base_context_chunks` is the **authoritative set** of retrieved `Chunk` objects for the session (merged from conversation history + long-term memory, de-duplicated by `id`). No stage creates a second corpus; later stages only manipulate views on these chunks.
2. `views_by_stage[stage]` is an **ordered list of `chunk_id`s** written by each stage that deals with retrieval results (Retrieval, ReRanker, A3, A4). This captures ranking/filter choices without duplicating text.
3. `final_selection_ids` always contains the current chosen `chunk_id`s for building `S_CTX_MD` and `Attachments_MD`. After A4 it reflects the token-budgeted subset that feeds the final LLM.
4. `Chunk` objects are **immutable** after creation. Any scores, keep/drop flags, etc. live only in stage-local maps and views.
5. `System_MD`, `Prompt_MD`, `S_CTX_MD`, `Attachments_MD` are **rendered at send time**, derived from `body`, `recentConversation`, and the id lists. They may be empty until Prompt_Builder runs.

---

## 4. Fixed numeric defaults (N-constants)

The pipeline uses named constants instead of magic numbers. All are configurable (JSON/YAML), but these are the **default values**:

* `N0_QUERY_PIECES = 5`

  * Number of query sub-spans extracted from the user prompt for embedding-based retrieval.
* `N1_RETR_MAX_CANDIDATES = 200`

  * Max number of high-scoring chunks kept after initial vector retrieval (per session).
* `N2_RERANK_TOP_K = 50`

  * Number of candidates from `views_by_stage["retrieval"]` passed into the cross-encoder reranker. (Matches the earlier “~50 candidates per query” decision.)
* `N3_FINAL_SELECTION_MAX = 24`

  * Upper bound on `final_selection_ids` after A4 (token budget + readability constraint).
* `N4_RECENT_CONV_MAX_PAIRS` (e.g. 8–12)

  * Max turn-pairs in `recentConversation` that may be included in the final prompt.

Requirements:

1. The constants above must live in a **single config** (e.g. `config/pipeline_limits.json`) and never be hard-coded.
2. Stages must treat these as **soft caps**: they can internally cut below the limit but never exceed it.
3. Changing these constants must not require code changes; only config + tests.

---

## 5. Stage-by-stage requirements

### 5.1 A0_PreProcessing

Reference: `Req_PreProcessing.md` and the implemented `preprocessing.py`.

Purpose

* Convert raw user prompt text into a canonical `sp.body`, enforce MUST attributes, and generate a clean GUI snapshot in `sp.prompt_ready`. No retrieval, no LLM by default.

Inputs

* `user_text: str` – raw prompt from GUI.
* `sp: SuperPrompt` – preferably at `stage="raw"` (but may be re-run).
* `prompt_schema.json` – canonical keys, MUST keys, defaults, aliases, bilingual map, typo tolerance, etc.

Outputs / mutations

1. Header parsing and mapping:

   * Use the deterministic “mapping ladder” (normalize → exact → alias → tiny-typo → bilingual → templates → keyword → unknown).
   * Map headers into canonical keys `{system, task, audience, tone, depth, context, purpose, format, text, ...}`.
2. MUST enforcement:

   * Apply TASK/CONTEXT special rule and fill defaults for other MUST keys.
3. Write into `sp.body` only for known keys; unknowns go to `sp.extras["unknown_attributes"]`.
4. Build `sp.prompt_ready` with `_compose_prompt_ready(...)` and update stage:

   * `sp.stage = "preprocessed"`
   * `sp.history_of_stages.append("preprocessed")`
5. No changes to retrieval fields: `base_context_chunks`, `views_by_stage`, `final_selection_ids` remain untouched.

Optional LLM fallback

* If `prompt_schema.modes.semantic_enabled = true`, A0 may call an LLM via the AgentStack as a **tiny Chooser agent** for header mapping, but:

  * It must still be deterministic at the pipeline level (fixed threshold, logged decisions).
  * All LLM operations and decisions are recorded into `sp.extras["semantic_used"]`, `normalized_map`, and `decisions`.

### 5.2 A2_PromptShaper

Purpose

* Classify the five meta-fields `system`, `audience`, `tone`, `depth`, `confidence` based on `task`, `context`, `purpose`, and the user prompt, using a fine-tuned OpenAI model (A2).

Nature

* Kind: Agent (uses AgentFactory, AgentPrompt, llm_client).
* Type: **Chooser** (closed enums, JSON output).
* LLM usage: LLM-only (stateless, single call per pass).

Inputs

* `sp: SuperPrompt` with `stage="preprocessed"`.
* A2 agent config JSON (see `Requirements_AgentStack.md`), containing:

  * Name / version (e.g. `"agent_name": "A2_PromptShaper", "version": "v1"`).
  * Enum lists for `system`, `audience`, `tone`, `depth`, `confidence`.
  * Default values and thresholds (e.g. min confidence).
  * Underlying model id (e.g. `ft:gpt-4.1-mini-...`), temperature, etc.

Behaviour

1. A2 **pass-1**:

   * Build input payload from `sp.body["task"]`, `sp.body["context"]`, `sp.body["purpose"]`, and possibly the raw prompt text.
   * Through AgentFactory → AgentPrompt → llm_client, call the A2 model to get a JSON object:
     `{ "system": ..., "audience": ..., "tone": ..., "depth": ..., "confidence": ... }`.
   * Enforce enums: if LLM output is outside the allowed sets, clamp to defaults.
2. Update `sp.body` fields (`system`, `audience`, `tone`, `depth`, `confidence`) and write logs into `sp.extras["a2_decisions"]`.
3. Bookkeeping:

   * `sp.stage = "a2"`
   * `sp.history_of_stages.append("a2")`
4. A2 **pass-2** (optional runtime refinement) uses the same model and agent config, but includes the earlier A2 output as part of the input payload. The requirement here is only to keep it **compatible**; details of pass-2 policies can be added later.

No retrieval fields are touched here.

### 5.3 Retrieval

Purpose

* Build the first ranked candidate list of chunks from both conversation history and long-term documents.

Nature

* Kind: Function (no LLM).
* Type: deterministic, CPU-friendly vector search.

Inputs

* `sp: SuperPrompt` with `stage="a2"`.
* Embedding index(es) for:

  * recent conversation chunks,
  * long-term Markdown/file chunks.
* Config:

  * `N0_QUERY_PIECES`, `N1_RETR_MAX_CANDIDATES`, embedding model name, τ for LogAvgExp.

Behaviour

1. Query decomposition:

   * Build a **normalized query string** from `sp.body["task"]`, `sp.body["context"]`, `sp.body["purpose"]`.
   * Split into `N0_QUERY_PIECES` pieces (e.g. 5) following the agreed chunking rules.
2. For each piece, perform vector search over the combined index; for each candidate chunk compute cosine scores.
3. Aggregate per-chunk scores across pieces with **LogAvgExp (τ = 9)** and length normalization.
4. Merge results from conversation and long-term memory, de-duplicate by `chunk_id`, and keep the top `N1_RETR_MAX_CANDIDATES`.
5. Populate `sp.base_context_chunks` with the **unique `Chunk` objects** for these ids (creating them if needed).
6. Write:

   * `sp.views_by_stage["retrieval"] = [chunk_id_1, chunk_id_2, ...]` (in score order).
   * `sp.stage = "retrieval"` and append to history.

The retrieval step does **not** set `final_selection_ids` yet; that is the job of A3/A4.

### 5.4 ReRanker

Purpose

* Use a cross-encoder to refine the ranking of the top candidates from Retrieval, independent of embedding geometry.

Nature

* Kind: Function.
* Type: deterministic.

Inputs

* `sp: SuperPrompt` with `stage="retrieval"`.
* Candidate ids: `sp.views_by_stage["retrieval"][:N2_RERANK_TOP_K]`.
* Model: `cross-encoder/ms-marco-MiniLM-L-6-v2`.

Behaviour

1. Render a **single query string** `Prompt_MD` from `sp.body` (task/purpose/context/format) for reranking; do **not** include `System_MD` or attachments.
2. For each candidate id (up to `N2_RERANK_TOP_K`), look up its `Chunk` text (`snippet`) and run the cross-encoder on `(Prompt_MD, snippet)`.
3. Sort by cross-encoder score descending and write:

   * `sp.views_by_stage["reranked"] = [chunk_id_1, chunk_id_2, ...]` in the new order.
4. Update:

   * `sp.stage = "reranked"`; append history.

Still no mutations to `final_selection_ids`.

### 5.5 A3_NLI_Gate

Purpose

* Filter and clean the reranked list using an LLM as a **semantic gate** (NLI / contradiction / redundancy checks).

Nature

* Kind: Agent.
* Type: **Hybrid**: Python pre-filters + LLM Chooser.

Inputs

* `sp: SuperPrompt` with `stage="reranked"`.
* Candidate ids: `sp.views_by_stage["reranked"]`.
* A3 agent config JSON (via AgentFactory), including:

  * max candidates to consider,
  * NLI labels / thresholds,
  * allowed decisions: `{keep, drop_irrelevant, drop_duplicate, drop_conflict}`, etc.

Behaviour

1. Optional deterministic pre-filter:

   * Cap candidates to a working set (e.g. first 80) to keep the LLM payload manageable.
   * Remove obviously empty or trivial chunks.
2. Build an A3 AgentPrompt (Chooser over many items):

   * Input payload: `Prompt_MD` + a numbered list of candidate summaries `(id, short snippet, source)`.
   * Enums: for each candidate id, the agent must choose `keep` or `drop`, possibly with a tag (`duplicate`, `off-topic`, `conflicting`).
3. Call LLM via llm_client; parse the JSON response; keep only candidates with `decision == "keep"`.
4. Write:

   * `sp.views_by_stage["a3"] = [kept_id_1, kept_id_2, ...]`.
   * `sp.final_selection_ids = sp.views_by_stage["a3"][:]` (initial final selection).
5. Update stage:

   * `sp.stage = "a3"`; append history.

A3 must **never** mutate `Chunk` contents; it only changes which ids survive.

### 5.6 A4_Condenser

Purpose

* Condense the selected context into a high-authority `S_CTX_MD` and enforce a hard context/token budget by trimming `final_selection_ids`.

Nature

* Kind: Agent.
* Type: LLM-only, Writer.

Inputs

* `sp: SuperPrompt` with `stage="a3"`.
* Candidate ids: `sp.final_selection_ids` (initially from A3).

Behaviour

1. Build an AgentPrompt for A4:

   * Input payload contains:

     * `Prompt_MD` (user ask),
     * a list of selected chunks (id, snippet, minimal provenance),
     * instructions: summarize **facts**, **constraints**, and **open issues** relevant to the ask; do not invent new facts.
   * Output contract:

     * `s_ctx_md` (markdown string),
     * optionally per-id relevance scores or ranks.
2. Call LLM; receive `S_CTX_MD` and any auxiliary scores.
3. Apply token/size budgeting:

   * If the set of chunks is too large, down-select to at most `N3_FINAL_SELECTION_MAX` ids, keeping those with highest relevance scores or best coverage.
4. Write:

   * `sp.S_CTX_MD = <condensed markdown>`.
   * `sp.final_selection_ids = [subset_of_ids]`.
   * `sp.views_by_stage["a4"] = sp.final_selection_ids[:]`.
5. Update:

   * `sp.stage = "a4"`; append history.

A4 is the stage where **S_CTX becomes the authoritative context block** for the final LLM call, based only on the final selection ids (not the entire retrieved set).

### 5.7 A5_Format_Enforcer

Purpose

* Ensure that the final answer will follow the requested format (JSON, Markdown, checklist, code fence, etc.), and that instructions in `sp.body` are coherent and deterministic.

Nature

* Kind: Agent.
* Type: LLM-only, Writer/Extractor.

Inputs

* `sp: SuperPrompt` with `stage="a4"`.
* Fields from `sp.body`: `format`, `constraints`, `deterministic_rules`, `deterministic_codes`, any relevant extras from PreProcessing.

Behaviour

1. Build an AgentPrompt for A5:

   * Input payload:

     * the current `Prompt_MD` and `System_MD` concepts (from `sp.body`),
     * the target output format description,
     * any deterministic rules / codes.
   * Output: a small JSON or text block with:

     * `normalized_format_spec`,
     * `example_shape` (optional),
     * `hard_rules` (constraints restated in a model-friendly way).
2. A5 writes its results into:

   * `sp.extras["format_enforcer"] = {...}`;
   * may also rewrite `sp.body["format"]` into a cleaner description.
3. Update:

   * `sp.stage = "a5"`; append history.

A5 **does not** call retrieval again and does not change `final_selection_ids` or `S_CTX_MD`.

### 5.8 Prompt_Builder

Purpose

* Final deterministic assembly of the messages that will be sent to the final answering model.

Nature

* Kind: Function.
* Type: fully deterministic.

Inputs

* `sp: SuperPrompt` with `stage="a5"`.

Behaviour

1. Render `System_MD` from `sp.body["system"]`, `tone`, `depth`, and any A5 rules.
2. Render `Prompt_MD` from `task`, `purpose`, `context`, `audience`, `format`.
3. Render `S_CTX_MD` (already produced by A4) and **do not edit it**, except for minor non-semantic formatting if needed.
4. Render `Attachments_MD` as raw excerpts from `sp.final_selection_ids`:

   * formatted with provenance fences (`SOURCE: ...`, `SPAN: ...`).
5. Optionally merge `recentConversation` as a distinct block (not mixed into S_CTX).
6. Compose `sp.prompt_ready` as the final concatenation of these blocks in the agreed order:

   1. `System_MD`
   2. `Prompt_MD`
   3. `S_CTX_MD`
   4. `Attachments_MD`
   5. (optional) `Recent Conversation` block
7. `sp.stage` stays `"a5"`; Prompt_Builder **does not** change the lifecycle stage, it only prepares the final view/send-time representation.

---

## 6. Controller integration

1. Manual mode (GUI):

   * Each button calls the controller, which:

     * passes the current `SuperPrompt` to the corresponding stage function/agent,
     * receives the mutated `SuperPrompt`,
     * updates the GUI `Super-Prompt` box (`sp.prompt_ready`) after stages that change it (A0, A2, A4, A5, Prompt_Builder).
2. Auto mode:

   * Controller runs all stages in sequence:

     * `A0 → A2 → Retrieval → ReRanker → A3 → A4 → A5 → Prompt_Builder`,
     * then sends `System_MD + Prompt_MD + S_CTX_MD + Attachments_MD` to the final answering LLM.
3. At every step, controller must check:

   * `sp.stage` sequence is strictly increasing in the allowed order,
   * `views_by_stage` and `final_selection_ids` are consistent with the stage definitions,
   * error conditions (e.g. missing retrieval results) are surfaced to the GUI.

---

## 7. Acceptance criteria (high-level)

The RAG pipeline is considered correctly implemented when:

1. For a fixed prompt + fixed configs, running the full chain twice produces **byte-identical** `sp.body`, `views_by_stage`, `final_selection_ids`, and `S_CTX_MD` (LLM stages at temperature 0 or with fixed seeds).
2. `base_context_chunks` never contains duplicates by `id`, and no stage mutates its `Chunk` contents.
3. The number of candidates at each stage respects the N-constants:

   * `len(views_by_stage["retrieval"]) ≤ N1_RETR_MAX_CANDIDATES`,
   * candidates passed to the cross-encoder ≤ `N2_RERANK_TOP_K`,
   * `len(final_selection_ids) ≤ N3_FINAL_SELECTION_MAX`.
4. Turning LLM fallbacks off (A0 semantic mapping, A3, A4, A5) either:

   * degrades gracefully to deterministic defaults, or
   * blocks the pipeline with clear error messages; it never produces silent, half-configured output.
5. The final `prompt_ready` always contains:

   * a stable System block,
   * a normalized Prompt block,
   * a condensed S_CTX block,
   * clearly fenced attachments for manual inspection.

