Here is the full, updated `Requirements.md` with **supp2** merged as strictly additive edits (no existing lines modified or removed). A short Change Log follows after the file.

---

# RAGstream — Comprehensive Requirements Specification (Updated)

*Version 2.3 • 2025-08-29*
*This document supersedes v2.2 and integrates (a) **Feature-1: Conversation History Persistence & Async Layer-E Embedding**, (b) **Feature-2: Debug Logger**, and prior deltas on external-reply import, bounded A2 audit, and personal-use scope.*

---

## 1  Purpose & Scope

RAGstream is a personal, production-grade, local-first RAG workbench focused on deterministic context construction, auditable selection, and tight control of authority ordering. It is for **single-user expert use**, not a consumer app. Its goal is to outperform generic chat UIs functionally (context discipline, retrieval precision, transparency), while remaining modular for future integration with AWS TinnyLlama Cloud and local models. “MVP” and end-user automation concepts do not apply here.

---

## 2  Stakeholders

| Role               | Interest                                                                    |
| ------------------ | --------------------------------------------------------------------------- |
| System Owner (You) | Deterministic, auditable, production-grade orchestration for personal work. |
| Developer (You)    | Clear, enforceable requirements and crisp architecture boundaries.          |

---

## 3  System Context

```
Local Files (clean .md/.txt only) ──▶ Ingestion ▶ Embedding ▶ Vector Store (NumPy/Chroma)
         ▲                                              │
         │                                              ▼
     A1 ❖ FILES ──▶ PromptBuilder (authority order) ──▶ LLM
         ▲                   ▲                     ▲
         │                   │                     │
   ConversationMemory (read-only: Layer-G recency + Layer-E episodic selection)
   External Reply import (UI-08/UI-09) feeds ConversationMemory with source=external
```

*Notes:*

* **No PDFs/Images/OCR ingestion** inside the app; only pre-verified, clean text is ingested.
* **Authority order** in PromptBuilder is fixed: \[Hard Rules] → \[Project Memory] → \[❖ FILES] → \[S\_ctx] → \[Task/Mode].
* **Exact File Lock** (when enabled) bypasses retrieval; only named ❖ FILES are injected.
* ConversationMemory is **read-only** to agents: Controller exposes a deterministic view (Layer-G recency window, Layer-E selection-only episodic items).

---

## 4  Functional Requirements

### 4.1  Ingestion / Knowledge Store

| ID     | Requirement                                                                                            | Priority |
| ------ | ------------------------------------------------------------------------------------------------------ | -------- |
| ING-01 | Only clean text/markdown files are ingested (no PDFs/Images/OCR).                                      | Must     |
| ING-02 | Chunker is deterministic: fixed chunk size/overlap; no reflow by context.                              | Must     |
| ING-03 | Embedder is pinned (model+params); identical input yields identical vectors.                           | Must     |
| ING-04 | Vector store supports append-only snapshots (.pkl) for NumPy; Chroma optional when environment allows. | Should   |
| ING-05 | **FileManifest** (sha256 or MD5, mtime, path) is maintained and used for authority/conflict decisions. | **Must** |
| ING-06 | Transparency artifacts (kept/dropped reasons) MAY be persisted via Debug Logger (Feature-2).           | Should   |

### 4.2  Conversation History Management (Two-Layer Model)

#### Layers & Data

