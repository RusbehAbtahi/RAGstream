# Architecture – RAGstream (Aug 2025)

This document shows the end-to-end architecture for RAGstream, aligned with the updated **Requirements (v2.2)**. It removes internal Tooling, adds **ConversationMemory** (two-layer, soft-fading, read-only with a **selection-only Layer-E semantic index** kept separate from the document store), formalizes **A2’s post-audit** with a **single bounded re-run** of the retrieval path (with a clear trigger rubric), and preserves deterministic authority order and Exact File Lock semantics. Vectors persist as NumPy `.pkl` snapshots (Chroma paused), and ingestion targets clean text. Personal-use only: no persistent logs, no pytest/CI/DevOps; functional quality remains production-grade. **FileManifest** is a **Must** for deterministic inclusion/versioning.&#x20;

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

*Notes:* **ConversationMemory** is a **controller-side, read-only** source used by A2 (pre and post) and optionally surfaced by PromptBuilder; it **does not change A1–A4 interfaces**. **External replies** can be pasted (UI-08) and appended (UI-09) with `source=external`. **❖ FILES** remain authoritative over history.

---

## Ingestion & Memory

**DocumentLoader** discovers files under `data/doc_raw/`.
• Current: `.txt`, `.md`, `.json`, `.yml`.
• **FileManifest is Must**: `path`, `sha256` (or MD5), `mtime`, `type` for deterministic inclusion/versioning.
**Chunker**: token-aware overlapping windows (≈1 024 tokens, overlap ≈200).
**Embedder**: E5/BGE family (configurable).
**VectorStore**: **NumPy `.pkl` snapshots** (Chroma paused; on-disk collection planned later).&#x20;

### Conversation Memory (read-only; two-layer, soft fading)

**Purpose.** Maintain flow/coherence without re-chunking chat; history remains **separate from the document store**. **Layer-E maintains a *small, append-only, selection-only* semantic index (embeddings) used solely to *score* episodic turns for inclusion (never to populate `S_ctx`).**&#x20;

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

**What:** Drops candidates not **entailed** by the query/task; adjustable strictness θ.
**Role with history & files:** Suppresses chat fragments overlapping with ❖ FILES; enforces conflict policy (**FILES > newer > older**).&#x20;

### A4 — Condenser (composer of `S_ctx`)

**What:** Produces compact, cited **`S_ctx`** with **Facts / Constraints / Open Issues**; output **must validate to schema**; on failure the controller falls back to showing top reranked, NLI-kept chunks.&#x20;

---

## Prompt Orchestration

**Fixed authority order** (facts over style):

```
[Hard Rules] → [Project Memory] → [❖ FILES] → [S_ctx] → [Your Task/Format/Mode]
```

*Notes:* **RECENT HISTORY**, when shown, is **non-authoritative** and cannot overrule ❖ FILES or `S_ctx`. Exact File Lock continues to short-circuit retrieval.&#x20;

---

## Deterministic vs. Model-Driven

* **Deterministic:** A1 (DCI), File ON/OFF eligibility, PromptBuilder authority application, Exact File Lock, bounded re-run rule cap.
* **Model-driven:** A2 (both passes), Reranker, A3 (NLI Gate), A4 (Condenser). The pipeline order and “one audit + optional one re-run” cap preserve **determinism of flow**.&#x20;

---

## End-to-End Narrative (what happens when you click)

1. You type a prompt, optionally name files, set Exact File Lock, pick model, see cost.
2. **A2 pass-1** proposes intent/domain + headers using Project Memory + ConversationMemory (G/E).
3. **A1** emits **❖ FILES** (FULL/PACK). If **locked**, skip retrieval.
4. If unlocked, **Retriever → Reranker → A3 → A4** produce **`S_ctx`** with citations.
5. **A2 audit-2** reads `S_ctx` and may refine headers/roles. If **material scope change**, the controller permits **one** bounded re-run of retrieval→A4; otherwise reuse `S_ctx`.
6. **PromptBuilder** composes the final Super-Prompt (authority order); optionally includes a brief RECENT HISTORY block (non-authoritative).
7. **LLMClient** sends the prompt; the UI shows answer + citations; transparency panel lists kept/dropped reasons (ephemeral).
8. Optional: If you pasted an **External Reply** (UI-08) and clicked **Send to History** (UI-09), it’s appended to ConversationMemory (`source=external`) and considered for future Layer-E selection/dedup.&#x20;

---

## Exact File Lock

When enabled, retrieval is skipped. Only **❖ FILES** are injected deterministically (FULL or PACK). History remains non-authoritative and is used only by A2 for shaping; A3 suppresses overlapping history when files are injected to avoid echoing.&#x20;

---

## Eligibility Pool

ON/OFF checkboxes constrain which files are eligible for retrieval (when not locked). The pool affects the Retriever’s candidate set before rerank, NLI gate, and condensation. Authority order ensures the final prompt never violates Hard Rules or Project Memory.&#x20;

---

## Persistence & Modularity

Vectors persist as **NumPy `.pkl` snapshots**; Chroma on-disk collection is planned once stable in your environment. The system remains modular to enable future AWS TinnyLlama Cloud integration (swap embedding models, LLMs, or vector store without touching UI/controller surfaces).&#x20;

---

# Sync Report

**Imported from Requirements v2.2:**

* ConversationMemory with **Layer-G + Layer-E (selection-only semantic index with guardrails)**; explicit separation from the document store; capacity/budget; fusion (embeddings + synonym/acronym list + recency + importance); authority/dedup; integrity/version metadata; determinism; transparency; acceptance.&#x20;
* **A2 audit + single bounded re-run** with **material scope change rubric**.&#x20;
* **UI-08/UI-09** external reply → history import (`source=external`).&#x20;
* **FileManifest is Must** (sha256/MD5, mtime).&#x20;
* Authority order **❖ FILES > newer > older** preserved; no Tooling/MVP; personal-use only; modular/TinnyLlama-ready.&#x20;

**Updated/added lines & blocks:**

* Main diagram: added **External Reply box (UI-08/09)** and annotated ConversationMemory as **selection-only** for Layer-E.&#x20;
* Ingestion & Memory: **FileManifest** upgraded to **required**; clarified `.pkl` persistence.&#x20;
* Conversation Memory subsection: replaced “no embedding chat” with **selection-only semantic index**; added guardrails bullets.&#x20;
* A2 section: inserted **material scope change rubric** and one-re-run cap.&#x20;
* End-to-End Narrative: appended **external reply path**.&#x20;

**No contradictions detected** between `Requirements.md v2.2` and this `Architecture_2.md`. The document keeps the original structure and ASCII style; unchanged parts are preserved verbatim. The next step is to **sync `PlanetextUML.md`** to reflect: ConversationMemory (Layer-G/E selection-only), FileManifest=Must, UI-08/09 link to ConversationMemory, and the A2 audit re-run rubric.&#x20;
