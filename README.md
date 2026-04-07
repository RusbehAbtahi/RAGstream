# RAGstream

RAGstream is a local-first RAG workbench for building transparent, controllable pipelines around large language models. It ingests project documents into local vector stores, runs a deterministic retrieval and reranking path, and assembles an explicit Super-Prompt that can be sent either to the ChatGPT UI or to APIs. LLM-based stages are routed through a neutral Agent Stack (`AgentFactory`, `AgentPrompt`, `llm_client`) so that agent behavior is defined by JSON configurations rather than scattered prompt logic.

A0_PreProcessing, A2_PromptShaper, project-scoped ingestion, and Retrieval are implemented and wired. ReRanker is also implemented in code and currently being redesigned after practical evaluation. Memory and tag-aware history management are under active development: the current GUI already exposes a development-side memory prototype, while the durable history ingestion and retrieval path remains under construction.

RAGstream is also already deployed on AWS. The current deployment uses GitHub Actions for image build/push, Amazon ECR as the image registry, EC2 + Docker for runtime, nginx for reverse proxy and TLS termination, Route 53 for DNS, SSM Parameter Store for secrets, and EBS-backed persistent runtime data outside the image.

The emphasis here is transparent RAG: human-agent orchestration, deterministic where possible, and explicit about which parts are LLM-driven and which parts are retrieval, selection, or control logic.

---

## Deployment & DevOps

RAGstream already has a working Phase-1 deployment path. Public traffic goes through HTTPS to nginx on EC2, and the application runs inside Docker behind the reverse proxy. Runtime project data is stored outside the image so that ingested files and Chroma databases survive container replacement. Detailed operational steps live in `RAGstream_AWS_Deployment_Guide_v02.md` and `RAGstream_HTTP_Proxy_Arch.md`.

```mermaid
flowchart LR
  DEV[Developer] --> GH[GitHub Repository]
  GH --> GA[GitHub Actions]
  GA --> ECR[Amazon ECR]
  ECR --> EC2[EC2 Runtime]
  EC2 --> DOCKER[Docker Container]
  DOCKER --> NGINX[nginx Reverse Proxy]
  NGINX --> HTTPS[HTTPS Endpoint]
```

```mermaid
flowchart LR
  USER[Browser] --> DNS[Route 53]
  DNS --> EC2[EC2 Public IP]
  EC2 --> NGINX[nginx :80/:443]
  NGINX --> APP[Docker / Streamlit]
  APP --> DATA[EBS-backed runtime data]
  EC2 --> SSM[SSM Parameter Store]
```

Near-term deployment direction remains incremental rather than architectural replacement. The current path stays GitHub Actions -> ECR -> EC2 -> Docker -> nginx, while later authentication and user-facing control can be extended further, for example with Cognito-based flows that are already documented as future work in the deployment and GUI requirements.

---

## Architecture

At a high level, RAGstream keeps ingestion and retrieval separated from generation, runs a linear 8-step RAG pipeline inside a Controller, and uses a neutral Agent Stack (`AgentFactory` + `AgentPrompt` + `llm_client`) for all LLM-based stages.

```mermaid
flowchart TD

  subgraph "Ingestion / Memory"
    IM["IngestionManager"]
    LDR["DocumentLoader"]
    CHK["Chunker"]
    EMB["Embedder (OpenAI text-embedding-3-large)"]
    VS["VectorStore (Chroma, on-disk)"]
    FM["FileManifest"]
    MEM["History / Tags (under development)"]

    IM --> LDR --> CHK --> EMB --> VS
    IM --> FM
    MEM --> VS
  end

  subgraph "Application"
    UI["Streamlit GUI"]
    CTRL["Controller"]

    subgraph "RAG Pipeline"
      A0["A0_PreProcessing"]
      A2["A2 PromptShaper"]
      RET["Retrieval"]
      RRK["ReRanker"]
      A3["A3 NLI Gate"]
      A4["A4 Condenser"]
      A5["A5 Format Enforcer"]
      PB["PromptBuilder"]
    end

    subgraph "Agent Stack"
      AF["AgentFactory"]
      AP["AgentPrompt"]
      LLM["llm_client"]
    end
  end

  UI --> CTRL
  CTRL --> A0 --> A2 --> RET --> RRK --> A3 --> A4 --> A5 --> PB

  A2 --> AF
  A3 --> AF
  A4 --> AF
  A5 --> AF
  AF --> AP --> LLM

  RET --> VS
```

