# Architecture – RAGstream (Aug 2025)

This document shows the end-to-end architecture for RAGstream, aligned with the updated Requirements (v2.0). It removes internal Tooling, adds **ConversationMemory** (two-layer, soft-fading, read-only), formalizes **A2’s post-audit** with a **single bounded re-run** of the retrieval path, and preserves deterministic authority order and Exact File Lock semantics. Vectors persist as NumPy `.pkl` snapshots (Chroma paused), and ingestion targets clean text. Personal-use only: no persistent logs, no pytest/CI/DevOps; functional quality remains production-grade.&#x20;

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
                         │ builds       │ planned
                         │              │
                         │              └──▶ 📇 FileManifest (path, sha, mtime, type)
                         │

╔═════════════════════════════════════════════════════════════════════════════╗
║                               MAIN QUERY FLOW                               ║
╚═════════════════════════════════════════════════════════════════════════════╝

[User Prompt] ───▶ 🎛️  Streamlit GUI
                    ├── Prompt box (you)
                    ├── ON/OFF file checkboxes  (+ “Exact File Lock”)
                    ├── Prompt Shaper panel (intent/domain + headers)
                    ├── Agent toggles (A1..A4), Model picker, Cost estimator
                    └── Super-Prompt preview (editable, source of truth)

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
             (G = recency window; E = episodic w/ metadata; soft fading)
