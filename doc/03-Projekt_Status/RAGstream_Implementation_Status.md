# RAGstream_Implementation_Status.md

Last update: 21.04.2026

Purpose:
- This file is a compact implementation status snapshot.
- It records what is already working now.
- It also records the currently agreed next implementation direction.
- It is not a requirement file and not a final roadmap.
- For future updates, newly added decisions and implementation changes should be date-stamped inside the relevant section so chronological evolution remains visible.

---

## 1. High-level picture

RAGstream already has a stable foundation in five major layers:

1. foundational prompt processing and GUI/controller structure,
2. JSON-based agent architecture with working A2 and A3 stages,
3. project-based document ingestion with manifest-based file tracking,
4. hybrid document retrieval with dense first-pass selection + SPLADE scoring on the same candidate IDs + weighted RRF,
5. a working AWS Phase-1 deployment with persistent runtime data outside the image.

The pipeline now reaches from prompt input and A2 shaping to project-aware hybrid chunk selection from the active document database, and it also includes a deterministic ReRanker stage plus a real A3 stage.

Current practical truth:
- Retrieval is implemented and working.
- Retrieval is no longer dense-only; it now includes a real SPLADE scoring branch and weighted RRF fusion.
- ReRanker is implemented and working in code.
- A3 is implemented and working in code as a real usefulness-classification stage over reranked candidates.
- However, the current BERT-style reranker direction is not accepted as the long-term solution, because in practical tests it often worsened ranking quality instead of improving it.

The currently agreed next implementation direction is:
- keep the existing Retrieval / ReRanker stage structure,
- keep the new hybrid Retrieval backbone,
- keep A3 as the current semantic usefulness gate,
- implement A4 Condenser next,
- implement Prompt Builder immediately after A4,
- postpone A5 to a later phase because its action may still change before implementation,
- keep ColBERT as the agreed immediate next reranking direction.

---

## 2. What is already implemented

### 2.1 Foundational app structure

- A Generation-1 Streamlit GUI exists.
  - Prompt input area exists.
  - Super-Prompt display area exists.
  - 8 pipeline buttons are visible.
  - Project-based ingestion controls exist.
  - Active project selection exists.
  - Embedded-file display for the selected project exists.
- The current GUI supports prompt processing, project creation, file ingestion, active project selection, and embedded-file display.

### 2.2 Deterministic prompt preprocessing

- Deterministic Pre-Processing is implemented.
  - Markdown/header parsing exists.
  - Schema-based field mapping exists.
  - MUST/default handling exists.
  - `prompt_ready` generation exists for the current preprocessing path.
- This stage is already part of the live GUI/controller wiring and acts as the first normalization layer for user input.

### 2.3 JSON-based agent architecture

- JSON-based agent infrastructure is implemented.
  - `AgentFactory` exists.
  - JSON agent loading and transparent config-level caching exist.
  - `LLMClient` exists.
  - `AgentPrompt` architecture exists.
- A2 PromptShaper is implemented and already wired.
  - It reads the current `SuperPrompt`.
  - It uses a JSON-configured agent prompt.
  - It calls the LLM.
  - It writes selected values back into `SuperPrompt`.
  - It updates stage/history.
- A3 NLI Gate is implemented and already wired.
  - It reads the reranked candidate set from the current `SuperPrompt`.
  - It uses the JSON-configured neutral Agent Stack.
  - It performs usefulness-only classification.
  - It writes `views_by_stage["a3"]`, `extras["a3_selection_band"]`, `extras["a3_item_decisions"]`, and `final_selection_ids`.
- [21.04.2026] Current immediate next implementation targets in the Agent Stack pipeline are A4 Condenser and Prompt Builder. A5 is intentionally postponed for a later phase because its final action is still open to revision.

### 2.4 SuperPrompt as shared state

- `SuperPrompt` exists as the central shared prompt object.
- It already stores:
  - canonical body fields,
  - stage,
  - stage history,
  - retrieval-related fields,
  - recent conversation placeholder fields,
  - rendered prompt fields.