| ID       | Requirement                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Priority |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| CH-01    | Provide **Layer-G (recency window)**: always include last *k* user/assistant turns verbatim.                                                                                                                                                                                                                                                                                                                                                                                                                        | Must     |
| CH-02    | Provide **Layer-E (episodic store)**: older turns stored with metadata (turn distance, Δt optional, tags, importance, source).                                                                                                                                                                                                                                                                                                                                                                                      | Must     |
| CH-03    | **Permit a small, append-only *Layer-E semantic index*** (embeddings) for **selection-only**; never injects directly into `S_ctx`. No retro re-chunking of chat.                                                                                                                                                                                                                                                                                                                                                    | **Must** |
| CH-03.1  | **Scope**: E-embeddings are used **only** to score episodic candidates for inclusion; never populate `S_ctx`.                                                                                                                                                                                                                                                                                                                                                                                                       | Must     |
| CH-03.2  | **Capacity/Budget**: hard cap vector count; token budgets for G/E; decay by turn distance/time; evict lowest-importance.                                                                                                                                                                                                                                                                                                                                                                                            | Must     |
| CH-03.3  | **Signal Fusion**: selection score = embeddings + acronym/synonym lexicon + recency + importance.                                                                                                                                                                                                                                                                                                                                                                                                                   | Must     |
| CH-03.4  | **Authority/Dedup**: ❖ FILES > newer > older; A3 suppresses chat duplicates when A1 injects a file.                                                                                                                                                                                                                                                                                                                                                                                                                 | Must     |
| CH-03.5  | **Integrity/Versioning**: each memory item carries source+hash/version hints; **FileManifest is Must** (sha256/MD5 + mtime).                                                                                                                                                                                                                                                                                                                                                                                        | Must     |
| CH-03.6  | **Determinism**: one A2 audit + at most one retrieval re-run on material scope change; Layer-E must not create extra loops.                                                                                                                                                                                                                                                                                                                                                                                         | Must     |
| CH-03.7  | **UI/Controls**: expose `k`, E token budget, synonym list import; show keep/drop reasons.                                                                                                                                                                                                                                                                                                                                                                                                                           | Should   |
| CH-03.8  | **Acceptance**: NVH⇄vehicle acoustics recalled from Layer-E; chat update can beat stale file until re-ingestion; Exact Lock short-circuits E selection.                                                                                                                                                                                                                                                                                                                                                             | Must     |
| CH-03.9  | **Eligibility alignment**: OFF files are not eligible for retrieval; Layer-E may still select history (not tied to file ON/OFF) unless file is injected this turn.                                                                                                                                                                                                                                                                                                                                                  | Must     |
| CH-03.10 | **Durable history, not logs**: **Persist** ConversationMemory state:  – **Text log**: append-only `PATHS.logs/conversation.log` with synchronized appends (user+assistant), fsync each turn. – **Layer-G** reconstructed from tail per prompt. – **Layer-E index**: separate snapshot (e.g., `history_store.pkl`), separate from document vectors; capacity/eviction per CH-03.2. – If persistence fails, continue in-memory and surface an error; determinism and bounded audit rules remain unchanged. **(Must)** | Must     |

**External Replies Import**

| ID    | Requirement                                                                                                              | Priority |
| ----- | ------------------------------------------------------------------------------------------------------------------------ | -------- |
| CH-04 | UI-08 textbox allows pasting an external reply; UI-09 “Send to History” appends it as a new turn with `source=external`. | Must     |
| CH-05 | External replies participate in Layer-E selection/dedup and are subject to the same authority/conflict rules.            | Must     |

### 4.3  Retrieval & Agents

| ID     | Requirement                                                                                                     | Priority |
| ------ | --------------------------------------------------------------------------------------------------------------- | -------- |
| RET-01 | Retriever uses embedding search over the vector store; K and similarity metric are pinned.                      | Must     |
| RET-02 | Reranker refines candidates deterministically (same config = same order).                                       | Must     |
| RET-03 | **A3 NLI Gate** drops candidates inconsistent with the question; threshold `θ` is pinned.                       | Must     |
| RET-04 | **A4 Condenser** emits `S_ctx` with **Facts / Constraints / Open Issues** lines; each Fact cites a source.      | Must     |
| RET-05 | **Exact File Lock** bypasses retrieval; only named ❖ FILES are injected.                                        | Must     |
| RET-06 | Eligibility Pool (ON/OFF) controls which files can be retrieved when not locked.                                | Must     |
| RET-07 | Transparency view shows *kept/dropped reasons* for candidates (kept source IDs, dropped duplicates, threshold). | Should   |

### 4.4  Prompt Orchestration & A2 Audit Model