### Design principles

- **Local-first, inspectable**  
  Project data lives in a local directory tree (documents, Chroma DBs, logs, JSON configs). The same relative runtime structure is preserved on AWS through the EC2 bind mount.

- **Explicit file and context control**  
  Ingestion and retrieval keep track of which files, chunks, and later history items are eligible to influence a run.

- **Agent Stack as neutral infrastructure**  
  A2, A3, A4, A5, and future helper agents use a neutral, stateless Agent Stack. A0_PreProcessing remains primarily deterministic, with optional LLM help later.

- **Separation of concerns**  
  Ingestion, retrieval, agent logic, controller orchestration, and GUI remain separate packages. The Controller wires stages together without hiding them.

- **LLM-neutral**  
  `llm_client` talks to OpenAI models today and is designed so that future backends can be added without changing stage contracts.

- **Transparent evolution path**  
  The implementation is documented through requirements, UML, architecture, deployment notes, and implementation-status snapshots so that code and documentation can evolve in a controlled way.

---

## Components

### Ingestion & Memory

Static documents are ingested through a deterministic pipeline.

- **Loader (`ingestion/loader.py`)**  
  Walks a raw document directory (`data/doc_raw/<project>/`) and reads the supported source files.

- **Chunker (`ingestion/chunker.py`)**  
  Splits each document into chunks with configurable size and overlap. The current implementation is deterministic and character-based.

- **Embedder (`ingestion/embedder.py`)**  
  Uses OpenAI `text-embedding-3-large` (configurable) to embed chunks into vectors.

- **Vector stores**  
  - **Document store**: ChromaDB collections under `data/chroma_db/<project>/`.  
  - **History store**: a separate tagged history layer is planned and partially reflected in the architecture and GUI work, but is not yet complete as a durable production path.

- **File manifest (`ingestion/file_manifest.py`)**  
  A JSON manifest tracks each raw file (path, hash, mtime, size) so that ingestion can update only changed content and keep the persistent store traceable.

Memory management is under active development. The current GUI already contains a development-side memory panel and tag semantics, while the durable history log, history embeddings, and tag-aware retrieval rules are still being built from the requirements and backlog.

### Retrieval & Ranking

Retrieval and reranking are separate deterministic stages.

- **Retrieval (`retrieval/retriever.py`)**  
  - Current implementation: project-aware dense retrieval using OpenAI embeddings, query splitting, and p-norm aggregation over query pieces.  
  - Current agreed next direction: hybrid first-pass retrieval with dense retrieval + SPLADE + RRF.

- **ReRanker (`retrieval/reranker.py`)**  
  - Current implementation: CPU-based cross-encoder reranking with `cross-encoder/ms-marco-MiniLM-L-12-v2`, dynamic chunk cleaning, and direct reranked ordering.  
  - Current agreed next direction: bounded ColBERT reranking on the Retrieval candidate band, with query splitting and fused ranking instead of full ranking replacement.

The current practical conclusion is simple: Retrieval already works well enough to serve as the backbone; the current ReRanker exists in code but is being replaced as a long-term ranking strategy.

### Agents inside the Controller

LLM-based stages are orchestrated through the Agent Stack.

- `AgentFactory` loads the JSON config for a given agent name/version and builds a configured `AgentPrompt`.
- `AgentPrompt` holds the neutral prompt-composition and validation logic.
- `llm_client` executes the actual model call.

On top of this infrastructure, the pipeline uses concrete stages:

- **A0_PreProcessing**  
  Deterministic normalization and schema mapping from raw prompt text into the internal SuperPrompt structure.

- **A2 PromptShaper**  
  Chooser-style agent that classifies `system`, `audience`, `tone`, `depth`, and `confidence` from `task`, `purpose`, and `context`.

