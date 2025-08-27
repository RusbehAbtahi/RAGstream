# RAGstream — Comprehensive Requirements Specification (Updated)

*Version 2.0 • 2025-08-27*
*This document supersedes v1.0 and integrates the decisions from “HistoryManagementandSafty.md” and our latest design discussion. It removes internal Tooling, adds Conversation History Management, and formalizes the A2 audit model while keeping the overall architecture intact.* &#x20;

---

## 1  Purpose & Scope

RAGstream is a personal, production-grade, local-first RAG workbench for a single expert user. Its mission is to deliver superior, deterministic prompt/context orchestration compared with generic chat UIs by combining: deterministic file inclusion (Exact File Lock), high-quality retrieval with semantic gating and condensation, explicit authority ordering, and now explicit Conversation History Management with fading. It remains modular to allow future integration with the AWS TinnyLlama Cloud project. “MVP” and end-user automation concepts do not apply here.&#x20;

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
                   │          ├──▶ A1 DCI → ❖ FILES (Exact Lock / FULL / PACK)
                   │          ├──▶ (if not locked) Retriever → Reranker → A3 NLI Gate → A4 Condenser (S_ctx)
                   │          ├──▶ A2 Prompt Shaper (audit-2) on S_ctx → header/role refinements
                   │          ├──▶ PromptBuilder (authority order)
                   │          ├──▶ ConversationMemory (read-only: recency window + pinned summary)
                   │          ├──▶ LLMClient (OpenAI or local)
                   │          └──▶ Transparency (kept/dropped reasons; no persistent logs)
DocumentLoader ◀───┘
     ▲
     └─ Chunker ─ Embedder ─ VectorStore.add() (.pkl snapshots; Chroma paused)
