# Architecture – RAGstream (Aug 2025)

This document shows the end-to-end architecture for RAGstream, aligned with the main Requirements. It uses a local-first design with deterministic context construction, authority ordering, bounded audits, and transparent reasoning. **FileManife­st** is a **Must** for deterministic inclusion/versioning.

```text
                                     ┌───────────────────────────────────┐
                                     │      🔄  Ingestion Pipeline       │
                                     │───────────────────────────────────│
 User adds / updates docs  ─────────►│ 1  DocumentLoader (paths / watch) │
                                     │ 2  Chunker  (recursive splitter)  │
                                     │ 3  Embedder (E5 / BGE model)      │
                                     │ 4  VectorStore.add() (NumPy .pkl) │
                                     └───────────────────────────────────┘
                         ▲              ▲
                         │ builds       │ required
                         │              │
                         │              └──▶ 📇 FileManifest (path, sha256/MD5, mtime, type)
                         │
╔═════════════════════════════════════════════════════════════════════════════╗
║                               MAIN QUERY FLOW                               ║
╚═════════════════════════════════════════════════════════════════════════════╝

[User Prompt] ───▶ 🎛️  Streamlit GUI
                    ├── Prompt box (you)
                    ├── ON/OFF file checkboxes  (+ “Exact File Lock”)
                    ├── Prompt Shaper panel (intent/domain + headers)
                    ├── Agent toggles (A1..A4), Model picker, Cost estimator
                    ├── History controls: k (Layer-G size), Layer-E token budget, synonym import, mark-important toggle (UI-06 / CH-03.7 / CH-05)
                    ├── Super-Prompt preview (editable, source of truth)
                    ├── Optional export with citations (UI-07)
                    ├── External Reply box (UI-08) + “Send to History” (UI-09)
                    ├── Persist History toggle (UI-11): ON/OFF (default ON) for Layer-E store
                    ├── Clear History (UI-12): purge persisted Layer-E store on confirmation (Layer-G kept in-memory)
                    └── Transparency (kept/dropped reasons)

                    ▼
                 🧠 Controller
                    ├── A2 Prompt Shaper — pass-1 (uses: Project Memory + ConversationMemory.G/E)
                    ├── A0 FileScopeSelector (deterministic pre-filter; reason-trace; no embeddings)
                    ├── A1 Deterministic Code Injector (files you named)
                    │     └─ emits:  ❖ FILES (FULL or PACK); if locked ⇒ retrieval is skipped
                    ├── Eligibility Pool (from ON/OFF checkboxes)
                    ├── (if not locked)
                    │      ┌──────────────────────────────────────────────┐
                    │      │ 🔍 Retriever → 🏅 Reranker → A3 NLI Gate → A4│
                    │      │ Condenser (S_ctx: Facts / Constraints /      │
                    │      │ Open Issues + citations)                     │
                    │      └──────────────────────────────────────────────┘
                    ├── A2 Prompt Shaper — audit-2 (reads S_ctx + same anchors)
                    ├── PromptBuilder (authority order; may show a brief “RECENT HISTORY” view)
                    ├── 📡 LLMClient (model call + cost)
                    ├── A5 Schema/Format Enforcer (contract check; one self-repair; escalate on FAIL)
                    └── 📊 Transparency panel (kept/dropped reasons)

                    ▲
                    │  read-only
                    │
             🗂️ ConversationMemory
             (G = recency window; E = episodic w/ metadata + selection-only semantic index; soft fading)
```

*Notes:* **ConversationMemory** is a **controller-side, read-only** source exposed to A2 and PromptBuilder; ❖ FILES and authority order remain decisive. External replies are ingested via UI-08/09 with `source=external`. **❖ FILES** remain authoritative over history.

---

## Ingestion & Memory

**DocumentLoader** discovers files under `data/doc_raw/`.
• Current: `.txt`, `.md`, `.json`, `.yml`.
• **FileManifest is Must**: `path`, `sha256` (or MD5), `mtime`, `type` for deterministic inclusion/versioning.
**Chunker**: token-aware overlapping windows (≈1 024 tokens, overlap ≈200).
**Embedder**: E5/BGE family (configurable).
**VectorStore**: **NumPy `.pkl` snapshots** (Chroma paused; on-disk collection planned later).

