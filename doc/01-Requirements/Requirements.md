# RAGstream — Comprehensive Requirements Specification (Updated)

*Version 2.3 • 2025-08-29*
*This document supersedes v2.2 and integrates (a) **Feature-1: Conversation History Persistence & Async Layer-E Embedding** and (b) **Feature-2: Debug Logger**, while preserving structure and all prior requirements. It maintains the selection-only Layer-E semantic index, external-reply import, bounded A2 audit, and personal-use scope.*

---

## 1  Purpose & Scope

RAGstream is a personal, production-grade, local-first RAG workbench for a single expert user. Its mission is to deliver superior, deterministic prompt/context orchestration compared with generic chat UIs by combining: deterministic file inclusion (Exact File Lock), high-quality retrieval with semantic gating and condensation, explicit authority ordering, and explicit Conversation History Management with fading. It remains modular to allow future integration with the AWS TinnyLlama Cloud project. “MVP” and end-user automation concepts do not apply here.

---

## 2  Stakeholders

| Role                | Interest                                                                 |
| ------------------- | ------------------------------------------------------------------------ |
| Owner (single user) | Precise, deterministic orchestration; fast iteration; personal workflow. |
| Future integrator   | Clean interfaces for later AWS TinnyLlama Cloud integration.             |

(Previously listed “future OSS users,” “data engineer,” and demo-oriented stakeholders are out of scope for this personal system.)

---

## 3  System Context

```
User ──▶ Streamlit GUI ──▶ Controller
                   ▲          │
                   │          ├──▶ A2 Prompt Shaper (pass-1) → advisory headers
                   │          ├──▶ A1 DCI → ❖ FILES (Exact File Lock / FULL / PACK)
                   │          ├──▶ (if not locked) Retriever → Reranker → A3 NLI Gate → A4 Condenser (S_ctx)
                   │          ├──▶ A2 Prompt Shaper (audit-2) on S_ctx → header/role refinements
                   │          ├──▶ PromptBuilder (authority order)
                   │          ├──▶ ConversationMemory (read-only: Layer-G recency + Layer-E episodic selection)
                   │          ├──▶ LLMClient (OpenAI or local)
                   │          └──▶ Transparency (kept/dropped reasons)
DocumentLoader ◀───┘
     ▲
     └─ Chunker ─ Embedder ─ VectorStore.add() (.pkl snapshots; Chroma paused)
```

Notes:
• ConversationMemory is a read-only source feeding A2 and (optionally) PromptBuilder; A1–A4 interfaces remain unchanged.
• Tooling remains out of scope (no ToolDispatcher/Math/Py).

---

## 4  Functional Requirements

### 4.1  Ingestion / Knowledge Store

| ID     | Requirement                                                                                              | Priority |
| ------ | -------------------------------------------------------------------------------------------------------- | -------- |
| ING-01 | Load `.txt`, `.md`, `.json`, `.yml`.                                                                     | Must     |
| ING-02 | Persist vectors as NumPy `.pkl` snapshots.                                                               | Must     |
| ING-03 | Recursive splitter (target \~1 024 tokens, overlap \~200).                                               | Must     |
| ING-04 | Planned: Chroma on-disk collection once environment allows (unchanged).                                  | Planned  |
| ING-05 | **FileManifest with `path`, `sha256` (or MD5), `mtime`, `type` for deterministic inclusion/versioning.** | **Must** |
| ING-06 | Ingestion UI messages may be shown; ingestion events MAY be persisted via Debug Logger per Feature-2.    | Must     |

---

### 4.2  Conversation History Management (Two-Layer Model)

**Purpose:** Maintain flow and coherence without re-chunking history, using a small always-present recency window plus a selective episodic layer with fading.

#### Layers & Data