```

Notes:
• ConversationMemory is a new read-only source feeding A2 and (optionally) PromptBuilder; A1–A4 interfaces remain unchanged.&#x20;
• Tooling has been removed from scope (no ToolDispatcher/Math/Py).&#x20;

---

## 4  Functional Requirements

### 4.1  Ingestion / Knowledge Store

| ID     | Requirement                                                                            | Priority |
| ------ | -------------------------------------------------------------------------------------- | -------- |
| ING-01 | Load `.txt`, `.md`, `.json`, `.yml`.                                                   | Must     |
| ING-02 | Persist vectors as NumPy `.pkl` snapshots.                                             | Must     |
| ING-03 | Recursive splitter (target \~1 024 tokens, overlap \~200).                             | Must     |
| ING-04 | Planned: Chroma on-disk collection once environment allows (unchanged).                | Planned  |
| ING-05 | Planned: FileManifest with `path`, `sha`, `mtime`, `type` for deterministic inclusion. | Planned  |
| ING-06 | Ingestion log UI messages may be shown ephemerally; no persistent logs are stored.     | Must     |

(ING items are preserved where compatible; only log persistence expectations are clarified per personal-use constraints.)&#x20;

---

### 4.2  Conversation History Management (Two-Layer Model)

**Purpose:** Maintain flow and coherence without re-chunking history, using a small always-present recency window plus a selective episodic layer with fading. (New section replacing the previous implicit omission.)&#x20;

#### Layers & Data

| ID    | Requirement                                                                                                                                                         | Priority |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| CH-01 | Provide Layer-G (recency window): always include the last k user–assistant turns verbatim (k≈3–5; configurable).                                                    | Must     |
| CH-02 | Provide Layer-E (episodic store): older turns with metadata (turn distance, optional Δt, tags, importance flag, source, version hints). Selection is on-topic only. | Must     |
| CH-03 | Never vectorize or re-chunk history for retrieval; history is not part of the document store.                                                                       | Must     |
| CH-04 | Soft fading: prefer nearer/important items; allow older items if clearly on-topic or important.                                                                     | Must     |
| CH-05 | Importance control: manual “mark important” and gentle auto-promotion when items are reused often.                                                                  | Should   |
| CH-06 | Deduplicate vs ❖ FILES: if A1 injects a file, drop chat fragments that duplicate or conflict with that file for this turn.                                          | Must     |
| CH-07 | Conflict policy: explicit ❖ FILES wins this turn; otherwise prefer newer items; surface conflicts in transparency UI.                                               | Must     |
| CH-08 | Compression: very old spans may be rolled into compact, titled summaries; recent window is never summarized.                                                        | Should   |
| CH-09 | Token budget first: include fewer, higher-value items; apply smooth keep/drop, not jumpy thresholds.                                                                | Must     |
| CH-10 | Optional real-time damping: if there’s a long gap between sessions, slightly reduce freshness scores of very old items.                                             | Could    |
| CH-11 | Exposure: A2 (pass-1) and A2 (audit-2) read Layer-G and eligible Layer-E items; PromptBuilder may include a brief “RECENT HISTORY” block when useful.               | Must     |

(Requirements CH-01..CH-11 consolidate the “Layers at a Glance,” metadata, selection, de-duplication, conflict handling, compression, and acceptance-style expectations from the History document.)&#x20;

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
| RET-07 | Transparency view shows kept/dropped with reasons (ephemeral; no persistent logs).       | Must     |

(Identical to earlier functional core, with language tightened for personal use and no logs.)&#x20;

---

### 4.4  Prompt Orchestration & A2 Audit Model

| ID     | Requirement                                                                                                                                                                                                   | Priority |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| ORC-01 | PromptBuilder composes the final prompt with fixed authority order: \[Hard Rules] → \[Project Memory] → \[❖ FILES] → \[S\_ctx] → \[Task/Mode].                                                                | Must     |
| ORC-02 | A2 runs **twice at most** per query: (pass-1) before retrieval using {user prompt + Project Memory + Layer-G + eligible Layer-E}; (audit-2) after A4, using {S\_ctx + same anchors}, to refine headers/roles. | Must     |
| ORC-03 | A2 (audit-2) cannot override Hard Rules, Project Memory, or Exact File Lock; it may adjust tone, audience, depth, and output format; it may change intent/domain **only if** justified by S\_ctx.             | Must     |
| ORC-04 | Retrieval re-run rule: if A2 (audit-2) changes the **task scope** (intent/domain) materially, allow **one** retrieval → A3 → A4 re-run; otherwise reuse the existing S\_ctx.                                  | Must     |
| ORC-05 | Schema validation: A4 output must validate against the `Facts / Constraints / Open Issues` schema; on validation failure, apply fallback (see 4.6).                                                           | Must     |

(ORC items formalize the single controlled A2 audit pass and retrieval re-run gate, aligning with our design and the “Missing Safety Elements” need for schema validation.)&#x20;

---

### 4.5  Safety: Guardrails, Brakes, Airbags

These requirements bring in the explicitly missing safety elements while respecting the personal, no-logs scope.&#x20;

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

| ID    | Requirement                                                                                                              | Priority |
| ----- | ------------------------------------------------------------------------------------------------------------------------ | -------- |
| UI-01 | Prompt box, ON/OFF eligibility per file, Exact File Lock toggle, Prompt Shaper panel, agent toggles, model picker.       | Must     |
| UI-02 | Super-Prompt preview (editable before send).                                                                             | Must     |
| UI-03 | Transparency view of kept/dropped with reasons (ephemeral; no persisted logs).                                           | Must     |
| UI-04 | Show ❖ FILES and `S_ctx` exactly as composed.                                                                            | Must     |
| UI-05 | Cost estimator visible pre-send; enforce token/cost ceiling (SAF-G3).                                                    | Must     |
| UI-06 | Optional “RECENT HISTORY” block visibility and controls: k for Layer-G; token budget for Layer-E; mark-important toggle. | Should   |
| UI-07 | Optional export of the current answer with citations (on-demand; no background automation).                              | Could    |

(Reminder: no persistent logs, no end-user automation; exports are explicit, on-demand actions.)

---

## 5  Non-Functional Requirements

| Category          | Target                                                                                               |
| ----------------- | ---------------------------------------------------------------------------------------------------- |
| Determinism       | Fixed orchestration; at most one A2 audit; at most one retrieval re-run per query.                   |
| Latency           | Prompt→first token < 3 s p95 with \~1M-token vector snapshot (CPU-only acceptable).                  |
| Memory footprint  | ≤ 6 GB peak; embeddings loaded on demand.                                                            |
| Privacy/Locality  | Personal, single-user workflow; no telemetry; no persistent logs.                                    |
| Modularity        | Clean boundaries: A1–A4, Retriever/Reranker, PromptBuilder, ConversationMemory, LLMClient.           |
| Integration Ready | Keep interfaces stable for future AWS TinnyLlama Cloud integration (controllers/adapters swappable). |

(Observability/logging and test-coverage NFRs are intentionally **removed** per personal-use constraints; functional quality remains a top priority.)&#x20;

---

## 6  Technology Stack

| Layer        | Library / Service                    | Notes                          |
| ------------ | ------------------------------------ | ------------------------------ |
| GUI          | Streamlit                            | Local desktop use.             |
| Embeddings   | `bge-large-en-v3` or `E5-Mistral`    | Via `sentence_transformers`.   |
| Vector Store | NumPy `.pkl` snapshots               | Chroma paused (planned later). |
| LLM API      | OpenAI (default) or local via Ollama | Pluggable via LLMClient.       |

(Previously listed SymPy, Tooling, Testing/CI entries are removed.)&#x20;

---

## 7  Directory / Module Tree (Informative)

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
│       └── conversation_memory.py   # new module (read-only views for G/E)
```

