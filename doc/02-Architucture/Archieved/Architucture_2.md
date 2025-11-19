````markdown
# Architecture – RAGstream (Oct 2025)

This document shows the end-to-end architecture for RAGstream, aligned with the main Requirements. It uses a local-first design with deterministic context construction, authority ordering, bounded audits, and transparent reasoning. **FileManifest** is a **Must** for deterministic inclusion/versioning.

```text
                                     ┌───────────────────────────────────┐
                                     │      🔄  Ingestion Pipeline       │
                                     │───────────────────────────────────│
 User adds / updates docs  ─────────►│ 1  DocumentLoader (paths / watch) │
                                     │ 2  Chunker  (recursive splitter)  │
                                     │ 3  Embedder (OpenAI embeddings)   │
                                     │ 4  VectorStore.add() (Chroma DB)  │
                                     └───────────────────────────────────┘
                         ▲              ▲
                         │ builds       │ required
                         │              │
                         │              └──▶ 📇 FileManifest (path, sha256, mtime, size)
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
````

*Notes:* **ConversationMemory** is a **controller-side, read-only** source exposed to A2 and PromptBuilder; ❖ FILES and authority order remain decisive. External replies are ingested via UI-08/09 with `source=external`. **❖ FILES** remain authoritative over history.

---

## Ingestion & Memory

**DocumentLoader** discovers files under `data/doc_raw/`.
• Current: `.txt`, `.md`, `.json`, `.yml`.

**FileManifest is Must:** per-file ledger `{path, sha256, mtime, size}` for deterministic inclusion/versioning. Hash (`sha256`) is computed on file bytes; unchanged files are skipped deterministically; manifest is published via atomic swap.

**Chunker**: overlapping windows (configurable; default ≈500 chars with overlap ≈100; deterministic boundaries).

**Embedder**: OpenAI embeddings (default `text-embedding-3-large`), batch API, returns 1536-D vectors.

**VectorStore**: **Chroma persistent on-disk DB** via `PersistentClient` under `data/chroma_db/<project>/` (per-project isolation).
• Upsert/query by ID and metadata.
• Chunk IDs are stable: `"{rel_path}::{sha256}::{chunk_idx}"`.
• Metadata saved per chunk: `{"path", "sha256", "chunk_idx", "mtime"}`.
• Deletion uses metadata filters (e.g., old versions by `{path AND sha256}`); file-level tombstones optional.
• `snapshot()` creates filesystem snapshots of the DB directory.

**IngestionManager**: Orchestrates `scan → diff → chunk → embed → add → publish`.
• Processes only `to_process` files (new/changed by hash).
• Optionally deletes **old versions** for the same `path` (different `sha256`).
• Emits `IngestionStats` (files scanned, to_process, unchanged, tombstones, chunks_added, vectors_upserted, deleted_old_versions, deleted_tombstones, published_manifest_path, **embedded_bytes**).

### Conversation Memory (read-only; two-layer, soft fading)

**Purpose.** Maintain flow/coherence without re-chunking chat; history is durable; Layer-E embeddings are **selection-only** and kept **separate** from document vectors. The Layer-E semantic index is used **only to score episodic turns for inclusion (never to populate `S_ctx`).**

**Layers.**
**G — Recency window (configurable k).**
**E — Episodic store (older turns + metadata: turn distance, Δt, tags, importance, source, version hints).** Soft fading and token budgets apply; duplicates vs ❖ FILES are suppressed; ❖ FILES > newer > older.

*(Implementation of G/E is planned; document ingestion is complete.)*

---

## Retrieval & Agent Stages

### A0 — FileScopeSelector

**What:** Deterministic pre-filter that computes the Eligibility Pool from FileManifest, ON/OFF, and ❖ FILES; no embeddings; emits reason-trace.

Outputs (envelope): eligible_files[{path, sha256, mtime, reason[]}], candidate_files_block{files[]}, trace[{path, decision, reason[]}]; failure codes: EMPTY_ELIGIBILITY, LOCK_MISS (escalate=true).

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

**Authority order (fixed):** [Hard Rules] → [Project Memory] → [❖ FILES] → [S_ctx] → [Task/Mode].
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

**Determinism (SR2-JSON-02).** Envelope keys are stable; each agent’s `payload` schema is documented; float scores use fixed precision; no free-text handoffs (prose lives inside typed fields in `payload`).

**Provenance & Hashing (SR2-JSON-03).** Referenced files include `path+hash+mtime`; history items include `id/hash`; the controller may attach a content hash of `payload` for traceability.

**Transport & Storage (SR2-JSON-04).** JSON flows are in-process; for debugging, the **Debug Logger** may write envelopes to disk (trace/vars), but envelopes remain the system of record for inter-agent data.

**Validation (SR2-JSON-05).** Controller validates required envelope fields before dispatch; on missing/invalid fields, set `escalate=true` with reason and halt (Human-in-the-Loop).

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

Vectors persist as **Chroma on-disk collections** (`data/chroma_db/<project>/`), managed by `PersistentClient` (no telemetry). `snapshot()` provides filesystem-level backups. **ConversationMemory** persists JSONL in `conversation.jsonl` and publishes Layer-E snapshots via atomic swap (selection-only). The system remains modular to enable future model or store swaps without touching UI/controller surfaces.

---

## Non-Functional Targets (mirror)

| Category         | Target                                                                                                                                                        |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Determinism      | Fixed orchestration; at most one A2 audit; at most one retrieval re-run per query.                                                                            |
| Latency          | Prompt→first token < 3 s p95 with ~1M-token vector snapshot (CPU-only acceptable).                                                                            |
| Memory footprint | ≤ 6 GB peak; embeddings loaded on demand.                                                                                                                     |
| Privacy/Locality | Personal, single-user workflow; **no telemetry**; **ConversationMemory persists locally** (Layer-G log + Layer-E store); **Debug Logger is user-controlled**. |
| Extensibility    | Add a new agent or embedding model without touching > 1 file.                                                                                                 |

## Technology Stack (updated)

| Layer           | Library / Service               | Version (Oct 2025) |
| --------------- | ------------------------------- | ------------------ |
| GUI             | Streamlit                       | 1.38               |
| Embeddings      | OpenAI `text-embedding-3-large` | openai >= 1.15     |
| Vector Store    | **Chroma (persistent on-disk)** | 0.10               |
| Reranker        | (configurable)                  | —                  |
| LLM API         | OpenAI                          | GPT-4o class       |
| Local LLM (opt) | Ollama                          | 0.2                |

## Directory / Module Tree (updated)

```
.
├── data/
│   ├── chroma_db/
│   │   └── <project>/           # per-project Chroma DB (e.g., project1/)
│   └── doc_raw/
│       └── <project>/           # raw documents per project
├── ragstream/
│   ├── ingestion/
│   │   ├── loader.py
│   │   ├── chunker.py
│   │   ├── embedder.py
│   │   ├── chroma_vector_store_base.py
│   │   ├── vector_store_chroma.py
│   │   ├── file_manifest.py
│   │   └── ingestion_manager.py
│   ├── retrieval/
│   │   ├── retriever.py
│   │   └── reranker.py
│   ├── orchestration/
│   │   ├── prompt_builder.py
│   │   └── llm_client.py
│   ├── app/
│   │   ├── controller.py
│   │   ├── ui_streamlit.py
│   │   └── agents/
│   │       ├── a1_dci.py
│   │       ├── a2_prompt_shaper.py
│   │       ├── a3_nli_gate.py
│   │       └── a4_condenser.py
│   └── memory/
│       └── conversation_memory.py   # read-only views for G/E (planned)
```

---

# Sync Report (this update)

**Precisely applied changes (minimal edits only):**

* In the Ingestion Pipeline diagram, replaced “VectorStore.add() (NumPy .pkl)” with **“VectorStore.add() (Chroma DB)”** and “Embedder (OpenAI embeddings)”.
* In **Ingestion & Memory**, updated:

  * `FileManifest` fields to `{path, sha256, mtime, size}` and atomic publish.
  * `Embedder` to OpenAI (`text-embedding-3-large`).
  * `VectorStore` to **Chroma persistent on-disk DB** with per-project directories, stable IDs, metadata, deletion by metadata, and `snapshot()`.
  * Added `IngestionManager` orchestration and `IngestionStats.embedded_bytes`.
* In **Persistence & Modularity**, set vectors to persist as **Chroma collections**.
* In **Technology Stack**, set Vector Store to **Chroma (current)**; embeddings to OpenAI.
* In **Directory / Module Tree**, added `chroma_vector_store_base.py`, `vector_store_chroma.py`, `file_manifest.py`, and `ingestion_manager.py`; added `data/chroma_db/<project>/`.

**Compatibility confirmation:** This `Architecture_2.md` matches `PlanetextUML.txt` (full UML) and the Python modules now implemented.

```
::contentReference[oaicite:0]{index=0}
```