| ID        | Requirement                                                                                                                                                                                                                                                            | Priority |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| CH-01     | Provide **Layer-G (recency window)**: always include the last k user–assistant turns verbatim (k≈3–5; configurable).                                                                                                                                                   | Must     |
| CH-02     | Provide **Layer-E (episodic store)**: older turns with metadata (turn distance, optional Δt, tags, importance flag, source, version hints). Selection is on-topic only.                                                                                                | Must     |
| CH-03     | **Permit a small, append-only *Layer-E semantic index* (embeddings) used *only to score episodic turns for selection*.** History is kept **separate** from the document store and is **never** used directly for retrieval into `S_ctx`. No retro re-chunking of chat. | **Must** |
| CH-04     | Soft fading: prefer nearer/important items; allow older items if clearly on-topic or important.                                                                                                                                                                        | Must     |
| CH-05     | Importance control: manual “mark important” and gentle auto-promotion when items are reused often.                                                                                                                                                                     | Should   |
| CH-06     | Deduplicate vs ❖ FILES: if A1 injects a file, drop chat fragments that duplicate or conflict with that file for this turn.                                                                                                                                             | Must     |
| CH-07     | Conflict policy: explicit ❖ FILES wins this turn; otherwise prefer newer items; surface conflicts in transparency UI.                                                                                                                                                  | Must     |
| CH-08     | Compression: very old spans may be rolled into compact, titled summaries; recent window is never summarized.                                                                                                                                                           | Should   |
| CH-09     | Token budget first: include fewer, higher-value items; apply smooth keep/drop, not jumpy thresholds.                                                                                                                                                                   | Must     |
| CH-10     | Optional real-time damping: if there’s a long gap between sessions, slightly reduce freshness scores of very old items.                                                                                                                                                | Could    |
| CH-11     | Exposure: A2 (pass-1) and A2 (audit-2) read Layer-G and eligible Layer-E items; PromptBuilder may include a brief “RECENT HISTORY” block when useful.                                                                                                                  | Must     |
| **CH-12** | **External replies import:** the UI can append pasted external replies to ConversationMemory with `source=external`, timestamp, and optional hash; such items participate in Layer-E selection and dedup rules.                                                        | **Must** |

**CH-03.x Guardrails (selection-only embeddings for Layer-E)**

* **CH-03.1 (Scope)** — Layer-E embeddings are **selection-only** and **never** populate `S_ctx` or the ❖ FILES block.
* **CH-03.2 (Capacity/Budget)** — Hard cap on history vectors; token budgets for G/E; decay by turn-distance/time; evict lowest-importance first.
* **CH-03.3 (Signal Fusion)** — Selection score combines **embeddings + acronym/synonym lexicon** (e.g., *NVH ⇄ vehicle acoustics*) + **recency** + **importance**.
* **CH-03.4 (Authority & Dedup)** — Preserve ❖ FILES > newer > older; A3 suppresses chat duplicates when A1 injects a file.
* **CH-03.5 (Integrity/Versioning)** — FileManifest hashes/mtime are authoritative; each ConversationMemory item carries source + hash/version hints for deterministic conflict resolution.
* **CH-03.6 (Determinism)** — Keep “one A2 audit + at most one retrieval re-run on *material scope change*”; Layer-E indexing **must not** introduce additional loops.
* **CH-03.7 (UI/Controls)** — Expose `k` (G size), Layer-E token budget, synonym list import, and transparent keep/drop reasons.
* **CH-03.8 (Acceptance)** — Functional checks include: NVH⇄vehicle acoustics recalled from Layer-E; chat update can beat stale file until re-ingestion; Exact Lock short-circuits Layer-E selection; every Fact in `S_ctx` has at least one citation.
* **CH-03.9 (Eligibility alignment)** — If a file is **OFF** in the Eligibility Pool for this turn, **Layer-E selection MUST ignore** history items whose source/version hints point to that file (path/hash/mtime), **unless** the file is explicitly injected via **❖ FILES**.
* **CH-03.10 (Durable history, not logs)** — **Persist** ConversationMemory state:
  – **Text log**: append-only `PATHS.logs/conversation.log`; after each user+assistant turn, synchronously append both lines and flush+fsync before the next prompt is accepted.
  – **Layer-G** is reconstructed from the tail of `conversation.log` per prompt (no RAM-only history).
  – **Layer-E index**: separate NumPy snapshot (e.g., `history_store.pkl`) used **only** for selection; lives **separate** from document vectors; capacity/eviction per CH-03.2.
  – If persistence fails, continue in-memory and surface a notice; determinism and bounded audit rules remain unchanged. **(Must)**

---

### 4.3  Retrieval & Agents

