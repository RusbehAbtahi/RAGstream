
# Architecture – RAGstream (Aug 2025)

This document shows the end-to-end architecture for RAGstream, aligned with the updated **Requirements (v2.2)**. It removes internal Tooling, adds **ConversationMemory** (two-layer, soft-fading, read-only with a **selection-only Layer-E semantic index** kept separate from the document store), formalizes **A2’s post-audit** with a **single bounded re-run** of the retrieval path (with a clear trigger rubric), and preserves deterministic authority order and Exact File Lock semantics. Vectors persist as NumPy `.pkl` snapshots (Chroma paused), and ingestion targets clean text. Personal-use only. **FileManifest** is a **Must** for deterministic inclusion/versioning.&#x20;

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
                    ├── Super-Prompt preview (editable, source of truth)
                    ├── External Reply box (UI-08) + “Send to History” (UI-09)
                    └── Transparency (kept/dropped reasons; ephemeral)

                    ▼
                 🧠 Controller
                    ├── A2 Prompt Shaper — pass-1 (uses: Project Memory + ConversationMemory.G/E)
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
                    └── 📊 Transparency panel (kept/dropped reasons; ephemeral)

                    ▲
                    │  read-only
                    │
             🗂️ ConversationMemory
             (G = recency window; E = episodic w/ metadata + selection-only semantic index; soft fading)
