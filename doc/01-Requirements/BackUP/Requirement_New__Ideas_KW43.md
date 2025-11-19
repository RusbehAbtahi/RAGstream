# RAGstream / PromptGenerator — Session State Reconstruction

This document reconstructs the previous session’s state with **exhaustive, factual detail**. It captures the agreed GUI, classes, retrieval math, reranker choice, processing order, and data-handling rules exactly as discussed.

---

## 1) Streamlit GUI (manual-first pipeline)

**File:** `ragstream/app/ui_streamlit_2.py`
**Run example:**
`python -m streamlit run /home/rusbeh_ab/project/RAGstream/ragstream/app/ui_streamlit_2.py --server.port 8503`

### Layout

* **Top-left title:** `RAGstream`.
* **Two large text areas (side-by-side):**

  * Left: **Prompt** (editable).
  * Right: **Super-Prompt** (shows the evolving prompt).
* **Eight buttons** under **Prompt**, in two rows (4 + 4), each with a dedicated handler:

  * Row 1: **PreProcessing**, **A2 PromptShaper**, **Retrieval**, **ReRanker**.
  * Row 2: **A3 NLI Gate**, **A4 Condenser**, **A5 Format Enforcer**, **Prompt Builder**.
* **Styling:** tight margins (hidden Streamlit header/toolbar), compact gaps between columns, prominent field titles, narrow gutters.
* **Mode:** **manual-first** (press buttons step-by-step). “Auto mode” discussed as future, calling the same functions in sequence. No automatic pipeline execution in this version.

---

## 2) Core classes

### 2.1 `SuperPrompt` (central session record)

**File (final agreed version):** `ragstream/orchestration/super_prompt.py`
**Construction:** plain Python class with `__slots__`, manual `__init__`, **no dataclass**.

**Fields (exact names and roles):**

* `stage` *(string; one of: raw, preprocessed, a2, retrieval, reranked, a3, a4, a5)* — current lifecycle state.

* `model_target` *(string)* — optional target LLM/model for this session.

* `history_of_stages` *(list of strings)* — append-only trail of visited stages (e.g., `["raw","preprocessed","a2",...]`).

* `body` *(dictionary)* — canonical prompt fields from the user; keys:
  `system`, `task`, `audience`, `role`, `tone`, `depth`, `context`, `purpose`, `format`, `text`.
  Defaults set: `"system": "consultant"`, `"tone": "neutral"`, `"depth": "high"`; required: `"task"` (must be set by caller).

* `extras` *(dictionary)* — user-defined or experimental fields kept separate from `body`.

* `base_context_chunks` *(list of `Chunk`)* — **authoritative set** of retrieved chunk objects for this session (merged from conversation history and long-term memory; de-duplicated by chunk id).

* `views_by_stage` *(dictionary: stage name → list of chunk IDs)* — for each processing stage, an **ordered** list of `chunk_id`s (captures ranking/filter snapshots without duplicating chunk text).

* `final_selection_ids` *(list of strings)* — current chosen `chunk_id`s (from the latest view after drops and token-budgeting); this list drives rendering of S_CTX and attachments.

* `recentConversation` *(dictionary)* — single block for recent dialog context (e.g., `{"body": <full transcript string>, "pairs_count": N, "range": (start_idx, end_idx)}`).

* `System_MD` *(string)* — rendered system/config block from `body` (role/tone/depth/rules).

* `Prompt_MD` *(string)* — rendered normalized ask from `body` (task/purpose/context/format).

* `S_CTX_MD` *(string)* — rendered short distilled summary from `final_selection_ids` (facts/constraints/open issues).

* `Attachments_MD` *(string)* — rendered raw excerpts with provenance fences from `final_selection_ids`.

**Important handling rule (agreed):** the four `*_MD` strings are **derived** at send time; they **may remain empty until render**. The authoritative data live in `body`, `recentConversation`, `base_context_chunks`, and the id lists (`views_by_stage`, `final_selection_ids`).