| ID     | Requirement                                                                              | Priority |
| ------ | ---------------------------------------------------------------------------------------- | -------- |
| RET-01 | Cosine top-k search (k≈20) with the configured embedder.                                 | Must     |
| RET-02 | Cross-encoder rerank (e.g., `mxbai-rerank-xsmall-v1`).                                   | Must     |
| RET-03 | Eligibility Pool: ON/OFF per file to bound retrieval.                                    | Must     |
| RET-04 | Exact File Lock: when ON, retrieval is skipped; only ❖ FILES are injected.               | Must     |
| RET-05 | A3 NLI Gate drops non-entailed/contradictory candidates with strictness θ.               | Must     |
| RET-06 | A4 Condenser emits cited `S_ctx` with three sections: Facts / Constraints / Open Issues. | Must     |
| RET-07 | Transparency view shows kept/dropped with reasons.                                       | Must     |

---

### 4.4  Prompt Orchestration & A2 Audit Model

| ID       | Requirement                                                                                                                                                                                                                                              | Priority |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| ORC-01   | PromptBuilder composes the final prompt with fixed authority order: \[Hard Rules] → \[Project Memory] → \[❖ FILES] → \[S\_ctx] → \[Task/Mode].                                                                                                           | Must     |
| ORC-02   | A2 runs **twice at most** per query: (pass-1) before retrieval using {user prompt + Project Memory + Layer-G + eligible Layer-E}; (audit-2) after A4, using {S\_ctx + same anchors}, to refine headers/roles.                                            | Must     |
| ORC-03   | A2 (audit-2) cannot override Hard Rules, Project Memory, or Exact File Lock; it may adjust tone, audience, depth, and output format; it may change intent/domain **only if** justified by S\_ctx.                                                        | Must     |
| ORC-04   | Retrieval re-run rule: if A2 (audit-2) changes the **task scope** (intent/domain) materially, allow **one** retrieval → A3 → A4 re-run; otherwise reuse the existing S\_ctx.                                                                             | Must     |
| ORC-04.1 | **Material scope change rubric (permits the one re-run):** change of **intent/domain**, or **target artifact set** (files/components) that affects retrieval eligibility, or **deliverable type**. Pure tone/audience/format changes **do not** qualify. | **Must** |
| ORC-05   | Schema validation: A4 output must validate against the `Facts / Constraints / Open Issues` schema; on validation failure, apply fallback (see 4.6).                                                                                                      | Must     |

---

### 4.5  Safety: Guardrails, Brakes, Airbags

These requirements bring in the explicitly missing safety elements while respecting the personal scope.

#### Guardrails (Policy / Boundaries)

| ID     | Requirement                                                                                                              | Priority |
| ------ | ------------------------------------------------------------------------------------------------------------------------ | -------- |
| SAF-G1 | Prompt-injection checks on retrieved text: strip/neutralize instructions that attempt to subvert rules.                  | Must     |
| SAF-G2 | Enforce A4 schema validation (see ORC-05).                                                                               | Must     |
| SAF-G3 | Prompt size/cost hard stop: refuse composition if estimated tokens exceed configured ceiling; surface a clear UI reason. | Must     |

#### Brakes (Timeouts / Cancellation)

| ID     | Requirement                                                                                                               | Priority |
| ------ | ------------------------------------------------------------------------------------------------------------------------- | -------- |
| SAF-B1 | Controller-level timeouts for retrieval, rerank, A3, and A4; if any stage exceeds limit, cancel stage and apply fallback. | Must     |
| SAF-B2 | Global cancellation: any stalled agent can be aborted cleanly; user can retry with adjusted settings.                     | Must     |

#### Airbags (Fallbacks / Graceful Degradation)

| ID     | Requirement                                                                                                               | Priority |
| ------ | ------------------------------------------------------------------------------------------------------------------------- | -------- |
| SAF-A1 | If A4 fails or its schema validation fails → fallback to showing top reranked, NLI-kept chunks with citations.            | Must     |
| SAF-A2 | If retrieval fails → proceed with ❖ FILES-only path.                                                                      | Must     |
| SAF-A3 | If LLM call fails → retry with a smaller/cheaper compatible model once; if still failing, surface reason to user.         | Must     |
| SAF-A4 | Optional rollback: if A2 (audit-2) changed scope and the re-run produced empty/invalid S\_ctx, revert to previous S\_ctx. | Should   |

---

### 4.6  UI / App