### Conversation Memory (read-only; two-layer, soft fading)

**Purpose.** Maintain flow/coherence without re-chunking chat; history is durable; Layer-E embeddings are **selection-only** and kept **separate** from document vectors. The Layer-E semantic index is used **only to score episodic turns for inclusion (never to populate `S_ctx`).**

**Layers.**

**G — Recency window (always included; configurable k).**
**E — Episodic store (older turns + metadata: turn distance, Δt?, tags, importance, source, version hints).** Soft fading and token budgets apply; duplicates vs ❖ FILES are suppressed; ❖ FILES > newer > older.

#### Feature-1: Conversation History **Persistence** & **Async Layer-E Embedding**

> **Goal:** Make history durable on disk and keep Layer-E selection-only embeddings current without blocking the prompt path; ensure atomic snapshot publishing; never block the prompt path on embeddings.

**(F1-1) Append-only conversation log (single source of truth).**

* Path: `PATHS.logs/conversation.jsonl`.
* After each completed turn (user prompt + assistant reply), the controller appends both lines and the writer **flushes + fsyncs** before accepting the next prompt.
* If the reply comes from outside (UI-08/09), the controller appends the pasted text with `source=external`.
* **Layer-G is reconstructed from the tail of this file** on each prompt; no RAM-only history.

**(F1-2) Guardrails unchanged.**

* ❖ FILES, newer-over-older, dedup vs ❖ FILES, and Eligibility Pool rules remain unchanged.

**(F1-3) Layer-E embedding store (separate from documents).**

* Maintain a dedicated **NumPy** vector store snapshot for history (e.g., `history_store.pkl`).
* **Append-only; selection-only:** used to **score** episodic turns for inclusion and **never** injected into `S_ctx`.
* **Completely separate** from the document vector snapshots.
* Enforce **capacity caps** and token budgets per guardrails.

**(F1-4) Async delta embedding worker.**

* After the synchronous log append completes, enqueue the **new tail** for background processing:

  1. read only the unprocessed tail with a **small overlap** (one last chunk) for boundary stability;
  2. split into chunks;
  3. embed the **new chunks**;
  4. write to a **staging** `.pkl`.
* Use **stable IDs** (e.g., `<log_offset>::chunk_n`) and content-hash de-duplication.
* This ensures we never re-embed the whole log.

**(F1-5) Atomic snapshot publishing.**

* Writers only touch `history_store_dynamic.pkl`.
* When a batch is complete, **flush+fsync** and then **publish** via `os.replace(history_store_dynamic.pkl → history_store.pkl)`.
* Readers always open `history_store.pkl` and therefore see either the old or the new snapshot — **never a half-write**.
* A companion `history_index_meta.json` stores versioning/read-path hints to aid deterministic recovery.

**(F1-6) Read paths per prompt.**

* **G:** tail of `conversation.jsonl` (synchronous).
* **E:** open current `history_store.pkl` (latest published snapshot).
* The prompt path **never blocks** on embedding; it uses the last published E snapshot.

**(F1-7) Startup & failure behavior.**

* On startup, open/create `conversation.jsonl`, build G from tail, and try to open `history_store.pkl`.
* If E is missing, start empty and let the worker backfill from the log.
* If the worker fails, the last published snapshot remains valid; retry next cycle.

**(F1-8) Authority, eligibility, dedup unaffected.**

* Exact File Lock and the Eligibility Pool continue to bound retrieval; A3 suppresses any history text that duplicates an injected ❖ FILES item.

**(F1-9) Eligibility alignment with history (CH-03.9).**

* If a file is **OFF** in the Eligibility Pool for this turn, **Layer-E selection ignores** history items whose source/version hints point to that file (path/hash/mtime), **unless** that file is explicitly injected via **❖ FILES** for this turn.

---

## Retrieval & Agent Stages

### A0 — FileScopeSelector

**What:** Deterministic pre-filter that computes the Eligibility Pool from FileManifest, ON/OFF, and ❖ FILES; no embeddings; emits reason-trace.

Outputs (envelope): eligible\_files\[{path, sha256, mtime, reason\[]}], candidate\_files\_block{files\[]}, trace\[{path, decision, reason\[]}]; failure codes: EMPTY\_ELIGIBILITY, LOCK\_MISS (escalate=true).

