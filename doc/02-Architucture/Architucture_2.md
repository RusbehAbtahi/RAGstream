

```text
                                     ┌───────────────────────────────────┐
                                     │      🔄  Ingestion Pipeline       │
                                     │───────────────────────────────────│
 User adds / updates docs  ─────────►│ 1  DocumentLoader (paths / watch) │
                                     │ 2  Chunker  (recursive splitter)  │
                                     │ 3  Embedder (E5 / BGE model)      │
                                     │ 4  VectorStore.add() (Chroma)     │
                                     └───────────────────────────────────┘
                         ▲              ▲
                         │ builds       │ builds
                         │              │
                         │              └──▶ 📇 FileManifest (path, sha, mtime, type)
                         │
╔═════════════════════════════════════════════════════════════════════════════╗
║                               MAIN QUERY FLOW                               ║
╚═════════════════════════════════════════════════════════════════════════════╝
                                                                           
[User Prompt] ───▶ 🎛️  Streamlit GUI
                    ├── Prompt box (you)
                    ├── ON/OFF file checkboxes  (+ “Exact File Lock”)
                    ├── Role presets (REQ/ARCH/CODE/TEST)
                    ├── Agent toggles (A1..A4), Mode (INTP/ENTJ…)
                    ├── Model picker + cost estimator
                    └── Super-Prompt preview (editable, source of truth)

                    ▼
                 🧠 Controller
                    ├── A2 Role Router (suggest; your presets override)
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
                    ├── 🛠️ ToolDispatcher (calc:/py: when explicitly asked)
                    ├── 📡 LLMClient (model call + cost)
                    └── 📊 Transparency panel (kept/dropped chunks, reasons)

                    ▼
        🖥️  Streamlit GUI (answer, citations, FILES block, costs, logs)
```

* The top half (Ingestion→VectorStore) and your original query path (Retriever→Reranker→PromptBuilder→LLMClient) remain as you designed. I’ve added **FileManifest** and the **four agents** in the controller path, plus an **Eligibility Pool** that matches your ON/OFF checkboxes.&#x20;
* Class-level mapping stays compatible with your UML: `DocumentLoader`, `Chunker`, `Embedder`, `VectorStore`, `Retriever`, `Reranker`, `PromptBuilder`, `LLMClient`, `ToolDispatcher`, `Controller`, `StreamlitUI`. We’re just inserting agent calls inside `Controller`, which is precisely how your packages are already arranged.&#x20;
* This still satisfies your requirements spec (dense top-k → cross-encoder rerank; prompt composition; UI transparency). Only the **attention sliders** are conceptually replaced by **ON/OFF eligibility**, which your spec tolerates because weights were always a UI concern, not a hard contract.&#x20;

---

## Agent-by-agent (precise responsibilities, simple and practical)

### Agent 1 — Deterministic Code Injector (DCI)  ➜ “❖ FILES” section

**What it is:** The **only** agent allowed to inject full code/config files you explicitly name (e.g., `handler.py`, `main.tf`, `docker-compose.yml`). It does *no* ranking or retrieval.
**Inputs:** your prompt; FileManifest; GUI “Exact File Lock” toggle; ON/OFF file selections.
**Outputs:** a **FILES** block added to the Super-Prompt, in this standard shape:

```
## FILES (locked=yes/no)
- C:\path\to\handler.py   [included verbatim]
```

```python
# handler.py
...entire content or PACK (if very large)...
```

**Policy (deterministic):**

* If you **explicitly name** a code/config file ⇒ include it **FULL** (or **PACK** if it exceeds a safe limit).
* If **Exact File Lock = ON** ⇒ no other documents may enter from retrieval (you chose a laser task).
* Never touches Markdown docs; those are handled by retrieval.
  **Why here:** Guarantees your referenced files are present *exactly*, a capability missing in a vanilla RAG path. (Your original design couldn’t *guarantee* deterministic file presence.)&#x20;

---

### Agent 2 — Role Router (soft suggestion)

**What it is:** A tiny classifier that reads your prompt and proposes `{REQ, ARCH, CODE, TEST}`.
**Inputs:** your prompt text (+ optional recent chat history with decay if you enable it).
**Outputs:** role suggestions + confidence.
**Authority:** **Your role presets/checkboxes always override** its suggestion.
**Why here:** Reduces clicks when you forget to flip a role, but never steals control. This matches your “commander–autopilot” ethos and keeps the system aligned with your Requirements/Architecture separation.&#x20;

---

### Agent 3 — NLI Gate (semantic keep/drop)

