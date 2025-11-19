# RAG Stream — **Comprehensive Requirements Specification**

*Version 0.9 • 2025-08-05*

---

## 1  Purpose & Scope

RAG Stream is a **local-first retrieval-augmented generation (RAG) workbench** that lets a power-user ingest arbitrary documents, steer retrieval weights via interactive *Attention Sliders*, optionally execute local tools (math / Python), and obtain a fully-cited answer from a remote or local LLM—all inside a transparent Streamlit UI.

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
                   │          ├──▶ Retriever ──▶ VectorStore (Chroma on-disk)
                   │          │
                   │          ├──▶ AttentionWeights
                   │          │
                   │          ├──▶ ToolDispatcher ──▶ {MathTool | PyTool}
                   │          │
                   │          ├──▶ PromptBuilder ──▶ LLMClient (OpenAI GPT-4o)
                   │          │
                   │          └──▶ Logging / Paths utilities
DocumentLoader ◀───┘          │
     ▲                         └──▶ Settings (env / .env / CLI)
     └─ Chunker ─ Embedder ─ VectorStore.add()
```

---

## 4  Functional Requirements

### 4.1  Ingestion / Memory

| ID     | Requirement                                                                 | Priority |
| ------ | --------------------------------------------------------------------------- | -------- |
| ING-01 | Load `.pdf`, `.md`, `.txt`, `.docx` from *drag-and-drop* or watched folder. | Must     |
| ING-02 | RecursiveTextSplitter (window = 1 024 tok, overlap = 200 tok).              | Must     |
| ING-03 | Default embedding model **BGE-Large-v3** via `sentence_transformers`.       | Must     |
| ING-04 | Persist and delta-update Chroma collection on disk (`./data/chroma_db`).    | Must     |
| ING-05 | Emit ingestion log (docs added / skipped / updated).                        | Should   |

### 4.2  Retrieval & Ranking

| ID     | Requirement                                                           | Priority |
| ------ | --------------------------------------------------------------------- | -------- |
| RET-01 | Cosine top-k search (k = 20) with embedder from 4.1.                  | Must     |
| RET-02 | Multiply each document score by UI-supplied slider weight  wᵢ∈\[0,1]. | Must     |
| RET-03 | Cross-encoder rerank with `mixedbread-ai/mxbai-rerank-xsmall-v1`.     | Must     |
| RET-04 | Expose retriever latency in the UI status bar.                        | Should   |

### 4.3  Prompt Orchestration

| ID     | Requirement                                                                       | Priority |
| ------ | --------------------------------------------------------------------------------- | -------- |
| ORC-01 | Build system prompt with slots: `{{question}}`, `{{context}}`, `{{tool_output}}`. | Must     |
| ORC-02 | Inject `<source_i>` tags for cited chunks for UI highlighting.                    | Must     |
| ORC-03 | Circular limit: prompt ≤ 8 k tokens incl. context & tool output.                  | Must     |

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

### 4.6  UI / App

| ID    | Requirement                                                         | Priority |
| ----- | ------------------------------------------------------------------- | -------- |
| UI-01 | Two-pane layout: left = prompt & sliders, right = answer & sources. | Must     |
| UI-02 | Show chunk pills with score × weight × rerank; click opens raw doc. | Should   |
| UI-03 | Dark & light theme auto-switch (`streamlit-theme`).                 | Could    |
| UI-04 | Download chat history as Markdown with citations.                   | Should   |

---

## 5  Non-Functional Requirements

| Category          | Target                                                              |
| ----------------- | ------------------------------------------------------------------- |
| **Latency**       | < 3 s p95 prompt→first token with 1 M-token Chroma store on M2-Pro. |
| **Memory**        | ≤ 6 GB RAM peak (embeddings loaded on demand).                      |
| **Extensibility** | Add a new tool or embedding model without touching > 1 file.        |
| **Observability** | Structured logs JSON → `ragstream/utils/logging.py`.                |
| **Test coverage** | Unit 80 % (`pytest` + `hypothesis` for splitter & retriever).       |
| **Security**      | Tool sandbox runs in separate process; no network in math/py tools. |
| **Licensing**     | Apache-2.0 except external models retaining original licenses.      |

---

## 6  Technology Stack

| Layer           | Library / Service                                   | Version (Aug 2025)                |
| --------------- | --------------------------------------------------- | --------------------------------- |
| GUI             | Streamlit                                           | 1.38                              |
| Embeddings      | `bge-large-en-v3`, `E5-Mistral` (optional)          | via `sentence_transformers = 3.0` |
| Vector DB       | Chroma                                              | 0.10                              |
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
.
├── .gitignore
├── data/
│   ├── chroma_db/
│   └── doc_raw/
├── ragstream/
│   ├── __init__.py
│   ├── app/
│   │   ├── controller.py
│   │   └── ui_streamlit.py
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
│   │   ├── attention.py         # AttentionWeights
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

---

## 8  Open Issues / Risks

| Risk                                                              | Mitigation                                                   |
| ----------------------------------------------------------------- | ------------------------------------------------------------ |
| Cross-encoder latency on CPU.                                     | Cache top-32 chunks, run cross-encoder only once.            |
| SymPy sandbox leakage via `eval`.                                 | Use `sympy.parsing.sympy_parser` + restricted globals.       |
| Streamlit session state resets when file watcher triggers reload. | Debounce file-watch events; persist state to JSON.           |
| Embedding model size ≈ 2 GB > memory on low-spec laptops.         | Offer `bge-base-v1` fallback; lazy-load model on first call. |

---

## 9  Acceptance Criteria (5-day MVP)

1. Ingest at least **1 000** Markdown pages; run dense + rerank retrieval; answer in ≤ 5 s p95.
2. Attention slider demonstrably changes ranking order live.
3. `calc: 3*(4+5)` prompt returns `27` inline.
4. Streamlit UI shows citations and chunk pop-ups.
5. All unit tests pass; `pytest` reports ≥ 80 % coverage.

---

## 10  Glossary

| Term                 | Meaning                                                       |
| -------------------- | ------------------------------------------------------------- |
| **RAG**              | Retrieval-Augmented Generation.                               |
| **Attention Slider** | UI widget assigning manual weights to per-document groups.    |
| **ToolDispatcher**   | Router that detects and executes local tools before LLM call. |
| **Chunk**            | Fixed-size text window (≈ 500 tokens) stored with embedding.  |

---

> **Status:** Spec validated against current repo layout (commit *HEAD* on 2025-08-05). Any structural change should update sections 4 & 7 and increment spec version.