- In the current implementation direction, `SuperPrompt` is the evolving shared state object across the pipeline rather than a one-off prompt string.
- A general `compose_prompt_ready()` path is part of the recent implementation direction so that later stages can reuse one central render logic instead of keeping rendering scattered across multiple modules.

### 2.5 Project-based ingestion

- Project-based ingestion is implemented and connected to the GUI.
  - Create Project button exists.
  - Add Files button exists.
  - Files are copied into `data/doc_raw/<project>`.
  - Ingestion runs automatically afterward.
- The project-specific storage model is implemented:
  - `data/doc_raw/<project>`
  - `data/chroma_db/<project>`
  - `data/splade_db/<project>`
  - `file_manifest.json` belongs to the matching Chroma DB project folder.
- The embedded-files list for the active project is visible in the GUI through the manifest/controller path.

### 2.6 Parallel dense + SPLADE document ingestion backend

- Parallel dense + SPLADE ingestion is implemented.
  - Loader exists.
  - Chunker exists.
  - Dense Embedder exists.
  - SPLADE Embedder exists.
  - Chroma vector store exists.
  - SPLADE vector store exists.
  - `IngestionManager` exists.
  - manifest-based diff/hash logic exists.
  - deterministic stable chunk IDs exist.
- The ingestion model now uses one canonical chunking pass and writes the same chunk IDs and metadata into both branches:
  - dense branch → `data/chroma_db/<project>`
  - sparse branch → `data/splade_db/<project>`
- This means ingestion is no longer conceptually dense-only.

### 2.7 Retrieval is implemented as a hybrid stage

- Retrieval is implemented as a deterministic, project-aware hybrid stage.
- Its logic now is:
  - read retrieval query text from the current `SuperPrompt`,
  - use `task`, `purpose`, and `context` as the retrieval source,
  - split the retrieval query into overlapping pieces,
  - run the dense embedding branch on the active project's Chroma document store,
  - select the dense top-k candidate IDs,
  - run the SPLADE sparse branch on the active project's SPLADE store for exactly those same dense-selected candidate IDs,
  - fuse both ranked lists with weighted RRF,
  - reconstruct the real chunk text from `doc_raw/<project>` using the same chunking logic as ingestion,
  - write the result back into `SuperPrompt`.
- Retrieval ranks chunks, reconstructs their text from `doc_raw/<project>`, and writes the selected chunks into `base_context_chunks`.

### 2.8 Retrieval-related GUI/controller integration

- The Retrieval Top-K field exists in the GUI.
- The active project selector exists in the GUI.
- Snapshot keys such as `sp_pre`, `sp_a2`, `sp_rtv`, `sp_rrk`, and `sp_a3` exist so that stage-specific prompt states can be preserved as snapshots rather than overwritten mentally.
- Retrieval is already a live button path after PreProcessing and A2.
- ReRanker is also already wired as a live stage after Retrieval.
- A3 is already wired as a live stage after ReRanker.
- The current Super-Prompt rendering path can now show Retrieval-related score information in the GUI.
- [17.04.2026] The GUI/controller startup path is split into light startup plus background heavy initialization so the page appears before Retrieval / ReRanker warm-up is complete.
- [17.04.2026] Optional slow-component bypass controls are already live in Generation-1:
  - `use Retrieval Splade`
  - `use Reranking Colbert`

### 2.9 ReRanker is implemented

- ReRanker is implemented as a deterministic stage.
- It is no longer only a planned step.
- The currently implemented ReRanker direction is:
  - BERT-style cross-encoder reranking
  - CPU-only runtime
  - current model:
    - `cross-encoder/ms-marco-MiniLM-L-12-v2`
- Its logic is:
  - read the Retrieval candidates already stored in `SuperPrompt`,
  - rebuild one reranking query from:
    - `task`
    - `purpose`
    - `context`
  - dynamically clean chunk text before scoring,
  - score each `(query, chunk)` pair with the cross-encoder,
  - sort by reranker score,
  - write the reranked view back into `SuperPrompt`.
- ReRanker reranks Retrieval candidates and writes the reranked view back into `SuperPrompt`.

### 2.10 A3 is implemented as a real stage

