
# Architecture – RAGstream (Pre-MVP, Aug 2025)

This document shows the end-to-end architecture for RAGstream. It reflects the updated README: A2 is a Prompt Shaper (intent/domain + headers), vectors persist as NumPy `.pkl` snapshots (Chroma paused), and ingestion currently handles plain/unformatted text files.

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
                    ├── Agent toggles (A1..A4), Mode (INTP/ENTJ…)
                    ├── Model picker + cost estimator
                    └── Super-Prompt preview (editable, source of truth)

                    ▼
                 🧠 Controller
                    ├── A2 Prompt Shaper (propose intent/domain + headers; you override)
                    ├── A1 Deterministic Code Injector (files you named)
                    │     └─ emits:  ❖ FILES section (FULL or PACK), locked if chosen
                    ├── Eligibility Pool (from your ON/OFF checkboxes / presets)
                    ├── (if not locked)
                    │      ┌──────────────────────────────────────────────┐
                    │      │ 🔍 Retriever → 🏅 Reranker → A3 NLI Gate → A4│
                    │      │ Context Condenser (S_ctx: Facts/Constraints/ │
                    │      │ Open Issues + citations)                     │
                    │      └──────────────────────────────────────────────┘
                    ├── PromptBuilder
                    │     └─ Authority order:
                    │        [Hard Rules] → [Project Memory] → [❖ FILES]
                    │        → [S_ctx] → [Your Task/Format/Mode]
                    ├── 🛠️ ToolDispatcher (calc:/py: when explicitly asked; future)
                    ├── 📡 LLMClient (model call + cost)
                    └── 📊 Transparency panel (kept/dropped chunks, reasons)

                    ▼
        🖥️  Streamlit GUI (answer, citations, FILES block, costs, logs)
````

* The top half (Ingestion→VectorStore) is unchanged in flow, but **vectors persist as NumPy `.pkl`** (Chroma paused due to env issue). **FileManifest** is planned (path/sha/mtime/type).
* The **four agents** now include **A2 Prompt Shaper** (not only role routing; it proposes full headers), and the **Eligibility Pool** mirrors your GUI ON/OFF file controls.
* The query path stays: **Retriever → Reranker → PromptBuilder → LLMClient**, with **NLI gating + Condenser** inserted to control/condense context. Attention sliders are replaced by explicit **ON/OFF eligibility**.

---

## Ingestion & Memory

* **DocumentLoader**: discovers files under `data/doc_raw/`.

  * **Current**: plain/unformatted text (`.txt`, `.md`, `.json`, `.yml`).
  * **Planned**: rich/binary (`.pdf`, `.docx`).
* **Chunker**: token-aware overlapping windows.
* **Embedder**: E5/BGE family (configurable).
* **VectorStore**: local persistence.

  * **Current**: NumPy-backed `.pkl` snapshots (Chroma disabled temporarily).
  * **Planned**: on-disk Chroma once stable in this environment.
* **📇 FileManifest (planned)**: `path`, `sha256`, `mtime`, `type` to support deterministic inclusion and change detection.

---

## Agent-by-agent (precise responsibilities)

### A1 — Deterministic Code Injector (DCI)  ➜ “❖ FILES” section

**What:** The only agent allowed to inject **full** code/config you explicitly name (e.g., `handler.py`, `main.tf`, `docker-compose.yml`). No ranking or retrieval.

**Inputs:** your prompt; FileManifest (when available); GUI “Exact File Lock”; ON/OFF selections.
**Output:** top-level **❖ FILES** block (FULL; or **PACK** if file is huge).
**Policy (deterministic):**

* If you explicitly name a code/config file ⇒ include **FULL** (or **PACK** if over limit).
* If **Exact File Lock = ON** ⇒ retrieval path is skipped (laser task).
* Markdown/notes remain in retrieval; A1 targets code/config deterministically.

---

### A2 — Prompt Shaper (intent/domain + meta-prompt headers)

**What:** Lightweight **prompt shaper** that suggests task **intent** and **domain**, and proposes structured headers for the Super-Prompt.

**Inputs:** raw query + optional project state.
**Outputs (advisory):**