### A1 — Deterministic Code Injector (❖ FILES)

**What:** Injects **exact file spans** (FULL or PACK); respects Exact File Lock and Eligibility Pool (when not locked). Markdown/notes remain for retrieval; A1 targets code/config deterministically.

### A2 — Prompt Shaper (intent/domain + meta-prompt headers)

**What:** Lightweight **prompt shaper** proposing task **intent/domain** and structured headers.
**Pass-1 (pre-retrieval):** Uses {**user prompt + Project Memory + ConversationMemory.G/E**}.
**Audit-2 (post-A4):** Reads **`S_ctx`** (plus same anchors) to **audit** and **refine** headers/roles; **cannot override** Hard Rules, Project Memory, or Exact File Lock.
**Bounded re-run rule:** If audit-2 **materially** changes **task scope** (intent/domain), permit **one** re-run of *Retriever → Reranker → A3 → A4*; otherwise reuse the existing `S_ctx`.
**Material scope change rubric:** change of **intent/domain**, or **target artifact set** affecting retrieval eligibility, or **deliverable type** (code vs spec vs plan). Pure tone/audience/format changes **do not** qualify.

### A3 — NLI Gate (semantic filter)

**What:** Drops candidates not **entailed** by the query/task; adjustable strictness θ; obeys ❖ FILES precedence and dedup rules.

### A4 — Condenser (context composer)

**What:** Emits `S_ctx` with **Facts / Constraints / Open Issues** (cited).
**Guarantee:** Every Fact carries ≥1 citation; if schema fails, controller triggers fallback (SAF-A1).

### A5 — Schema/Format Enforcer (contract check; one self-repair; escalate on FAIL)

**What:** Validates generated artifacts against CodeSpec.md; performs exactly one bounded self-repair, then re-validates; on FAIL → escalate=true.

Outputs (envelope): status PASS|FAIL; violations[{rule, evidence, suggestion}]; hashes{spec_sha256, draft_sha256, final_sha256}; artifact{filename, code_fenced}; exactly one self-repair then re-validate once; on FAIL → escalate=true.


---

## Prompt Orchestration

**Authority order (fixed):** \[Hard Rules] → \[Project Memory] → \[❖ FILES] → \[S\_ctx] → \[Task/Mode].
**PromptBuilder** assembles the final system/user messages; it may optionally show a **“RECENT HISTORY”** block (non-authoritative). **Exact File Lock** injects only ❖ FILES and skips retrieval entirely.

---

## Safety (Guardrails / Brakes / Airbags)

**Guardrails**
• **SAF-G1** Prompt-injection checks on retrieved text: neutralize/strip instructions that attempt to subvert rules before orchestration.
• **SAF-G2** Enforce A4 schema validation (`Facts / Constraints / Open Issues`) prior to PromptBuilder composition.
• **SAF-G3** Pre-send token/cost ceiling: LLMClient/PromptBuilder estimate and block over-budget sends; clear UI reason.

**Brakes**
• **SAF-B1** Controller-level timeouts for retrieval, rerank, A3, and A4; on limit breach, cancel the stage and apply fallback.
• **SAF-B2** Global cancellation: any stalled agent can be aborted cleanly; user can retry with adjusted settings.

**Airbags (Fallbacks)**
• **SAF-A1** If A4 fails or schema validation fails → fallback to showing top reranked, NLI-kept chunks with citations.
• **SAF-A2** If retrieval fails → proceed with ❖ FILES-only path.
• **SAF-A3** If LLM call fails → retry once with a smaller/cheaper compatible model; on repeat failure, surface reason.
• **SAF-A4** Optional rollback: if A2 (audit-2) changed scope and the re-run produced empty/invalid `S_ctx`, revert to previous `S_ctx`.

---

## Eligibility Pool

ON/OFF checkboxes constrain which files are eligible for retrieval (when not locked). The pool affects the Retriever’s candidate set before rerank, NLI gate, and condensation. Authority order ensures the final prompt never violates Hard Rules or Project Memory.

---

## Structured JSON Communication & Provenance

**Envelope Required (SR2-JSON-01).** Every inter-agent handoff uses a structured JSON **Envelope** with stable top-level keys:
`agent, goal, timestamp, request_id, turn_id, source, version, escalate, reason, provenance, payload`.