- A3 is implemented as a real semantic stage.
- It is no longer only a placeholder or abstract future idea.
- The current implemented A3 direction is:
  - usefulness-only classification over reranked candidates,
  - one global `selection_band`,
  - one usefulness decision per candidate chunk,
  - deterministic useful-first selection with borderline fallback.
- Important current A3 truth:
  - long real chunk ids are not shown to the LLM,
  - local chunk ids `1..N` are used in the prompt and mapped back internally,
  - chunk-internal heading markers are sanitized to avoid prompt-structure conflicts,
  - duplicate marking has been intentionally removed.
- A3 already performs meaningful semantic filtering and is considered good enough to keep as the current stage truth while the next work moves to A4 and Prompt Builder.

### 2.11 Why the current ReRanker direction is not accepted as final

- Practical evaluation showed that the current BERT-style reranker often did not improve the already good Retrieval ranking.
- In important real examples, it made the ranking worse:
  - relevant chunks were demoted too aggressively,
  - some weaker or less useful chunks were promoted,
  - and the final ranking became less trustworthy than dense Retrieval alone.
- Therefore the current BERT-style reranking direction is considered unsatisfactory as the future production direction.

### 2.12 AWS Phase-1 deployment

- AWS Phase-1 deployment is implemented and working.
- The current live deployment already provides:
  - GitHub Actions builds and pushes Docker image to ECR,
  - EC2 pulls the latest image and starts the container,
  - nginx reverse proxy is working,
  - HTTPS/TLS is working,
  - Route53 update is working,
  - SSM secret loading is working,
  - persistent runtime data on EC2/EBS is working.
- The public network path is already stable:
  - Route53 → AWS public IPv4 → EC2 → nginx → Docker → Streamlit.

---

## 3. What is intentionally not complete yet

### 3.1 A4 Condenser

- A4 exists as a project module (`ragstream/agents/a4_condenser.py`) and as a pipeline contract, but it is not yet a live, completed operational stage in the current GUI/controller path.
- [21.04.2026] A4 is now the next immediate implementation target.

### 3.2 Prompt Builder

- `prompt_builder.py` exists as a project module and the deterministic final-assembly concept is defined in the requirements.
- It is not yet the completed final operational stage in the current Generation-1 GUI flow.
- [21.04.2026] Prompt Builder is the immediate follow-up target after A4.

### 3.3 A5 Format Enforcer

- A5 exists in the long-range 8-stage contract, but it is not a live completed operational stage.
- [21.04.2026] A5 is intentionally postponed to a later phase.
- [21.04.2026] Its future action may be revised before implementation, so the current requirement contract should be treated as provisional rather than implementation-locked.

### 3.4 History ingestion and tagging

- Conversation history ingestion remains future / partial.
- Append-only memory direction exists conceptually, but it is not yet the current working production path for the pipeline.
- Tag-governed retrieval and cross-chat import remain backlog/future work.

---

## 4. Current immediate implementation plan

### 4.1 Immediate next work order

[21.04.2026] The agreed immediate work order is:

1. keep current Retrieval / ReRanker / A3 truth stable,
2. implement A4 Condenser,
3. implement Prompt Builder,
4. postpone A5,
5. revisit ReRanker improvement with ColBERT after the pipeline is stable through A4 and Prompt Builder.

### 4.2 Why this order is now preferred

- Retrieval is already strong enough to continue development.
- ReRanker is live enough to keep the stage contract while its long-term replacement is still open.
- A3 is already good enough to be treated as a real stage.
- The biggest missing operational gap in the end-to-end pipeline is now downstream of A3:
  - condensed context generation,
  - final deterministic prompt assembly.
- Therefore the highest leverage is no longer more A3 redesign, but implementation of A4 and Prompt Builder.

---

## 5. Compact bottom-line statement

RAGstream is no longer only an ingestion + retrieval prototype.
It already has:
- working preprocessing,
- working JSON-based Agent Stack,
- working A2,
- working project-based ingestion,
- working hybrid Retrieval,
- working deterministic ReRanker,
- working A3 usefulness filtering,
- and working AWS Phase-1 deployment.

[21.04.2026] The immediate next milestone is to complete the pipeline after A3 by implementing A4 Condenser and Prompt Builder. A5 is postponed and may be redefined before it is built.