Note: the former `tooling/` package is removed from requirements scope; if it exists in code, it should be disabled and unused.

---

## 8  Open Issues / Risks

| Risk                           | Mitigation                                                                 |
| ------------------------------ | -------------------------------------------------------------------------- |
| Cross-encoder latency on CPU   | Limit candidates; single pass; cache embeddings where feasible.            |
| History selection bloat        | Enforce token budgets; smooth fading; manual importance pinning.           |
| A2 audit causes scope creep    | Single audit only; retrieval re-run allowed once and only on scope change. |
| Chroma environment instability | Keep `.pkl` snapshots until stable.                                        |

(Updated to match the new history/audit model and removed Tooling/CI/testing risks.)&#x20;

---

## 9  Acceptance Criteria

1. Conversation Memory
   • The last k turns (Layer-G) are always available to A2 and visible in UI if enabled.
   • Layer-E contributes only clearly on-topic or important items; duplicates of ❖ FILES are suppressed.
   • Conflicts are resolved by authority and freshness (❖ FILES > newer > older) and surfaced in transparency.&#x20;

2. Orchestration & Audit
   • A2 runs at most twice; audit-2 can refine headers/roles and may change scope only if supported by S\_ctx.
   • If scope changes, exactly one retrieval→A3→A4 re-run occurs; otherwise S\_ctx is reused.
   • PromptBuilder applies the fixed authority order precisely.&#x20;

3. Safety
   • A4 output always validates against the `Facts / Constraints / Open Issues` schema or triggers SAF-A1 fallback.
   • Controller timeouts, global cancellation, and cost/token ceilings function as defined.&#x20;

4. UI
   • Super-Prompt preview shows ❖ FILES and S\_ctx exactly; transparency view explains kept/dropped (no persisted logs).
   • Cost estimator prevents over-budget sends via hard stop.&#x20;

---

## 10  Glossary (Updated)

| Term               | Meaning                                                                    |
| ------------------ | -------------------------------------------------------------------------- |
| ConversationMemory | Read-only provider of Layer-G (recency window) and Layer-E (episodic).     |
| Layer-G            | Always-keep recency window of last k turns.                                |
| Layer-E            | Episodic store of older turns with metadata and fading.                    |
| ❖ FILES            | Deterministically injected files by A1; canonical for that turn.           |
| S\_ctx             | Cited, condensed context emitted by A4 (Facts/Constraints/Open Issues).    |
| A2 audit           | Second, controlled pass of A2 after A4 to refine headers/roles.            |
| Authority order    | \[Hard Rules] → \[Project Memory] → \[❖ FILES] → \[S\_ctx] → \[Task/Mode]. |

---

### Change Log (relative to v1.0)

• Added: Conversation History Management (4.2) with two-layer model and fading.&#x20;
• Added: A2 audit model, retrieval re-run rule, and A4 schema validation.&#x20;
• Added: Safety requirements (guardrails, brakes, airbags).&#x20;
• Removed: Internal Tooling and all associated requirements and stack entries.&#x20;
• Removed: MVP language, persistent logs, pytest/testing/CI mentions.&#x20;

---

