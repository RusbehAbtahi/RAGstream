# RAG Stream — **Comprehensive Requirements Specification**

*Version 1.0 • 2025-08-25*

---

## 1  Purpose & Scope

RAG Stream is a **local-first retrieval-augmented generation (RAG) workbench** that lets a power-user ingest documents, deterministically include/exclude files via ON/OFF toggles or an Exact File Lock, optionally execute local tools (math / Python), and obtain a fully-cited answer from a remote or local LLM—all inside a transparent Streamlit UI with cost estimation and agent logs.

---

## 2  Stakeholders

| Role                     | Interest                                                                 |
| ------------------------ | ------------------------------------------------------------------------ |
| Product owner            | End-to-end demo & daily assistant running on a laptop (no cloud infra).  |
| Prompt-/Context-Engineer | Fine-tune templates, inspect retrieved chunks, toggle tool routing.      |
| Data engineer            | Extend ingestion pipeline, add file-watcher, experiment with embeddings. |
| Future OSS users         | Fork and replace LLM or vector DB without touching GUI / controller.     |

---

## 3  System Context

```
User ──▶ Streamlit GUI ──▶ Controller
                   ▲          │
                   │          ├──▶ A2 Prompt Shaper → headers
                   │          ├──▶ A1 DCI → ❖ FILES (lock/full/pack)
                   │          ├──▶ Retriever → Reranker → A3 NLI Gate → A4 Condenser (S_ctx)
                   │          ├──▶ PromptBuilder (authority order)
                   │          ├──▶ ToolDispatcher ──▶ {MathTool | PyTool}
                   │          ├──▶ LLMClient (OpenAI GPT-4o or local)
                   │          └──▶ Transparency / Cost / Logs
DocumentLoader ◀───┘
     ▲
     └─ Chunker ─ Embedder ─ VectorStore.add() (.pkl snapshots; Chroma paused)
```

---

## 4  Functional Requirements

### 4.1  Ingestion / Memory

| ID     | Requirement                                                           | Priority |
| ------ | --------------------------------------------------------------------- | -------- |
| ING-01 | Load `.txt`, `.md`, `.json`, `.yml`.                                  | Must     |
| ING-02 | Planned: support `.pdf`, `.docx` via drag-and-drop or watched folder. | Planned  |
| ING-03 | RecursiveTextSplitter (window = 1 024 tok, overlap = 200 tok).        | Must     |
| ING-04 | Persist vectors as NumPy `.pkl` snapshots.                            | Must     |
| ING-05 | Planned: Chroma collection on disk once stable.                       | Planned  |
| ING-06 | Planned: FileManifest with `path`, `sha`, `mtime`, `type`.            | Planned  |
| ING-07 | Emit ingestion log (docs added / skipped / updated).                  | Should   |

### 4.2  Retrieval & Agents

| ID     | Requirement                                                           | Priority |
| ------ | --------------------------------------------------------------------- | -------- |
| RET-01 | Cosine top-k search (k = 20) with embedder from 4.1.                  | Must     |
| RET-02 | Cross-encoder rerank with `mixedbread-ai/mxbai-rerank-xsmall-v1`.     | Must     |
| RET-03 | Eligibility Pool: ON/OFF checkboxes per file.                         | Must     |
| RET-04 | Exact File Lock disables retrieval and injects only named ❖ FILES.    | Must     |
| RET-05 | A3 NLI Gate filters reranked chunks by entailment with strictness θ.  | Must     |
| RET-06 | A4 Condenser emits cited `S_ctx` (Facts / Constraints / Open Issues). | Must     |
| RET-07 | Expose retriever latency in the UI status bar.                        | Should   |

### 4.3  Prompt Orchestration

| ID     | Requirement                                                                                             | Priority |
| ------ | ------------------------------------------------------------------------------------------------------- | -------- |
| ORC-01 | Build system prompt with slots: `{{question}}`, `{{❖ FILES}}`, `{{S_ctx}}`, `{{tool_output}}`.          | Must     |
| ORC-02 | Apply fixed authority order: \[Hard Rules] → \[Project Memory] → \[❖ FILES] → \[S\_ctx] → \[Task/Mode]. | Must     |
| ORC-03 | Inject `<source_i>` tags for cited chunks for UI highlighting.                                          | Must     |
| ORC-04 | Circular limit: prompt ≤ 8 k tokens incl. context & tool output.                                        | Must     |