| ID        | Requirement                                                                                                                                                                       | Priority |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| UI-01     | Prompt box, ON/OFF eligibility per file, Exact File Lock toggle, Prompt Shaper panel, agent toggles, model picker.                                                                | Must     |
| UI-02     | Super-Prompt preview (editable before send).                                                                                                                                      | Must     |
| UI-03     | Transparency view of kept/dropped with reasons.                                                                                                                                   | Must     |
| UI-04     | Show ❖ FILES and `S_ctx` exactly as composed.                                                                                                                                     | Must     |
| UI-05     | Cost estimator visible pre-send; enforce token/cost ceiling (SAF-G3).                                                                                                             | Must     |
| UI-06     | Optional “RECENT HISTORY” visibility and controls: k for Layer-G; token budget for Layer-E; mark-important toggle.                                                                | Should   |
| UI-07     | Optional export of the current answer with citations (on-demand; no background automation).                                                                                       | Could    |
| **UI-08** | **External Reply textbox**: paste an external LLM reply prior to import.                                                                                                          | **Must** |
| **UI-09** | **Send to History** button: appends the pasted external reply into ConversationMemory with `source=external`.                                                                     | **Must** |
| **UI-10** | **Per-file ON/OFF checkboxes** populate the **Eligibility Pool**; when **OFF**, all chunks/MD5s of that file are excluded from retrieval → rerank → A3 → A4 for the current turn. | **Must** |
| **UI-11** | **Persist History (Layer-E) toggle** ON/OFF (default **ON**). When OFF, keep Layer-E in-memory for this run only; do not write to disk.                                           | **Must** |
| **UI-12** | **Clear History** control: on confirmation, purge the persisted Layer-E store (keeps Layer-G in-memory).                                                                          | **Must** |

---

### 4.7  Debug Logger (Feature-2)

A deterministic, optional logger for developer debugging; separate from ConversationMemory.

| ID     | Requirement                                                                                                                                                 | Priority |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| LOG-01 | On GUI start, open new session logs under `PATHS.logs/` with a common stem and timestamp: `debug_trace_YYYYmmdd-HHMMSS_sessNN.log` and `debug_vars_…`.      | Must     |
| LOG-02 | `logWriteText(msg, level="INFO")` appends `[ts] [LEVEL] msg` to `debug_trace`; if `vars_enabled=True` it is mirrored to `debug_vars`.                       | Must     |
| LOG-03 | `logWriteVar(name1, value1, …)` always writes an explanation line to `debug_trace`; if `vars_enabled=True`, writes names+values to `debug_vars`.            | Must     |
| LOG-04 | **Truncation:** default max 200 chars/items; per-variable override by passing `(name, maxlen)`; truncated dumps include an ellipsis and length metadata.    | Must     |
| LOG-05 | **Levels:** support at least `INFO` and `DEBUG`; a `min_level` setting drops lower-priority lines before enqueue.                                           | Must     |
| LOG-06 | **Rotation:** append-only by default; optional rollover when file size > N MB (rotate `.1`…`.K`) using atomic replace; continue in new base files.          | Should   |
| LOG-07 | **Serialization:** dict/list to safe JSON-like form; large/numpy/pandas/torch objects show type, shape/len, and truncated preview; others use `repr()`.     | Must     |
| LOG-08 | **Crash-survivability:** flush + `fsync()` per line in the writer; logs remain readable after a crash; when `vars_enabled=False`, **no** `debug_vars` file. | Must     |

(These logs are optional developer aids; they do not feed retrieval or history selection and are distinct from transparency UI.)

---

## 5  Non-Functional Requirements

| Category         | Target                                                                                                                                                        |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Determinism      | Fixed orchestration; at most one A2 audit; at most one retrieval re-run per query.                                                                            |
| Latency          | Prompt→first token < 3 s p95 with \~1M-token vector snapshot (CPU-only acceptable).                                                                           |
| Memory footprint | ≤ 6 GB peak; embeddings loaded on demand.                                                                                                                     |
| Privacy/Locality | Personal, single-user workflow; **no telemetry**; **ConversationMemory persists locally** (Layer-G log + Layer-E store); **Debug Logger is user-controlled**. |
| Extensibility    | Add a new agent or embedding model without touching > 1 file.                                                                                                 |

---

## 6  Technology Stack

| Layer           | Library / Service                          | Version (Aug 2025)         |
| --------------- | ------------------------------------------ | -------------------------- |
| GUI             | Streamlit                                  | 1.38                       |
| Embeddings      | `bge-large-en-v3`, `E5-Mistral` (optional) | sentence\_transformers 3.0 |
| Vector Store    | NumPy `.pkl` snapshots (current)           | –                          |
| Planned DB      | Chroma                                     | 0.10                       |
| Cross-encoder   | `mixedbread-ai/mxbai-rerank-xsmall-v1`     | 🤗 cross-encoder 0.6       |
| LLM API         | OpenAI (`openai>=1.15.0`)                  | GPT-4o                     |
| Local LLM (opt) | Ollama                                     | 0.2                        |