- **A3 NLI Gate**  
  Current agreed direction: Multi-Chooser-style chunk labeling and duplicate marking on the reranked candidate set.

- **A4 Context Condenser**  
  Writer-style agent that produces `S_CTX_MD` from the selected chunks.

- **A5 Format Enforcer**  
  Writer / Extractor-style agent that normalizes the final response contract.

- **PromptBuilder**  
  Deterministic assembly of the final prompt blocks from the SuperPrompt.

### Prompt orchestration

The final prompt is built from a small number of explicit regions.

```text
[RAG Context]

1. Hard Rules
   - Global system constraints
   - Non-negotiable principles

2. Project / Memory Context
   - Project-level assumptions
   - Later: tagged history according to explicit retrieval rules

3. Optional explicitly loaded material
   - Future deterministic fetcher-style loading of files, code blocks, or notes

4. S_CTX_MD (from A4)
   - Facts
   - Constraints
   - Open issues / questions

5. Attachments (optional)
   - Longer excerpts kept for traceability and citations
```

Below this context block, the prompt carries the `SYSTEM`, `AUDIENCE`, `TASK`, `PURPOSE`, `TONE`, and `CONFIDENCE` fields from the SuperPrompt.

### Deterministic vs model-driven

| Component          | Nature                               | Notes |
|--------------------|--------------------------------------|-------|
| A0_PreProcessing   | Deterministic → Hybrid (later)       | Normalisation + schema mapping; optional LLM help later. |
| A2 PromptShaper    | Model-driven (Chooser)               | Fine-tuned A2 model maps `task/purpose/context` to five labels. |
| Retrieval          | Deterministic function               | Current dense retrieval is implemented; hybrid Retrieval is the agreed next step. |
| ReRanker           | Deterministic ranking stage          | Current cross-encoder reranker is implemented; bounded ColBERT reranking is the agreed next step. |
| A3 NLI Gate        | Model-driven (Multi-Chooser direction) | Chunk labeling and duplicate marking are under construction. |
| A4 Condenser       | Model-driven (Writer)                | Generates `S_CTX_MD` from selected chunks. |
| A5 Format Enforcer | Model-driven (Writer/Extractor)      | Enforces response format / contracts. |
| PromptBuilder      | Deterministic function               | Concatenates everything into a final prompt string. |

---

## Current Status

Implemented / available:

- Core documentation set:
  - `Requirements_Main.md`
  - `Requirements_AgentStack.md`
  - `Requirements_RAG_Pipeline.md`
  - `Requirements_Ingestion_Memory.md`
  - `Requirements_GUI.md`
  - `Requirements_Orchestration_Controller.md`
  - `Requirements_Quality_Governance.md`
  - `Architecture.md`
  - UML files for the main subsystem views
- Working document ingestion pipeline with Chroma-backed persistence.
- Deterministic A0_PreProcessing.
- JSON-based Agent Stack in code.
- A2 PromptShaper wired and live.
- Retrieval wired and live.
- ReRanker wired and live in code.
- Streamlit development GUI with:
  - prompt input,
  - SuperPrompt inspection,
  - 8 pipeline buttons,
  - project creation,
  - file import,
  - active DB selection,
  - embedded-file display,
  - Retrieval Top-K,
  - Retrieval / ReRanker inspection.
- AWS Phase-1 deployment with:
  - GitHub Actions -> ECR,
  - EC2 + Docker runtime,
  - nginx reverse proxy,
  - HTTPS,
  - Route 53,
  - SSM-backed secrets,
  - persistent runtime data outside the image.

Implemented but under redesign or still under construction:

- ReRanker exists, but the current cross-encoder direction is not accepted as the long-term solution.
- A3, A4, A5, and final PromptBuilder stabilization are still under construction.
- Memory / history ingestion and tagged retrieval are under construction.
- Evaluation, benchmarking, and richer governance automation are still being built on top of the current foundation.

---

## Roadmap (near term)

Near-term priorities:

1. **Upgrade Retrieval from dense-only to hybrid Retrieval**  
   - Add SPLADE as the sparse branch.  
   - Fuse dense Retrieval and sparse Retrieval with RRF.