| ID    | Requirement                                                                                                                                                                               | Priority |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| A2-01 | Pass #1: A2 proposes `{intent, domain, audience, headers, role}` using user prompt + Project Memory + **ConversationMemory (Layer-G/E)**.                                                 | Must     |
| A2-02 | Retrieval → Rerank → A3 → A4 builds `S_ctx`; PromptBuilder composes with fixed authority order.                                                                                           | Must     |
| A2-03 | **Audit #2 (single)**: A2 may refine headers/roles **once** after seeing `S_ctx`. If scope materially changes, Controller allows **one** retrieval→A3→A4 re-run; otherwise reuse `S_ctx`. | Must     |
| A2-04 | **Never overwrites**: A2 **must not** override Hard Rules or Project Memory; authority order is immutable.                                                                                | Must     |

### 4.5  Safety: Guardrails, Brakes, Airbags

#### Guardrails (Policy / Boundaries)

* No code execution/research tooling inside RAGstream beyond minimal deterministic utilities (Embedder, Validator).
* No PDFs/OCR; ingestion is clean text only.
* No autonomous multi-agent loops; only bounded A2 audit with single allowed re-run.

#### Brakes (Timeouts / Cancellation)

* Controller global timeout; per-agent timeouts; UI stop button cancels the current LLM call cleanly.

#### Airbags (Fallbacks / Graceful Degradation)

* If A3 yields empty set, show “No eligible evidence” with kept/dropped reasoning; allow Exact Lock fallback run.

### 4.6  UI / App

| ID        | Requirement                                                                                                             | Priority |
| --------- | ----------------------------------------------------------------------------------------------------------------------- | -------- |
| UI-01     | Single main panel; no sidebars; clean controls for ❖ FILES, eligibility, k, budgets, and submit.                        | Must     |
| UI-02     | Super-Prompt preview (read-only) before send; visibility into ❖ FILES and S\_ctx blocks.                                | Must     |
| UI-03     | Transparency panel shows kept/dropped reasons and A3 decisions.                                                         | Must     |
| UI-04     | Error surfaces are explicit; show cause (timeout, empty eligibility, lock miss).                                        | Must     |
| UI-05     | Cost estimator visible pre-send; enforce token/cost budget; hard stop on exceed.                                        | Must     |
| UI-06     | Optional “RECENT HISTORY” visibility and controls (k, Layer-E budget).                                                  | Should   |
| UI-07     | Optional export of the current answer with citations (markdown).                                                        | Could    |
| **UI-08** | **External Reply textbox**: paste an external answer for history.                                                       | **Must** |
| **UI-09** | **Send to History** button: appends the pasted reply as `source=external` and participates in selection.                | **Must** |
| **UI-10** | **Per-file ON/OFF checkboxes** populate the Eligibility Pool used in retrieval → rerank → A3 → A4 for the current turn. | **Must** |
| **UI-11** | **Persist History (Layer-E) toggle** ON/OFF to allow or block durable embedding snapshots to disk.                      | **Must** |
| **UI-12** | **Clear History** control: on confirmation, clears durable history index and truncates the log tail safely.             | **Must** |

### 4.7  Debug Logger (Feature-2)

**Purpose.** Optional developer-facing logs under `PATHS.logs` to trace actions and, if enabled, variable dumps for debugging.

* Two files per session (new session = new files):

  * `debug_trace.log` — compact steps/explanations with `[timestamp] [level] msg`.
  * `debug_vars.log` — variable names + truncated preview, written only when `vars_enabled=True`.
* `logWriteText(msg, level="INFO")` appends to trace (and vars if enabled).
* `logWriteVar(name1, value1, ...)` writes explanation to trace; if `vars_enabled`, writes name/value pairs to vars log with truncation (default 200 chars/items; per-variable override via `(name, maxlen)`).
* Support at least `INFO` and `DEBUG` levels; include level per line.
* Append-only; optional rollover on size > N MB; fsync periodically to remain readable after crash.
* Serialization: dicts/lists in safe JSON-like form; large objects show length/shape + preview.
* If `vars_enabled=False`, only trace is written; `logWriteVar()` auto-downgrades to `logWriteText()`.

### 4.8  Structured JSON Communication & Provenance (supp2)

**Purpose:** Enforce deterministic, auditable inter-component handoffs by mandating **structured JSON envelopes** for all agent/component outputs and internal APIs.