---

## 7  Directory / Module Tree

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

(Note: the former `tooling/` package is out of scope; if it exists in code, it should be disabled and unused.)

---

## 8  Open Issues / Risks

| Risk                           | Mitigation                                                                 |
| ------------------------------ | -------------------------------------------------------------------------- |
| Cross-encoder latency on CPU   | Limit candidates; single pass; cache embeddings where feasible.            |
| History selection bloat        | Enforce token budgets; smooth fading; manual importance pinning.           |
| A2 audit causes scope creep    | Single audit only; retrieval re-run allowed once and only on scope change. |
| Chroma environment instability | Keep `.pkl` snapshots until stable.                                        |

---

## 9  Acceptance Criteria

1. **Conversation Memory**
   • The last k turns (Layer-G) are always available to A2 and visible in UI if enabled.
   • Layer-E contributes only clearly on-topic or important items; duplicates of ❖ FILES are suppressed.
   • Conflicts resolved by authority and freshness (**❖ FILES > newer > older**).
   • **Semantic aliasing** examples (e.g., **NVH ⇄ vehicle acoustics**) are recalled via Layer-E selection.
   • **External replies** imported via UI-09 are stored with `source=external` and participate in selection/dedup.
   • **Persistence:** after each turn, `conversation.log` contains both sides and is fsynced; on restart, Layer-G rebuilds from log tail; Layer-E loads from the last published snapshot (or backfills).

2. **Orchestration & Audit**
   • A2 runs at most twice; audit-2 can refine headers/roles and may change scope only if supported by S\_ctx.
   • If scope changes, exactly one retrieval→A3→A4 re-run occurs; otherwise S\_ctx is reused.
   • PromptBuilder applies the fixed authority order precisely.

3. **Safety**
   • A4 output always validates against the `Facts / Constraints / Open Issues` schema or triggers SAF-A1 fallback.
   • Controller timeouts, global cancellation, and cost/token ceilings function as defined.
   • **Every Fact in `S_ctx` has at least one citation.**

4. **UI**
   • Super-Prompt preview shows ❖ FILES and S\_ctx exactly; transparency view explains kept/dropped.
   • Cost estimator prevents over-budget sends via hard stop.
   • UI exposes `k`, Layer-E budget, and synonym import; UI-08/UI-09 enable manual external-reply import; UI-10 enforces eligibility; UI-11/12 manage history persistence.

---

## 10  Glossary (Updated)

| Term               | Meaning                                                                                   |
| ------------------ | ----------------------------------------------------------------------------------------- |
| ConversationMemory | Read-only provider of Layer-G (recency window) and Layer-E (episodic).                    |
| Layer-G            | Always-keep recency window of last k turns.                                               |
| Layer-E            | Episodic store of older turns with metadata and fading.                                   |
| ❖ FILES            | Deterministically injected files by A1; canonical for that turn.                          |
| S\_ctx             | Cited, condensed context emitted by A4 (Facts/Constraints/Open Issues).                   |
| A2 audit           | Second, controlled pass of A2 after A4 to refine headers/roles.                           |
| Authority order    | \[Hard Rules] → \[Project Memory] → \[❖ FILES] → \[S\_ctx] → \[Task/Mode].                |
| Eligibility Pool   | Set of files currently ON for retrieval; populated by UI-10.                              |
| Debug Logger       | Optional per-session trace/vars logs under `PATHS.logs/`; not used for retrieval/history. |

---

### Change Log (edits to remove anti-logging language; FileManifest status)

* **§3 System Context** — removed “ephemeral” qualifier from “Transparency (kept/dropped reasons)”.
* **ING-06** — changed to allow persistence via Debug Logger (“…MAY be persisted via Debug Logger per Feature-2”).
* **RET-07** — removed “(ephemeral; no persistent logs)”.
* **UI-03** — removed “(ephemeral; no persisted logs)”.
* **§5 Non-Functional (Privacy/Locality row)** — clarified: “no telemetry; ConversationMemory persists locally; Debug Logger is user-controlled.”
* **§9 Acceptance → UI bullet** — removed “(no persisted logs)”.
* **ING-05** — confirmed **Must** (sha256/MD5 + mtime) and ensured no other table lists it as “Planned.”