```

*Notes:* **ConversationMemory** is a **controller-side, read-only** source used by A2 (pre and post) and optionally surfaced by PromptBuilder; it **does not change A1–A4 interfaces**. Internal Tooling is **out of scope**.&#x20;

---

## Ingestion & Memory

**DocumentLoader** discovers files under `data/doc_raw/`.
• Current: `.txt`, `.md`, `.json`, `.yml`. • Planned: FileManifest (`path`, `sha256`, `mtime`, `type`).
**Chunker**: token-aware overlapping windows.
**Embedder**: E5/BGE family (configurable).
**VectorStore**: **NumPy `.pkl` snapshots** (Chroma paused; planned on-disk collection when stable).&#x20;

### Conversation Memory (read-only; two-layer, soft fading)

**Purpose.** Maintain flow/coherence without re-chunking or embedding chat. History is **not** part of the document store.&#x20;

**Layers.**

* **Layer-G (recency window):** always include last *k* user–assistant turns (k≈3–5; configurable).
* **Layer-E (episodic store):** older turns w/ metadata (turn distance, optional Δt, tags, importance flag, source, version hints).&#x20;

**Selection & fading.**

* Guaranteed recency (always pass G).
* From E, pick clearly on-topic with soft preference for freshness; importance can override; smooth keep/drop; **token-budget-first** selection.
* Optional real-time damping if long gaps between sessions.&#x20;

**Dedup & conflicts vs ❖ FILES.**

* If A1 injects a file, **suppress chat fragments** that duplicate/conflict with that file for this turn.
* Conflict resolution: **❖ FILES > newer > older**; surface conflicts in the transparency panel (ephemeral).&#x20;

**Compression.**

* Very old spans may be rolled into compact, titled summaries; **never summarize G**. Promote summaries that prove useful.&#x20;

**Exposure.**

* A2 (pass-1 and audit-2) reads G + eligible E; PromptBuilder **may** include a short “RECENT HISTORY” block when helpful.
* The RECENT HISTORY view is **non-authoritative**; it cannot override ❖ FILES or S\_ctx.&#x20;

---

## Agent-by-agent (precise responsibilities)

### A1 — Deterministic Code Injector (DCI)  ➜ “❖ FILES” section

**What:** The only agent allowed to inject **full** code/config you explicitly name. No ranking/retrieval.
**Inputs:** your prompt; ON/OFF selections; Exact File Lock; (planned) FileManifest.
**Output:** **❖ FILES** block (FULL or PACK if large).
**Policy:** If **Exact File Lock = ON**, retrieval is skipped. Markdown/notes remain for retrieval; A1 targets code/config deterministically.&#x20;

### A2 — Prompt Shaper (intent/domain + meta-prompt headers)

**What:** Lightweight **prompt shaper** proposing task **intent/domain** and structured headers.
**Pass-1 (pre-retrieval):** Uses *user prompt + Project Memory + ConversationMemory.G/E*.
**Audit-2 (post-A4):** Reads **S\_ctx** (plus same anchors) to **audit** and **refine** headers/roles.
**Bounded re-run rule:** If audit-2 **materially** changes **task scope** (intent/domain), permit **one** re-run of *Retriever → Reranker → A3 → A4*; otherwise reuse S\_ctx. **Never** override Hard Rules, Project Memory, or Exact File Lock.&#x20;

### A3 — NLI Gate (semantic filter)

**What:** Drops candidates not **entailed** by the query/task; adjustable strictness θ.
**Role with history & files:** Suppresses chat fragments overlapping with ❖ FILES; enforces conflict policy (FILES > newer > older).&#x20;

### A4 — Condenser (composer of `S_ctx`)

**What:** Produces compact, cited **`S_ctx`** with **Facts / Constraints / Open Issues**. Output **must** validate to schema; on failure, controller falls back to showing top reranked, NLI-kept chunks.&#x20;

---

## Prompt Orchestration

**Fixed authority order** (facts over style):

```
[Hard Rules] → [Project Memory] → [❖ FILES] → [S_ctx] → [Your Task/Format/Mode]
```

*Notes:* **RECENT HISTORY**, when shown, is a **non-authoritative** aide for continuity; it does not participate in precedence and cannot overrule ❖ FILES or S\_ctx. Exact File Lock continues to short-circuit retrieval.&#x20;

---

## Deterministic vs. Model-Driven

* **Deterministic:** A1 (DCI), File ON/OFF eligibility, PromptBuilder authority application, Exact File Lock, bounded re-run rule.
* **Model-driven:** A2 (both passes), Reranker, A3 (NLI Gate), A4 (Condenser). The pipeline order and “one audit + optional one re-run” cap preserve **determinism of flow**.&#x20;

---

## End-to-End Narrative (what happens when you click)

1. You type a prompt, optionally name files, set Exact File Lock, pick model, see cost.
2. **A2 pass-1** proposes intent/domain + headers using Project Memory + ConversationMemory (G/E).
3. **A1** emits **❖ FILES** (FULL/PACK). If **locked**, skip retrieval.
4. If unlocked: **Retriever → Reranker → A3 → A4** produce **S\_ctx** (short, cited).
5. **A2 audit-2** reads **S\_ctx** and refines headers/roles; if it **changes scope**, perform **one** retrieval→A3→A4 re-run; otherwise keep S\_ctx.
6. **PromptBuilder** assembles the Super-Prompt with the fixed authority order; it may show a brief non-authoritative “RECENT HISTORY” block for continuity.
7. **LLMClient** sends; GUI shows answer, citations, ❖ FILES, token/cost, and a **transparency** view of kept/dropped with reasons (ephemeral only).&#x20;

---

## Why this fits the repo and requirements

* Preserves clean module boundaries (Controller orchestrates A1–A4; ConversationMemory is a controller-side helper; PromptBuilder/LLMClient unchanged).
* Adds quality levers beyond vanilla RAG (NLI Gate + schema-validated Condenser; authority order; Exact File Lock; bounded audit) for **production-grade** functional control.
* Mirrors the updated Requirements: **two-layer history with fading**, **A2 double-pass with one allowed re-run**, **no internal Tooling**, **NumPy `.pkl` persistence**, **personal-use** constraints, and **TinnyLlama-ready** modularity.&#x20;

---

## TL;DR

* **A1 DCI** — Deterministic file injection (**❖ FILES**, lock supported).
* **A2 Prompt Shaper** — Two passes (pre + post audit), can trigger **one** retrieval re-run on scope change.
* **A3 NLI Gate** — Semantic bouncer; enforces “FILES > newer > older” and suppresses duplicates.
* **A4 Condenser** — Emits cited **`S_ctx`** (Facts / Constraints / Open Issues), schema-validated.
* **ConversationMemory (G/E)** — Read-only continuity: recency + episodic, soft fading, dedup vs ❖ FILES, optional compact summaries.
* **PromptBuilder** — Fixed authority order; RECENT HISTORY is non-authoritative.&#x20;

---

## Sync Report

**Imported from Requirements.md:** ConversationMemory (G/E, metadata, soft fading, dedup vs ❖FILES, conflict policy, optional compression, token-budget selection, exposure rules); A2 audit with **single bounded re-run** on scope change; fixed authority order; Exact File Lock; Eligibility Pool; A4 schema validation and transparency (ephemeral); NumPy `.pkl` persistence; personal-use constraints; modularity/TinnyLlama readiness.&#x20;

**Removed/edited lines:** Eliminated any “Pre-MVP/MVP” wording; removed ToolDispatcher/Tooling mentions in flow and sections; clarified transparency as **ephemeral** (no persistent logs); added non-authoritative status for RECENT HISTORY; noted read-only ConversationMemory feeding A2 and PromptBuilder.&#x20;

**Consistency check:** Architecture now matches Requirements with no contradictions: A1–A4 interfaces unchanged; ConversationMemory is controller-side, read-only; A2’s two passes and the one re-run gate are explicit; authority order untouched; Exact File Lock and eligibility semantics preserved; no internal Tooling; personal-use, production-grade stance affirmed.&#x20;