---

### 2.2 `Chunk` (minimal retrieved piece)

**File:** saved by user as `ragstream/orchestration/chunk.py` (works as-is).
*(A relocation to `retrieval/chunk.py` was discussed; current location remains under `orchestration`.)*

**Fields (no methods):**

* `id` *(str)* — stable identifier (e.g., vector-store id), used in all views and selections.
* `source` *(str)* — provenance (file path or URI) to locate the original text.
* `snippet` *(str)* — the actual text excerpt of this chunk.
* `span` *(tuple[int, int])* — start/end offsets (characters or lines) within the source.
* `meta` *(dict)* — extra metadata (e.g., sha256, mtime, file_type, chunk_index).

**Immutability convention:** chunk **content** is not edited after creation. Stage-specific changes (ranking, scores, keep/drop) are represented **outside** the object via `views_by_stage`, `final_selection_ids`, and any stage-level maps.

---

## 3) Retrieval and scoring (union + weighting)

### Sources merged

* **Conversation history** (recent dialog) and **long-term memory** (Markdown files) are retrieved **together**, merged into one candidate set, and **de-duplicated by `chunk_id`**. After merge, **origin does not matter** for ranking.

### Query decomposition

* The user prompt is divided into **multiple query pieces** (typical range discussed: **1–10**; example used frequently: **5** pieces).

### Per-candidate scoring (main agreed method)

* **LogAvgExp (length-normalized LogSumExp)** with **τ = 9** over the per-piece cosine similarities:
  [
  \text{score} ;=; \frac{1}{\tau},\log!\Big(\frac{1}{N}\sum_{i=1}^{N} e^{\tau, s_i}\Big)
  ]
  where (N) is the number of query pieces and (s_i) are cosine similarities to a given candidate chunk.

* **Rationale captured in-session:** τ=9 biases the aggregation toward **MAX** while still rewarding **consistent multi-piece support**. This setting satisfied the tested cases:

  * ([0.85 \times 5]) outranks a single ([0.90]).
  * ([0.40 \times 5]) remains below ([0.90]).
  * With two strong matches ([0.90, 0.90, 0, 0, 0]), the score remains below ([0.85 \times 5]), and above weak bundles, consistent with a max-leaning soft aggregator.

* **Numeric tables recorded (N=5):**

  * **For τ ∈ {1,3,5,7,9}**
    • ([0.9,0,0,0,0]): {0.2561, 0.4429, 0.5868, 0.6711, 0.7213}
    • ([0.85×5]): **0.8500** (for all τ under LogAvgExp normalization)
    • ([0.4×5]): **0.4000** (for all τ under LogAvgExp normalization)
  * **For τ ∈ {1,3,5,7,9}**, case ([0.9,0.9,0,0,0]): {0.4599, 0.6266, 0.7200, 0.7695, 0.7982}

---

## 4) Cross-encoder reranking (chosen library and usage)

* **Chosen reranker:** `cross-encoder/ms-marco-MiniLM-L-6-v2` (free; CPU-friendly).
* **Reason captured:** runs fast on **CPU-only** (ThinkPad + WSL2 environment), adequate quality for ~50 candidates per query.
* **Pairing rule:** reranker input is **(Prompt_MD, chunk_text)** — i.e., the **full normalized query string** paired with each candidate chunk’s text.

  * **Do not** include `System_MD` or retrieved attachments in the reranker query.
  * **Do not** rerank per query-piece; the cross-encoder expects a single query string.

---

## 5) Processing order and stage semantics

### Button sequence (manual mode)

1. **PreProcessing** (A0 pre-processing / file-scope selection, per earlier naming)
2. **A2 PromptShaper**
3. **Retrieval**
4. **ReRanker**
5. **A3 NLI Gate**
6. **A4 Condenser**
7. **A5 Format Enforcer**
8. **Prompt Builder**

*(A “single reranker pass” before A3 was the agreed default. Additional passes were acknowledged as possible but not part of this plan.)*