**Determinism (SR2-JSON-02).**
Envelope keys are stable; each agent’s `payload` schema is documented; float scores use fixed precision; no free-text handoffs (prose lives inside typed fields in `payload`).

**Provenance & Hashing (SR2-JSON-03).**
Referenced files include `path+hash+mtime`; history items include `id/hash`; the controller may attach a content hash of `payload` for traceability.

**Transport & Storage (SR2-JSON-04).**
JSON flows are in-process; for debugging, the **Debug Logger** may write envelopes to disk (trace/vars), but envelopes remain the system of record for inter-agent data.

**Validation (SR2-JSON-05).**
Controller validates required envelope fields before dispatch; on missing/invalid fields, set `escalate=true` with reason and halt (Human-in-the-Loop).

---

## Feature-2 — Debug Logger (developer-oriented; optional)

**Purpose:** Deterministic developer logs separate from ConversationMemory.
**Files:** Each GUI session creates new logs under `PATHS.logs/` with a common timestamped stem:

* `debug_trace_YYYYmmdd-HHMMSS_sessNN.log` — compact actions/steps/explanations.
* `debug_vars_YYYYmmdd-HHMMSS_sessNN.log` — variable dumps (only if `vars_enabled=True`).

**Methods:**

* `logWriteText(msg, level="INFO")` → `[ts] [LEVEL] msg` to `debug_trace`; mirror to `debug_vars` if vars enabled.
* `logWriteVar(name1, value1, ...)` → always writes an explanation line to `debug_trace`; if `vars_enabled=True`, writes `name=value` pairs to `debug_vars`.

**Truncation:** default max 200 chars/items; per-variable override by passing `(name, maxlen)`; truncated dumps include ellipsis & length metadata.
**Levels:** at least `INFO` and `DEBUG`; `min_level` drops lower-priority lines before enqueue.
**Rotation:** append-only by default; optional rollover when file size > N MB using atomic replace (rotate `.1`…`.K`).
**Serialization:** dict/list to safe JSON-like form; large/numpy/pandas/torch objects → type + shape/len + preview; otherwise `repr()`.
**Crash-survivability:** writer flushes + fsyncs each line; if `vars_enabled=False`, no `debug_vars` file is produced.

---

## Persistence & Modularity

Vectors persist as **NumPy `.pkl` snapshots**; Chroma on-disk collection is planned once stable in your environment. **ConversationMemory** persists JSONL in `conversation.jsonl` and publishes **Layer-E** snapshots via atomic swap. The system remains modular to enable future AWS TinnyLlama Cloud integration (swap embedding models, LLMs, or vector store without touching UI/controller surfaces).

---

## Non-Functional Targets (mirror)

| Category         | Target                                                                                                                                                        |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Determinism      | Fixed orchestration; at most one A2 audit; at most one retrieval re-run per query.                                                                            |
| Latency          | Prompt→first token < 3 s p95 with \~1M-token vector snapshot (CPU-only acceptable).                                                                           |
| Memory footprint | ≤ 6 GB peak; embeddings loaded on demand.                                                                                                                     |
| Privacy/Locality | Personal, single-user workflow; **no telemetry**; **ConversationMemory persists locally** (Layer-G log + Layer-E store); **Debug Logger is user-controlled**. |
| Extensibility    | Add a new agent or embedding model without touching > 1 file.                                                                                                 |

## Technology Stack (mirror)

| Layer           | Library / Service                          | Version (Aug 2025)         |
| --------------- | ------------------------------------------ | -------------------------- |
| GUI             | Streamlit                                  | 1.38                       |
| Embeddings      | `bge-large-en-v3`, `E5-Mistral` (optional) | sentence\_transformers 3.0 |
| Vector Store    | NumPy `.pkl` snapshots (current)           | –                          |
| Planned DB      | Chroma                                     | 0.10                       |
| Cross-encoder   | `mixedbread-ai/mxbai-rerank-xsmall-v1`     | 🤗 cross-encoder 0.6       |
| LLM API         | OpenAI (`openai>=1.15.0`)                  | GPT-4o                     |
| Local LLM (opt) | Ollama                                     | 0.2                        |

## Directory / Module Tree (mirror)