2. **Replace the current ReRanker direction**  
   - Keep ReRanker as a separate stage.  
   - Move from the current cross-encoder path toward bounded ColBERT reranking with query splitting and fused ranking.

3. **Implement A3 as a real chunk-selection stage**  
   - Label reranked chunks (`Must_Keep`, `Useful`, `BorderLine`, `Discarded`).  
   - Mark duplicates against higher-ranked chunks.

4. **Continue the memory layer**  
   - durable history logging,  
   - tag-aware retrieval rules,  
   - explicit include/exclude semantics,  
   - cross-session import of selected history later.

5. **Stabilize the late pipeline**  
   - A4 Condenser, A5 Format Enforcer, PromptBuilder.

6. **Extend development governance and synchronization**  
   - keep requirements, architecture, UML, and implementation aligned as the system evolves.

---

## Repository Layout

The repository already contains a real working tree. A trimmed high-level view looks like this:

```text
ragstream/
  agents/                  # A2, A3, A4 agent modules
  app/
    controller.py          # Orchestrates pipeline stages
    ui_streamlit.py        # Current Streamlit GUI
  config/
    prompt_schema.json
    settings.py
  ingestion/
    loader.py
    chunker.py
    embedder.py
    file_manifest.py
    chroma_vector_store_base.py
    vector_store_chroma.py
    ingestion_manager.py
  memory/
    conversation_memory.py
  orchestration/
    super_prompt.py
    prompt_builder.py
    llm_client.py
    agent_factory.py
    agent_prompt.py
  preprocessing/
    preprocessing.py
    prompt_schema.py
    name_matcher.py
  retrieval/
    chunk.py
    retriever.py
    reranker.py
    attention.py
  utils/
    logging.py
    paths.py

data/
  agents/
  doc_raw/
  chroma_db/
  A2_SLM_Training/
```

---

## GUI (Streamlit)

### Current development GUI
 
RAGstream includes a Streamlit-based development GUI for stepping through the pipeline manually and inspecting intermediate state.

Current development view includes:

- raw prompt input,
- SuperPrompt inspection,
- manual 8-stage pipeline control,
- Retrieval Top-K control,
- project creation and file import,
- active project / DB selection,
- embedded-file visibility,
- retrieval and reranking inspection,
- an evolving memory section.

The current GUI image below shows the active development view:

<p align="center">
  <img src="doc/04-GUI/Dev1.png" alt="Current development GUI">
  <br/><em>Figure 1 – Current development GUI</em>
</p>

The memory section reflects the current direction of the memory architecture. It combines two complementary ideas:

- a persistent always-fed layer for pinned rules and durable context,
- and a retrieval-based semantic layer for normal memory selection.

The tag semantics shown in the current development view already reflect that direction:

- **Gold**: pinned persistent memory, comparable to always-included Layer-G context,
- **Green**: normal semantic memory entry,
- **Silver**: semantic memory entry with baseline weighting,
- **Black**: excluded memory entry, used to remove irrelevant or unwanted prompt/history material from future context.

The full memory workflow is still under construction, and its intended operational shape is the one illustrated in the development GUI shown in `Dev1.png`.

### Planned GUI (next phases)

The next GUI phases extend the current development view rather than replacing its logic.

Planned directions already documented in the requirements and backlog include:

- history view and tag editing,
- manual answer capture from external UIs,
- model selection and cost awareness,
- richer per-stage inspection,
- multi-history and multi-project controls,
- dynamic attention controls,
- deterministic loading of explicit text/material into context,
- later V-model-oriented development tooling.

<p align="center">
  <img src="doc/04-GUI/Vision1.png" alt="Vision mock-up – complete GUI">
  <br/><em>Figure 2 – Conceptual vision of the later GUI direction</em>
</p>

---

## License & Author

This is a personal research and engineering project by **Rusbeh Abtahi**.

The codebase is MIT-licensed. The project is being developed as a transparent, inspectable RAG system whose requirements, architecture, UML, deployment, and implementation can evolve in a controlled way.
  