### 4.4  Tooling

| ID      | Requirement                                                              | Priority |
| ------- | ------------------------------------------------------------------------ | -------- |
| TOOL-01 | Parse `calc:` or `py:` prefixes—route remainder to local tool.           | Must     |
| TOOL-02 | MathTool → evaluate via `sympy.sympify`, return pretty string.           | Must     |
| TOOL-03 | PyTool → run in `exec` sandbox with `asyncio` timeout = 2 s.             | Should   |
| TOOL-04 | Register new tools by subclassing `BaseTool`, auto-discover at start-up. | Should   |

### 4.5  LLM Interface

| ID     | Requirement                                                             | Priority |
| ------ | ----------------------------------------------------------------------- | -------- |
| LLM-01 | Default remote client: `gpt-4o` with temperature 0.2, max\_tokens 512.  | Must     |
| LLM-02 | Pluggable local model via `ollama run llama3:instruct`, flag `--local`. | Should   |
| LLM-03 | Stream tokens to UI with first byte < 1 s.                              | Must     |
| LLM-04 | Retry on HTTP 429/5xx with exponential back-off max 3 tries.            | Should   |
| LLM-05 | Provide estimated cost for composed prompt.                             | Must     |

### 4.6  UI / App

| ID    | Requirement                                                                                     | Priority |
| ----- | ----------------------------------------------------------------------------------------------- | -------- |
| UI-01 | Prompt box, ON/OFF file checkboxes, Exact File Lock, Prompt Shaper panel, Agent toggles, Modes. | Must     |
| UI-02 | Super-Prompt preview (editable).                                                                | Must     |
| UI-03 | Transparency panel shows kept/dropped chunks with reasons.                                      | Must     |
| UI-04 | Show ❖ FILES block and `S_ctx`.                                                                 | Must     |
| UI-05 | Model picker + cost estimator.                                                                  | Must     |
| UI-06 | Answer + citations view.                                                                        | Must     |
| UI-07 | Download chat history as Markdown with citations.                                               | Should   |
| UI-08 | Dark & light theme auto-switch (`streamlit-theme`).                                             | Could    |

---

## 5  Non-Functional Requirements

| Category          | Target                                                               |
| ----------------- | -------------------------------------------------------------------- |
| **Latency**       | < 3 s p95 prompt→first token with 1 M-token `.pkl` snapshot store.   |
| **Memory**        | ≤ 6 GB RAM peak (embeddings loaded on demand).                       |
| **Extensibility** | Add a new tool, agent, or embedding model without touching > 1 file. |
| **Observability** | Structured logs JSON → `ragstream/utils/logging.py`.                 |
| **Test coverage** | Unit 80 % (`pytest` + `hypothesis` for splitter & retriever).        |
| **Security**      | Tool sandbox runs in separate process; no network in math/py tools.  |
| **Licensing**     | Apache-2.0 except external models retaining original licenses.       |
## 6  Technology Stack

| Layer           | Library / Service                                   | Version (Aug 2025)                |
| --------------- | --------------------------------------------------- | --------------------------------- |
| GUI             | Streamlit                                           | 1.38                              |
| Embeddings      | `bge-large-en-v3`, `E5-Mistral` (optional)          | via `sentence_transformers = 3.0` |
| Vector Store    | NumPy `.pkl` snapshots (current)                    | -                                 |
| Planned DB      | Chroma                                              | 0.10                              |
| Cross-encoder   | `mixedbread-ai/mxbai-rerank-xsmall-v1`              | 🤗 `cross-encoder = 0.6`          |
| LLM API         | OpenAI (`openai>=1.15.0`)                           | GPT-4o                            |
| Local LLM (opt) | Ollama                                              | 0.2                               |
| Math            | SymPy                                               | 1.13                              |
| Testing         | pytest, coverage, hypothesis                        | latest                            |
| Packaging       | Poetry / PEP 621 (`pyproject.toml`)                 | 1.8                               |
| CI              | GitHub Actions (`python-versions {3.10,3.11,3.12}`) | -                                 |

---

## 7  Directory / Module Tree