**What it is:** A **gatekeeper** that filters retrieved chunks using textual entailment with the active role(s).
**Inputs:** query, reranked candidates, active role(s).
**Outputs:** only **supporting** chunks (keeps), with scores; drops contradictory/irrelevant ones.
**Control:** you expose a **Strictness (θ)** knob in the GUI (low = exploratory, high = strict).
**Why here:** Prevents “nice-but-irrelevant” context from entering your Super-Prompt—something plain dense+rerank can’t guarantee. It’s the single biggest quality/correctness upgrade beyond your baseline. (Your spec already has rerank; the NLI filter sits right after it.)&#x20;

---

### Agent 4 — Context Condenser (structured pack)

**What it is:** A summarizer that turns the **kept** chunks into a compact, **cited** block the LLM can reliably use.
**Inputs:** kept chunks + metadata.
**Outputs:** `S_ctx` with **three sections**:

* **Facts** (copy minimal exacts like ARNs, paths, code lines)
* **Constraints** (decisions, security/cost limits, acceptance criteria)
* **Open Issues** (what’s missing/uncertain)

**Why here:** Stops prompt bloat, increases grounding, and gives you a single, inspectable block below the ❖ FILES section. Fits cleanly into your existing `PromptBuilder` and UI (citations already part of your spec).&#x20;

---

## The rest of the pipeline (what stays as-is, with small clarifications)

* **Ingestion Pipeline**: unchanged; adds **FileManifest** (path, sha256, mtime, type) so Agent 1 can resolve exact files deterministically. Your `DocumentLoader → Chunker → Embedder → VectorStore` remains the backbone.&#x20;
* **Retriever & Reranker**: unchanged core; now take the **Eligibility Pool** (from ON/OFF checkboxes) and any role filter (from you / A2). This is still “dense top-k → cross-encoder rerank,” as in your spec.&#x20;
* **PromptBuilder**: add the **Authority Order** you want:
  `[Hard Rules] → [Project Memory] → [❖ FILES] → [S_ctx] → [Your Task & Output Format] → [Optional Mode (INTP/ENTJ…)]`.
  This aligns with your PromptGenerator schema and prevents style from outranking facts.&#x20;
* **ToolDispatcher**: remains opt-in (`calc:` / `py:`), exactly as in your current design.&#x20;
* **LLMClient**: same; add a **cost estimator** that reads token counts from the Super-Prompt and your chosen model pricing (your audit already suggested small client add-ons like this).&#x20;
* **Streamlit UI**: same layout; swap sliders → **ON/OFF checkboxes**; add toggles for **Exact File Lock** and **Agent Strictness**; keep the **Super-Prompt preview** fully editable (the final source of truth).&#x20;

---

## End-to-end narrative (what happens when you click)

1. **You** type a prompt and (optionally) name explicit files; choose roles/presets; turn **Exact File Lock** ON or OFF; pick model; see estimated cost.&#x20;
2. **A2** proposes roles (you can ignore).
3. **A1** injects your named code/config files **verbatim** into `❖ FILES`; if **lock ON**, this alone may be your whole context.
4. If **lock OFF**: **Retriever → Reranker → A3 NLI Gate → A4 Condenser** produce `S_ctx` (short, cited).
5. **PromptBuilder** assembles the Super-Prompt in the fixed authority order; **you can still edit it**.&#x20;
6. **ToolDispatcher** runs only if you asked for it.
7. **LLMClient** sends; UI shows answer, citations, ❖ FILES, token/cost, and “kept vs dropped” evidence with reasons.&#x20;

---

## Why this fits your repo and specs without churn

* It **preserves** your modular classes and package tree (only adds Agent calls inside `Controller`), exactly the way your **UML** and **Architecture** files intend.
* It **completes** your **Requirements** by adding the two missing quality levers professionals rely on (NLI gate + condenser) and by formalizing the **Super-Prompt** composition you already standardize in **PromptGenerator**.
* It **aligns** with the earlier **audit** suggestions (explicit value objects like `DocScore`, truncation/cost awareness, simple logging) without forcing any heavy framework.&#x20;

---

## TL;DR (your four must-have agents, one line each)

* **A1 DCI:** Include named code/config files **verbatim** (or structured PACK) as a top **FILES** block. Deterministic.
* **A2 Router:** Suggest roles; you’re the boss.
* **A3 NLI Gate:** Only let **supporting** chunks through (semantic keep/drop).
* **A4 Condenser:** Compress kept chunks into **Facts / Constraints / Open Issues** with citations.

This is the simplest, most **controllable** agentic layer over your existing system that meaningfully increases correctness and focus—while keeping *you* in command.