* **intent** (e.g., explain, design, implement, refactor, debug, test, review, plan, compare, decide, compute, translate, generate, …)
* **domain** (software, AWS, research, writing, legal, music, …)
* **headers**: `SYSTEM, AUDIENCE, PURPOSE, TONE, CONFIDENCE, RESPONSE DEPTH, OUTPUT FORMAT` (may suggest `CHECKLIST/EXAMPLE`)

**Implementation:**

* Uses a small LLM (e.g., GPT-4o-mini) with **deterministic templates as fallback**.
* May suggest defaults for downstream strictness (e.g., higher NLI θ for implement/debug).
* **You always review/override** in the GUI.

---

### A3 — NLI Gate (semantic keep/drop)

**What:** Filters reranked chunks via natural-language inference (entailment) to keep only those that **support** the task.

**Inputs:** query, reranked candidates, Prompt Shaper hints.
**Output:** kept chunks (+ scores); drops irrelevant/contradictory.
**Control:** **Strictness (θ)** in GUI (low = exploratory; high = strict).
**Why:** Prevents “nice-but-irrelevant” context from bloating the Super-Prompt.

---

### A4 — Context Condenser (structured pack → `S_ctx`)

**What:** Summarizes **kept** chunks into a compact, **cited** block the LLM can reliably use.

**Output:** `S_ctx` with three sections:

* **Facts** — minimal exacts (paths, code lines, IDs)
* **Constraints** — decisions, limits, acceptance criteria
* **Open Issues** — gaps/uncertainties

Small LLM is sufficient (e.g., GPT-4o-mini). This reduces tokens while preserving grounding.

---

## Prompt Orchestration

Fixed authority order (keeps facts above style):

```
[Hard Rules] → [Project Memory] → [❖ FILES] → [S_ctx] → [Your Task & Output Format] → [Optional Mode]
```

* **Hard Rules** — non-negotiables (e.g., do not alter code blocks; follow exact spec boundaries).
* **Project Memory** — persistent decisions and invariants (stack, naming, policies).
* **S\_ctx** — cited, structured pack from A4 (Facts / Constraints / Open Issues).
* **Optional Mode** — style/voice presets (e.g., INTP/ENTJ) applied after facts.

---

## Deterministic vs. Model-Driven

* **Deterministic:** A1 (DCI), File ON/OFF eligibility, PromptBuilder authority application.
* **Model-driven:** A2 (Prompt Shaper), Reranker (cross-encoder/LLM), A3 (NLI Gate), A4 (Condenser).

> Note: **Reranker** reorders candidates (scores order) and is not an agent because it does not inject/exclude by policy.

---

## End-to-End Narrative (what happens when you click)

1. You type a prompt, optionally name files, toggle **Exact File Lock**, pick model, see cost.
2. **A2 Prompt Shaper** proposes intent/domain + headers (you edit/approve).
3. **A1 DCI** injects named files into **❖ FILES** (FULL/PACK). If locked, retrieval is skipped.
4. If unlocked: **🔍 Retriever → 🏅 Reranker → A3 NLI Gate → A4 Condenser** emit **`S_ctx`** (short, cited).
5. **PromptBuilder** assembles the Super-Prompt with the fixed authority order; you can still edit.
6. **🛠️ ToolDispatcher** runs only if explicitly requested.
7. **📡 LLMClient** sends; GUI shows answer, citations, **❖ FILES**, token/cost, and **📊 Transparency** (kept/dropped with reasons).

---

## Why this fits the repo and requirements

* Preserves the modular packages (agents live in Controller).
* Adds quality levers beyond vanilla RAG (NLI gate + condenser) and makes Super-Prompt composition transparent.
* Aligns with requirements: dense top-k → rerank, prompt composition, local-first control, UI transparency.

---

## TL;DR

* **A1 DCI** — Deterministic file injection (FILES block; optional lock).
* **A2 Prompt Shaper** — Suggests intent/domain + headers; you approve.
* **A3 NLI Gate** — Keep only semantically supporting chunks.
* **A4 Condenser** — Compress to cited Facts / Constraints / Open Issues.