```
.
├── data/
│   ├── chroma_db/         # planned
│   └── doc_raw/
├── ragstream/
│   ├── app/
│   │   ├── controller.py
│   │   ├── ui_streamlit.py
│   │   └── agents/
│   │       ├── a1_dci.py
│   │       ├── a2_prompt_shaper.py
│   │       ├── a3_nli_gate.py
│   │       └── a4_condenser.py
│   ├── orchestration/
│   │   ├── prompt_builder.py
│   │   └── llm_client.py
│   ├── retrieval/
│   │   ├── retriever.py
│   │   └── reranker.py
│   ├── ingestion/
│   │   ├── loader.py
│   │   ├── chunker.py
│   │   └── embedder.py
│   └── memory/
│       └── conversation_memory.py   # read-only views for G/E
```

## Open Issues / Risks (mirror)

| Risk                           | Mitigation                                                                 |
| ------------------------------ | -------------------------------------------------------------------------- |
| Cross-encoder latency on CPU   | Limit candidates; single pass; cache embeddings where feasible.            |
| History selection bloat        | Enforce token budgets; smooth fading; manual importance pinning.           |
| A2 audit causes scope creep    | Single audit only; retrieval re-run allowed once and only on scope change. |
| Chroma environment instability | Keep `.pkl` snapshots until stable.                                        |

---

# Sync Report

**Integrated features (per Requirements v2.3):**

* **Feature-1:** Durable `conversation.jsonl`, Layer-G tail read, dedicated Layer-E **selection-only** embedding store, async delta worker, **atomic** snapshot publishing, per-prompt read paths (G from JSONL tail, E from latest snapshot), startup/backfill behavior, and preservation of authority/eligibility/dedup rules; **CH-03.9** eligibility alignment for history respected.
* **Feature-2:** **Debug Logger** with trace/vars files, methods, truncation, levels, optional rollover, serialization rules, and crash-survivability semantics.
* **UI-08/09:** External reply import path (`source=external`) into ConversationMemory and participation in Layer-E selection/dedup.
* **UI-11/12:** Persist History toggle (default ON) and Clear History control for Layer-E store management.
* **FileManifest = Must**; authority order **❖ FILES > newer > older**; Exact File Lock; Eligibility Pool; A2 audit with **single bounded re-run** and **material scope change** rubric.
* **A0 FileScopeSelector**: deterministic pre-filter runs before A1; honors ❖ FILES and ON/OFF; emits reason-trace.
* **A5 Schema/Format Enforcer**: contract check with exactly one self-repair; escalates on FAIL.
* **JSON envelopes & HIL**: all inter-agent handoffs use JSON envelopes; schema/determinism failures set `escalate=true` and halt.
* **Safety set:** Guardrails (SAF-G1..G3), Brakes (SAF-B1..B2), Airbags/Fallbacks (SAF-A1..A4) explicitly included.
* **Non-Functional Requirements:** determinism, latency, memory footprint, privacy/locality, and extensibility targets stated.

**Alignment confirmation:**
`Architecture_2.md` reflects Layer-E selection-only embeddings, durable JSONL history, external reply import, bounded A2 audit, Eligibility Pool, authority order, FileManifest, Debug Logger, JSON envelopes/HIL, **Safety guardrails/brakes/airbags**, **UI-11/12**, and **Non-Functional** targets, with prior text preserved except for the minimal additions above.

---

## Sync Report (this update)

**Precisely applied changes (minimal edits only):**

* Added two GUI bullets for **UI-06** (history controls) and **UI-07** (optional export with citations).
* Added two GUI bullets previously present for **UI-11** (Persist History toggle) and **UI-12** (Clear History).
* Inserted **Safety (Guardrails / Brakes / Airbags)** section with SAF-G1..G3, SAF-B1..B2, SAF-A1..A4.
* Added **Structured JSON Communication & Provenance** section (SR2-JSON-01..05).
* Appended **(F1-9)** to Conversation Memory to capture **CH-03.9** eligibility alignment for history.
* Expanded **Sync Report** to reflect Safety, UI-06/07/11/12, JSON Envelopes, and Non-Functional coverage.

**Conformance confirmation:**
This `Architecture_2.md` now mirrors `Requirements.md` v2.3, with all missing items integrated and existing content left otherwise byte-identical.