```
Here’s the corrected tree with agents in their own files and the controller just orchestrating them:

```
.
├── .gitignore
├── data/
│   ├── chroma_db/         # planned
│   └── doc_raw/
├── ragstream/
│   ├── __init__.py
│   ├── app/
│   │   ├── controller.py        # orchestrates agents A1–A4 (implemented in app/agents/)
│   │   ├── ui_streamlit.py
│   │   └── agents/
│   │       ├── __init__.py
│   │       ├── a1_dci.py            # A1 Deterministic Code Injector
│   │       ├── a2_prompt_shaper.py  # A2 Prompt Shaper
│   │       ├── a3_nli_gate.py       # A3 NLI Gate
│   │       └── a4_condenser.py      # A4 Context Condenser
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── loader.py            # DocumentLoader
│   │   ├── chunker.py           # Chunker
│   │   ├── embedder.py          # Embedder
│   │   └── vector_store.py      # VectorStore
│   ├── retrieval/
│   │   ├── __init__.py
│   │   ├── attention.py         # replaced by eligibility toggles
│   │   ├── reranker.py          # Reranker
│   │   └── retriever.py         # Retriever
│   ├── orchestration/
│   │   ├── __init__.py
│   │   ├── prompt_builder.py    # PromptBuilder
│   │   └── llm_client.py        # LLMClient
│   ├── tooling/
│   │   ├── __init__.py
│   │   ├── base_tool.py         # BaseTool
│   │   ├── math_tool.py         # MathTool
│   │   ├── py_tool.py           # PyTool
│   │   ├── registry.py          # ToolRegistry
│   │   └── dispatcher.py        # ToolDispatcher
│   └── utils/
│       ├── __init__.py
│       ├── logging.py
│       └── paths.py
└── pyproject.toml  (or requirements.txt)
```

```

---

## 8  Open Issues / Risks

| Risk                                                              | Mitigation                                                   |
| ----------------------------------------------------------------- | ------------------------------------------------------------ |
| Cross-encoder latency on CPU.                                     | Cache top-32 chunks, run cross-encoder only once.            |
| SymPy sandbox leakage via `eval`.                                 | Use `sympy.parsing.sympy_parser` + restricted globals.       |
| Streamlit session state resets when file watcher triggers reload. | Debounce file-watch events; persist state to JSON.           |
| Embedding model size ≈ 2 GB > memory on low-spec laptops.         | Offer `bge-base-v1` fallback; lazy-load model on first call. |
| FileManifest not yet implemented.                                 | Plan incremental rollout after `.pkl` stable.                |
| Chroma paused due to environment issues.                          | Resume once stable in deployment environment.                |

---

## 9  Acceptance Criteria (5-day MVP)

1. Ingest at least **1 000** Markdown / text pages; run dense + rerank retrieval; answer in ≤ 5 s p95.
2. ❖ FILES block deterministically injects named files and respects Exact File Lock.
3. `S_ctx` (Facts / Constraints / Open Issues) generated with citations.
4. Prompt assembled in fixed authority order.
5. Transparency panel shows kept/dropped chunks with reasons.
6. Cost estimator visible and accurate.
7. `calc: 3*(4+5)` prompt returns `27` inline.
8. Streamlit UI shows citations and ❖ FILES block.
9. All unit tests pass; `pytest` reports ≥ 80 % coverage.

---

## 10  Glossary

| Term                   | Meaning                                                       |
| ---------------------- | ------------------------------------------------------------- |
| **RAG**                | Retrieval-Augmented Generation.                               |
| **Eligibility Pool**   | ON/OFF per-file toggles controlling retrieval.                |
| **Exact File Lock**    | Mode skipping retrieval and injecting only named ❖ FILES.     |
| **❖ FILES**            | Deterministically injected file contents (via A1).            |
| **S\_ctx**             | Condensed cited context (Facts / Constraints / Open Issues).  |
| **Prompt Shaper (A2)** | Suggests intent/domain + headers.                             |
| **NLI Gate (A3)**      | Filters reranked chunks by entailment.                        |
| **Condenser (A4)**     | Compresses context to `S_ctx`.                                |
| **ToolDispatcher**     | Router that detects and executes local tools before LLM call. |
| **Chunk**              | Fixed-size text window (≈ 500 tokens) stored with embedding.  |

---

> **Status:** Spec validated against Architecture\_2.md (commit *HEAD* on 2025-08-25). Any structural change should update sections 4 & 7 and increment spec version.