```

*Notes:* **ConversationMemory** is a **controller-side, read-only** source used by A2 (pre and post) and optionally surfaced by PromptBuilder; it **does not change A1–A4 interfaces**. **External replies** can be pasted (UI-08) and appended (UI-09) with `source=external`. **❖ FILES** remain authoritative over history.&#x20;

---

## Ingestion & Memory

**DocumentLoader** discovers files under `data/doc_raw/`.
• Current: `.txt`, `.md`, `.json`, `.yml`.
• **FileManifest is Must**: `path`, `sha256` (or MD5), `mtime`, `type` for deterministic inclusion/versioning.
**Chunker**: token-aware overlapping windows (≈1 024 tokens, overlap ≈200).
**Embedder**: E5/BGE family (configurable).
**VectorStore**: **NumPy `.pkl` snapshots** (Chroma paused; on-disk collection planned later).&#x20;

### Conversation Memory (read-only; two-layer, soft fading)

**Purpose.** Maintain flow/coherence without re-chunking chat; history remains **separate from the document store**. **Layer-E maintains a small, append-only, selection-only semantic index (embeddings) used solely to score episodic turns for inclusion (never to populate `S_ctx`).**&#x20;

**Layers.**

* **Layer-G (recency):** always include last *k* user–assistant turns verbatim (k≈3–5; configurable).
* **Layer-E (episodic):** older turns with metadata: turn distance, optional Δt, topic tags, importance flag, `source` (chat/file/external), version hints (filename/path + `mtime`/hash).&#x20;

**Selection & fading (guardrails).**

* Guaranteed recency (always pass G).
* From E, propose clearly on-topic items via **signal fusion**: selection-only embeddings + acronym/synonym lexicon (e.g., *NVH ⇄ vehicle acoustics*) + **recency** + **importance**.
* Soft preference for freshness; importance can override; **token-budget-first**; smooth keep/drop; optional real-time damping on large gaps.
* **Capacity caps** on E vectors; evict lowest-importance first.&#x20;

**Dedup & conflicts vs ❖ FILES.**

* If A1 injects a file, **suppress chat fragments** that duplicate/conflict with that file for this turn.
* Conflict resolution: **❖ FILES > newer > older**; surface conflicts in transparency (ephemeral).
* Every Fact in `S_ctx` must carry at least one citation.&#x20;

**Compression.** Very old spans may be rolled into compact, titled summaries; **never summarize G**; promote summaries that prove useful.&#x20;

**Exposure.** A2 (pass-1 and audit-2) reads G + eligible E; PromptBuilder **may** include a short **“RECENT HISTORY”** block (non-authoritative).&#x20;

**External Reply Path.** **UI-08** provides a text box to paste/edit an external reply; **UI-09** appends it to ConversationMemory with `source=external`, timestamp, and optional hash/version hints; such items participate in Layer-E selection and dedup rules.&#x20;

---

## Feature-1 — Conversation History **Persistence** & **Async Layer-E Embedding**

> **Goal:** Make history durable on disk and keep Layer-E selection deterministic via snapshot publishing; never block the prompt path on embeddings.

**(F1-1) Append-only conversation log (single source of truth).**

* Path: `PATHS.logs/conversation.log`.
* After each completed turn (user prompt + assistant reply), the controller **appends both texts** in order, then **flushes + fsyncs** before accepting the next prompt.
* If the reply comes from outside (UI-08/09), the controller appends the pasted text with `source=external`.
* **Layer-G is reconstructed from the tail of this file** on each prompt; no RAM-only history.&#x20;

**(F1-2) Layer-G read path.**

* On each prompt, parse the tail of `conversation.log` to build the last *k* user/assistant pairs (verbatim, no summarization).
* G is visible in UI if enabled; it remains **non-authoritative** in PromptBuilder.&#x20;

**(F1-3) Layer-E embedding store (separate from documents).**

* Maintain a dedicated **NumPy** vector store snapshot for history (e.g., `history_store.pkl`).
* **Append-only; selection-only:** used to **score** episodic turns for inclusion and **never** injected into `S_ctx`.
* **Completely separate** from the document vector snapshots.
* Enforce **capacity caps** and token budgets per guardrails.&#x20;

**(F1-4) Async delta embedding worker.**

* After the synchronous log append completes, enqueue the **new tail** for background processing:

  1. read only the unprocessed tail with a **small overlap** (one last chunk) for boundary stability;
  2. split into chunks;
  3. embed the **new chunks**;
  4. write to a **staging** `.pkl`.
* Use **stable IDs** (e.g., `<log_offset>::chunk_n`) and content-hash de-duplication.
* This ensures we never re-embed the whole log.&#x20;

**(F1-5) Atomic snapshot publishing.**

* Writers only touch `history_store_dynamic.pkl`.
* When a batch is complete, **flush+fsync** and then **publish** via `os.replace(history_store_dynamic.pkl → history_store.pkl)`.
* Readers always open `history_store.pkl` and therefore see either the old or the new snapshot — **never a half-write**.&#x20;

**(F1-6) Read paths per prompt.**

* **G:** tail of `conversation.log` (synchronous).
* **E:** open current `history_store.pkl` (latest published snapshot).
* The prompt path **never blocks** on embedding; it uses the last published E snapshot.&#x20;

**(F1-7) Startup & failure behavior.**

* On startup, open/create `conversation.log`, build G from tail, and try to open `history_store.pkl`.
* If E is missing, start empty and let the worker backfill from the log.
* If the worker fails, the last published snapshot remains valid; retry next cycle.&#x20;

**(F1-8) Authority, eligibility, dedup unaffected.**

* Exact File Lock and authority order remain unchanged; A3 suppresses history fragments that duplicate injected ❖ FILES; **Eligibility Pool** still bounds retrieval candidates.&#x20;

---

## Agent-by-agent (precise responsibilities)

### A1 — Deterministic Code Injector (DCI)  ➜ “❖ FILES” section

**What:** The only agent allowed to inject **full** code/config you explicitly name. No ranking/retrieval.
**Inputs:** your prompt; ON/OFF selections; Exact File Lock; **FileManifest**.
**Output:** **❖ FILES** block (FULL or PACK if large).
**Policy:** If **Exact File Lock = ON**, retrieval is skipped. Markdown/notes remain for retrieval; A1 targets code/config deterministically.&#x20;

### A2 — Prompt Shaper (intent/domain + meta-prompt headers)

**What:** Lightweight **prompt shaper** proposing task **intent/domain** and structured headers.
**Pass-1 (pre-retrieval):** Uses {**user prompt + Project Memory + ConversationMemory.G/E**}.
**Audit-2 (post-A4):** Reads **`S_ctx`** (plus same anchors) to **audit** and **refine** headers/roles; **cannot override** Hard Rules, Project Memory, or Exact File Lock.
**Bounded re-run rule:** If audit-2 **materially** changes **task scope** (intent/domain), permit **one** re-run of *Retriever → Reranker → A3 → A4*; otherwise reuse the existing `S_ctx`.
**Material scope change rubric:** change of **intent/domain**, or **target artifact set** affecting retrieval eligibility, or **deliverable type** (code vs spec vs plan). Pure tone/audience/format changes **do not** qualify.&#x20;

### A3 — NLI Gate (semantic filter)

**What:** Drops candidates not **entailed** by the query/task; adjustable strictness θ; obeys ❖ FILES precedence and dedup rules.&#x20;

### A4 — Condenser (context composer)

**What:** Emits `S_ctx` with **Facts / Constraints / Open Issues** (cited).
**Guarantee:** Every Fact carries ≥1 citation; if schema fails, controller triggers fallback (SAF-A1).&#x20;

---

## Prompt Orchestration

**Authority order (fixed):** \[Hard Rules] → \[Project Memory] → \[❖ FILES] → \[S\_ctx] → \[Task/Mode].
**PromptBuilder** assembles the final system/user messages; it may optionally show a **“RECENT HISTORY”** block (non-authoritative). **Exact File Lock** injects only ❖ FILES and skips retrieval entirely.&#x20;

---

## Eligibility Pool

ON/OFF checkboxes constrain which files are eligible for retrieval (when not locked). The pool affects the Retriever’s candidate set before rerank, NLI gate, and condensation. Authority order ensures the final prompt never violates Hard Rules or Project Memory.&#x20;

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
**Crash-survivability:** writer flushes + fsyncs each line; if `vars_enabled=False`, no `debug_vars` file is produced.&#x20;

---

## Persistence & Modularity

Vectors persist as **NumPy `.pkl` snapshots**; Chroma on-disk collection is planned once stable in your environment. **ConversationMemory** persists text in `conversation.log` and publishes **Layer-E** snapshots via atomic swap. The system remains modular to enable future AWS TinnyLlama Cloud integration (swap embedding models, LLMs, or vector store without touching UI/controller surfaces).&#x20;

---

# Sync Report

**Integrated features (per Requirements v2.2):**

* **Feature-1:** Durable `conversation.log`, Layer-G tail read, dedicated Layer-E **selection-only** embedding store, async delta worker, **atomic** snapshot publishing, per-prompt read paths (G from log, E from latest snapshot), startup/backfill behavior, and preservation of authority/eligibility/dedup rules.&#x20;
* **Feature-2:** **Debug Logger** with trace/vars files, methods, truncation, levels, optional rollover, serialization rules, and crash-survivability semantics.&#x20;
* **UI-08/09:** External reply import path (`source=external`) into ConversationMemory and participation in Layer-E selection/dedup.&#x20;
* **FileManifest = Must**; authority order **❖ FILES > newer > older**; Exact File Lock; Eligibility Pool; A2 audit with **single bounded re-run** and **material scope change** rubric.

**Sections/diagrams updated:**

* Main query-flow diagram (added UI-08/09 and explicit ConversationMemory note).&#x20;
* Conversation Memory subsection (expanded for persistence + async Layer-E embedding + atomic swap).&#x20;
* New Feature-1 and Feature-2 sections without altering agent interfaces.
* Persistence & Modularity paragraph (clarified CM persistence).&#x20;

**Alignment confirmation:**
`Architecture_2.md` now reflects **all** requirements pertaining to Layer-E selection-only embeddings, durability, external reply import, the bounded A2 audit re-run, Eligibility Pool, authority order, FileManifest, and Debug Logger. **No contradictions detected** with the current `Requirements.md`.&#x20;

---
