

## ✅ 1) Architectural Completeness & Clarity (Ti)

### Strengths

* Clear end-to-end narrative and controller-centric design with explicit agents: A1 (Deterministic Code Injector), A2 (Prompt Shaper), A3 (NLI Gate), A4 (Condenser). The System Context diagram and FRs consistently reference this pipeline, including `❖ FILES`, `S_ctx`, authority order, and transparency/cost surfaces.&#x20;
* Deterministic controls are first-class: ON/OFF eligibility toggles and “Exact File Lock” disable retrieval and inject only named files (aligns GUI, controller, and acceptance criteria).&#x20;
* Scope is crisp for Pre-MVP: ingestion limited to plaintext formats; Chroma is explicitly “planned,” with current persistence via NumPy `.pkl` snapshots. This reduces integration risk and keeps performance predictable.&#x20;

### Minor structural nits

* Directory tree still lists `retrieval/attention.py` with a comment “replaced by eligibility toggles,” which can confuse implementers since sliders are no longer part of the spec/UI. Consider renaming the module or removing it from the tree to prevent drift.&#x20;

---

## 🧪 2) Technical Correctness & Testability (Te)

### What’s solid

* Functional Requirements are largely verifiable: RET-04 (File Lock behavior), ORC-02 (authority order), ORC-04 (8k cap), and UI-03 (transparency panel) all have observable outcomes; Acceptance Criteria reference many of these behaviors directly.&#x20;
* Non-functional targets (p95 <3s; ≤6GB RAM) are concrete; security constraints isolate tools; observability points to a unified logger—good for perf baselines and incident analysis.&#x20;

### Gaps / ambiguities that impede testing

1. Embedding model is implied in the Tech Stack (“bge-large-en-v3”, “E5-Mistral”) but not normed in FRs; ING/RET sections don’t specify the default embedder contract, making accuracy/latency comparisons non-deterministic across runs. Add an explicit default and an interface requirement (ID).&#x20;
2. RET-01 “cosine top-k” over a `.pkl` store is underspecified: the spec should state whether an in-memory index (e.g., FAISS or NumPy cosine on a loaded matrix) is required for latency targets—and how it’s rebuilt from snapshots. Otherwise p95 guarantees are hard to verify.&#x20;
3. A3 NLI Gate lacks acceptance-testable parameters: define θ (strictness) default, range, and a deterministic test harness (e.g., given a known contradictory chunk, it must be dropped at θ≥X).&#x20;
4. A4 Condenser’s `S_ctx` format is named (Facts/Constraints/Open Issues), but the citation scheme isn’t bound to `<source_i>` mapping rules. Define how `S_ctx` cites sources so UI highlighting (ORC-03) is consistent.&#x20;
5. LLM-05 “estimated cost” needs a tolerance (e.g., ±10%) and a pricing reference (input/output token accounting) to be testable; otherwise “accurate” is subjective. Tie this to model selection in the UI.&#x20;
6. ORC-04 hard-caps at 8k tokens while the default model often supports more. If intentional for speed, state rationale or make it a configurable limit with a default, so test cases don’t become obsolete with model changes.&#x20;
7. Security: TOOL-03 mentions `exec` with timeout; Non-Functional says “separate process; no network.” Add a normative constraint to forbid `import socket`/`requests` (denylist) and require a subprocess/sandbox, to make this verifiable.&#x20;

---

## 🎛️ 3) UI/UX & Observability (Se)

### What’s working

* UI is specified around the new mental model (toggle/lock, Prompt Shaper panel, agent toggles, Super-Prompt preview, transparency, cost). This mirrors the controller’s decision log and is checkable via Acceptance Criteria.&#x20;

### What to tighten