| ID      | Requirement                                                                                                                                 | Priority      |      |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ------------- | ---- |
| JSON-01 | All agents/components (A0–A5, Controller, PromptBuilder, Retriever, Gate, Condenser) **must emit** and **consume** structured JSON only.    | Must          |      |
| JSON-02 | Every handoff uses a single top-level **JSON envelope**: `type`, `version`, `id`, `goal`, `producer`, `timestamp`, `provenance`, `payload`. | Must          |      |
| JSON-03 | The envelope **must include a `goal` field** stating the intended purpose (e.g., “select eligibility pool”, “provide cited facts”).         | Must          |      |
| JSON-04 | On uncertainty/failure, include an **`escalate` object**: `{ "escalate": true, "reason": "<short>" }` and stop automatic processing.        | Must          |      |
| JSON-05 | PromptBuilder and Controller **consume only JSON envelopes**; human-readable rendering is UI-only.                                          | Must          |      |
| JSON-06 | **Provenance** includes (when applicable): `file.path`, `file.sha256` (or MD5), `file.mtime`, and any `selection_rules` used.               | Must          |      |
| JSON-07 | ConversationMemory **Layer-G/E items are stored and exchanged as JSON** records consistent with this envelope (see JSON-12..JSON-15).       | Must          |      |
| JSON-08 | UI may pretty-print JSON, but internal stores/APIs remain JSON-first.                                                                       | Must          |      |
| JSON-09 | A lightweight schema check validates required fields/types; failures **must set `escalate`** (no uncontrolled retries).                     | Must          |      |
| JSON-10 | Envelope IDs are monotonically increasing per session or globally unique; timestamps are ISO-8601.                                          | Should        |      |
| JSON-11 | **Back-compat note:** This JSON persistence **supersedes plain-text history** where both exist; if both are present, **JSON is canonical**. | Must          |      |
| JSON-12 | **Layer-G**: each kept turn pair is serialized to JSON \`{role, text, timestamp, goal="store recency turn", source="chat                    | external"}\`. | Must |
| JSON-13 | **Layer-E**: per-chunk index metadata `{log_offset, chunk_id, embedding_id, turn_distance, importance, tags, source, file.hash?}`.          | Must          |      |
| JSON-14 | External replies (UI-08/09) are stored with `source="external"` and the same envelope/provenance structure.                                 | Must          |      |
| JSON-15 | Maintain one canonical JSON schema under version control; doc examples are illustrative only.                                               | Must          |      |

### 4.9  Agent A0 — FileScopeSelector (supp2)

**Purpose:** Deterministically build the minimal **Eligibility Pool** honoring Exact File Lock and ON/OFF toggles, with explainable reasons.

| ID    | Requirement                                                                                                                                                                     | Priority |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| A0-01 | Inputs: prompt; **FileManifest** (name, path, hash, mtime, tags); UI toggles (ON/OFF per file, ❖FILES lock); optional include/exclude lists; static alias labels.               | Must     |
| A0-02 | Outputs: ordered eligible files with **per-file reason trace**; compact ❖FILES candidate block; JSON envelope `goal="select eligibility pool"`.                                 | Must     |
| A0-03 | Rules (priority): OFF → exclude; ❖FILES lock never overridden; hard-includes win; hard-excludes remove; title/regex > tag > **static** synonym/alias; tie: priority→mtime→path. | Must     |
| A0-04 | Enforce max-N; if overflow, keep top by rule order and record truncation reason.                                                                                                | Must     |
| A0-05 | No network; **no dynamic embeddings**; decisions must be explainable from manifest/aliases only.                                                                                | Must     |
| A0-06 | Failure codes: `EMPTY_ELIGIBILITY` (no candidates, no lock), `LOCK_MISS` (locked files missing); controller surfaces escalation.                                                | Must     |
| A0-07 | Controller runs A0 **before** A1; with lock present, A0 validates and passes lock-through without expansion.                                                                    | Must     |

### 4.10  Agent A5 — Schema/Format Enforcer (supp2)

**Purpose:** Enforce `CodeSpec.md` on generated artifacts and allow exactly **one** bounded self-repair; then re-validate once.

| ID    | Requirement                                                                                                                                                                               | Priority |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| A5-01 | Inputs: draft output; `CodeSpec.md` (versioned, hashed); task metadata (language/runtime/libs); stop conditions (no prose, single file, fixed filename).                                  | Must     |
| A5-02 | Checks: structure order; naming/imports allow/deny; forbidden I/O/network/time if disallowed; output shape (single fenced block, fixed filename); style normalization (formatter/linter). | Must     |
| A5-03 | On violation: emit minimal line-referenced **violation report**; permit **one** self-repair (same model, temp=0) using only: violation list + CodeSpec excerpts + original prompt.        | Must     |
| A5-04 | After self-repair, re-validate once; if still failing, return `FAIL` with the violation report; **no loops**.                                                                             | Must     |
| A5-05 | A5 JSON envelope includes `goal="validate schema compliance"` and provenance: `spec.hash`, `draft.hash`, `final.hash`.                                                                    | Must     |
| A5-06 | A5 **must not** mutate `CodeSpec.md` at runtime; spec changes are human-authored and versioned.                                                                                           | Must     |

### 4.11  Human-in-the-Loop Escalation (supp2)

| ID     | Requirement                                                                                                                                                            | Priority |
| ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| HIL-01 | Any agent/component unable to complete reliably **must** set `escalate=true` with a short `reason` in its JSON envelope.                                               | Must     |
| HIL-02 | On escalation, the Controller **halts the path** and surfaces the issue in UI for human decision; no autonomous retries beyond allowed cases (e.g., A5 single repair). | Must     |
| HIL-03 | Escalations are visible in transparency/log views with envelope `id`, `producer`, and `goal`.                                                                          | Should   |

---

## 5  Non-Functional Requirements

| Area           | Requirement                                                                                       |
| -------------- | ------------------------------------------------------------------------------------------------- |
| Determinism    | Same inputs/config yield same outputs; bounded A2 audit + single allowed re-run only.             |
| Transparency   | Keep/dropped reasoning visible; A3 decisions visible; PromptBuilder shows authority order blocks. |
| Locality       | All data and stores are local; no forced cloud dependencies; ConversationMemory persists locally. |
| Performance    | Token budgets enforced; costs estimated pre-send; snapshots are O(1) to publish (atomic replace). |
| Modularity     | Components are replaceable (Embedder, VectorStoreNP/Chroma), ready for TinnyLlama integration.    |
| Personal Scope | No end-user automation, no CI scaffolding, no pytest mandate.                                     |

---

## 6  Technology Stack

* Python 3.10+
* OpenAI client (or local model client)
* NumPy for vector store; optional Chroma when environment allows
* Streamlit UI (or similar)
* Standard libraries for fsync/atomic replace

---

## 7  Directory / Module Tree

```
ragstream/
  app/
    agents/
      a1_dci.py
      a2_prompt_shaper.py
      a3_nli_gate.py
      a4_condenser.py
    controller.py
    ui_streamlit.py
  ingestion/
    loader.py
    chunker.py
    embedder.py
    vector_store.py
    vector_store_np.py
  memory/
    conversation_memory.py
  orchestration/
    prompt_builder.py
    llm_client.py
  utils/
    paths.py
    logging.py