### LLM message composition (send-time rendering)

* Messages are constructed from four blocks, each rendered from `SuperPrompt` data:

  1. `System_MD`
  2. `Prompt_MD`
  3. `S_CTX_MD` *(summary of selected chunks)*
  4. `Attachments_MD` *(raw excerpts with provenance fences)*
* **`recentConversation`** is kept as a distinct **“Recent Conversation”** block (last N turn-pairs) that can be included explicitly in the prompt, separate from retrieved attachments.

---

## 6) Data handling rules (chunks, views, selections)

* **Authoritative set:** `base_context_chunks` holds the **unique** `Chunk` objects used for this session (no whole-corpus mirroring).
* **Stage outputs as views:** each stage writes an **ordered list of `chunk_id`s** in `views_by_stage[stage]`.
  This captures ranking and filtering **without duplicating** `Chunk` objects.
* **Final selection:** `final_selection_ids` contains the ids chosen from the latest view after filtering (e.g., A3) and token budgeting (e.g., A4).
* **No chunk mutation:** `Chunk` fields are immutable after creation; any keep/drop decisions and ranks live in the **views and selection lists**, not in the `Chunk`.
* **Vector operations stop after initial retrieval:** subsequent agents operate on the **text chunks**; additional vector passes are not part of the default flow.

---

## 7) Pre-processing concept (Tasks 1–4 snapshot)

*(Provided by the user and kept intact as the v1 design for the pre-processing agent.)*

* **Task 1 — Format detect & header extraction:** detect Plain/Markdown/JSON-like; extract headers/bodies with character spans; no classification yet.
* **Task 2 — Must-header check & canonicalization:** normalize header names; map via alias table into canonical set `{SYSTEM, TASK, CONTEXT, PURPOSE, USER_PROMPT, AUDIENCE, FORMAT, DEPTH}`; guarantee `TASK` via fallbacks; meta vs content separation.
* **Task 3 — Segment table:** drop meta sections; keep content sections `{TASK, CONTEXT, PURPOSE, USER_PROMPT}` with `id`, `canon_type`, `text`, `weight=1.0`, spans, and trace.
* **Task 4 — Chunking to query pieces:** split kept content into retrieval-ready pieces aligned with ingestion chunking rules; enforce model max length; produce final list for retrieval; preserve full traceability.

---

## 8) Finalized variables (SuperPrompt)

Exact list, as agreed and implemented:

* `stage` *(string)*
* `model_target` *(string)*
* `history_of_stages` *(list of strings)*
* `body` *(dictionary)*
* `extras` *(dictionary)*
* `base_context_chunks` *(list of `Chunk`)*
* `views_by_stage` *(dictionary: stage → list of chunk IDs)*
* `final_selection_ids` *(list of strings)*
* `recentConversation` *(dictionary)*
* `System_MD` *(string)*
* `Prompt_MD` *(string)*
* `S_CTX_MD` *(string)*
* `Attachments_MD` *(string)*

---

## 9) Environment notes

* Execution environment during development: **Windows 11 + WSL2 (Ubuntu 24.04)** on a **ThinkPad**, **CPU-only**.
* The reranker choice (`ms-marco-MiniLM-L-6-v2`) matches this constraint.

---

## 10) Decisions captured (no additions)

* **Aggregation method:** **LogAvgExp (LSE) with τ=9**, length-normalized by N (number of query pieces).
* **Reranking:** **single pass** with **`cross-encoder/ms-marco-MiniLM-L-6-v2`**, scoring `(Prompt_MD, chunk_text)`.
* **Merged sources:** conversation history and long-term memory are merged and treated uniformly after retrieval.
* **Data model:** `Chunk` immutable; **views and selections** carry stage outcomes; avoid duplicating chunk text.
* **LLM prompt blocks:** `System_MD`, `Prompt_MD`, `S_CTX_MD`, `Attachments_MD` (rendered at send time); `recentConversation` is a separate block.

---