* Add a UI requirement for a visible “Retrieval skipped (Exact File Lock ON)” badge/event so users can’t misinterpret empty retrieval results. This also eases black-box testing of RET-04.&#x20;
* Observability calls out JSON logs but doesn’t bind agent decisions to traceable fields (e.g., `a3_dropped[]`, `a4_kept[]`, reasons). Add a logging schema requirement so the transparency panel can be validated from logs.&#x20;

---

## ⚙️ 4) Feasibility & Performance Risks (Te/Se)

* p95 <3s with 1M-token corpus plus cross-encoder and NLI may be tight on CPU, depending on implementation (RET-02/RET-05). Consider scoping p95 target by hardware profile (the spec earlier references M2-class; keep that) and add a “degrade path” (e.g., skip A3 above size N) for large corpora.&#x20;
* Chroma is “planned”; success depends on the `.pkl` → in-memory search pathway. Without an explicit indexing requirement, perf may regress as data grows.&#x20;

---

## 🛠️ 5) Concrete, Minimal Changes (ready to merge into the spec)

1. Add FR “ING-08 (Must): Default embedder = `bge-large-en-v3` with cosine metric; allow override via config; record model name+dim in snapshot metadata.”&#x20;
2. Add FR “RET-08 (Must): Build an in-memory ANN or vector-matrix index from `.pkl` at startup; document rebuild time target; expose index stats in logs.”&#x20;
3. Amend RET-05: define `θ ∈ [0,1]`, default 0.6; add an acceptance bullet “A3 drops a known contradiction at θ≥0.6 and keeps it at θ≤0.3.”&#x20;
4. Amend ORC-03/`S_ctx`: specify citation mapping, e.g., each `S_ctx` bullet carries `<source_i>` IDs that correspond 1:1 to UI highlights; define validation rule in Acceptance.&#x20;
5. Amend LLM-05: “Cost estimator within ±10% using current model prices; show input/output token counts and assumed price per 1k tokens.” Add an acceptance bullet for this.&#x20;
6. Amend TOOL-03 + Security: must run user code in a separate, no-network subprocess with a restricted builtins set; denylist importing `socket`, `subprocess`, `os.system`, `ctypes`; add a unit test to verify denial.&#x20;
7. UI-new: “UI-09 (Must): Display a persistent badge when Exact File Lock is enabled and retrieval is bypassed.” Add to Acceptance.&#x20;
8. Logging schema: define a minimal agent-trace contract (kept/dropped IDs, reasons, θ, ranks) so Transparency panel is reproducible from logs. Add to Observability.&#x20;
9. Housekeeping: remove or rename `retrieval/attention.py` to avoid misreads; if kept, specify it as a shim for legacy tests only.&#x20;

---

## 📊 Final Assessment & Scorecard

| Aspect                                  | Score | Rationale / Key Notes                                                                                                  |
| --------------------------------------- | :---: | ---------------------------------------------------------------------------------------------------------------------- |
| Architectural clarity & alignment       |  9/10 | Agents, determinism, and authority order are codified across diagram, FRs, and acceptance. Minor module naming drift.  |
| Functional completeness                 |  8/10 | Core flows covered; embedder/index details and NLI parameters need binding to be fully testable.                       |
| Testability (acceptance + unit targets) |  8/10 | Good coverage goals; add θ tests, cost tolerance, ingestion logs, and lock badge checks.                               |
| Security & tooling safety               |  7/10 | Exec timeout noted; require process isolation + denylist to meet stated security NFRs.                                 |
| Performance realism                     |  7/10 | Tight p95 with cross-encoder + NLI on CPU; require explicit indexing and degrade paths.                                |
| Observability & transparency            |  8/10 | Panels/logs called out; add agent trace schema to ensure reproducibility.                                              |

**Bottom line:** The spec is coherent and MVP-ready, with strong determinism and transparency. Add the small normative details above (embedder/index, NLI θ, `S_ctx` citation mapping, cost tolerance, sandbox guarantees, and explicit lock UI state) to make it fully testable and production-credible without changing the overall architecture.&#x20;