```

* `utils/paths.py` provides `PATHS` including `logs/` root for conversation and debug logs.
* NumPy `.pkl` snapshots are persisted with atomic swap; Chroma optional.

---

## 8  Open Issues / Risks

* Long-running sessions: memory budgets vs. quality.
* Local model variance vs. determinism; pinning configs needed.
* Manual synonym lists maintenance (NVH⇄vehicle acoustics, etc.).

---

## 9  Acceptance Criteria

1. **Conversation Memory**
   • The last k turns (Layer-G) are always available to A2 and visible in UI if enabled.
   • Layer-E contributes only clearly on-topic or important items; duplicates of ❖ FILES are suppressed.
   • Conflicts resolved by authority and freshness (**❖ FILES > newer > older**).
   • **Semantic aliasing** examples (e.g., **NVH ⇄ vehicle acoustics**) are recalled via Layer-E selection.
   • **External replies** imported via UI-09 are stored with `source=external` and participate in selection/dedup.
   • **Persistence:** after each turn, `conversation.log` ...; Layer-E loads from the last published snapshot (or backfills).

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
   • UI exposes `k`, Layer-E budget, and synonym import; UI-10 enforces eligibility; UI-11/12 manage history persistence.

5. **JSON & Escalation**
   • All inter-agent handoffs use JSON envelopes with required fields; schema failures set `escalate` and halt the path.
   • Every envelope carries a `goal` and provenance (file path + hash/mtime when applicable).

6. **A0 & A5**
   • A0 deterministically builds the Eligibility Pool with per-file reason traces; honors ❖FILES and ON/OFF; emits `EMPTY_ELIGIBILITY`/`LOCK_MISS` when applicable.
   • A5 validates outputs against `CodeSpec.md`, permits exactly one self-repair, then re-validates once; failures return a violation report.

---

## 10  Glossary (Updated)

| Term                        | Meaning                                                                                                                                                 |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ConversationMemory          | Read-only provider of Layer-G (recency window) and Layer-E (episodic).                                                                                  |
| Layer-G                     | Always-keep recency window of last k turns.                                                                                                             |
| Layer-E                     | Episodic store of older turns with metadata and fading.                                                                                                 |
| ❖ FILES                     | Deterministically injected files by A1; canonical for that turn.                                                                                        |
| S\_ctx                      | Cited, condensed context emitted by A4 (Facts/Constraints/Open Issues).                                                                                 |
| A2 audit                    | Second, controlled pass of A2 after A4 to refine headers/roles.                                                                                         |
| Authority order             | \[Hard Rules] → \[Project Memory] → \[❖ FILES] → \[S\_ctx] → \[Task/Mode].                                                                              |
| Eligibility Pool            | Set of files currently ON for retrieval; populated by UI-10.                                                                                            |
| Debug Logger                | Optional per-session trace/vars logs under `PATHS.logs/`; not used for retrieval/history.                                                               |
| JSON Envelope               | Canonical wrapper for inter-agent messages with `type`, `version`, `id`, `goal`, `producer`, `timestamp`, `provenance`, `payload`, optional `escalate`. |
| `goal` field                | Declares the intended purpose of a JSON message (selection, facts, compliance, etc.).                                                                   |
| `escalate` field            | Signals handoff to human when an agent cannot reliably proceed; carries a short reason.                                                                 |
| A0 (FileScopeSelector)      | Deterministic pre-filter that builds the Eligibility Pool from FileManifest, ❖FILES lock, and ON/OFF toggles (no embeddings).                           |
| A5 (Schema/Format Enforcer) | Contract checker validating outputs against `CodeSpec.md`; allows exactly one bounded self-repair then re-validates once.                               |

---

### Change Log (edits to remove anti-logging language; FileManifest status)

* **§3 System Context** — removed “ephemeral” qualifier from “Transparency (kept/dropped reasons)”.
* **ING-06** — changed to allow persistence via Debug Logger (“…MAY be persisted via Debug Logger per Feature-2”).
* **RET-07** — removed “(ephemeral; no persistent logs)”.
* **UI-03** — removed “(ephemeral; no persisted logs)”.
* **§5 Non-Functional (Privacy/Locality row)** — clarified that “All data and stores are local; ConversationMemory persists locally; Debug Logger is user-controlled.”
* **§9 Acceptance → UI bullet** — removed “(no persisted logs)”.
* **ING-05** — confirmed **Must** (sha256/MD5 + mtime) and ensured no other table lists it as “Planned.”

### Change Log (supp2 integration)

* Added **§4.8 Structured JSON Communication & Provenance (supp2)** with JSON-01..JSON-15.
* Added **§4.9 Agent A0 — FileScopeSelector (supp2)** with A0-01..A0-07.
* Added **§4.10 Agent A5 — Schema/Format Enforcer (supp2)** with A5-01..A5-06.
* Added **§4.11 Human-in-the-Loop Escalation (supp2)** with HIL-01..HIL-03.
* Acceptance (§9): added items 5 and 6 for JSON/envelopes/escalation and A0/A5 behaviors.
* Glossary (§10): added rows for JSON Envelope, `goal`, `escalate`, A0, and A5.

---

**(End of file)**
