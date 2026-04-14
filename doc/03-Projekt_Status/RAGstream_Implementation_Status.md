# RAGstream_Implementation_Status.md

Last update: 14.04.2026

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
2. JSON-based agent architecture with a working A2 PromptShaper stage,
3. project-based document ingestion with manifest-based file tracking,
4. hybrid document retrieval with dense first-pass selection + SPLADE scoring on the same candidate IDs + weighted RRF,
5. a working AWS Phase-1 deployment with persistent runtime data outside the image.

The pipeline now reaches from prompt input and A2 shaping to project-aware hybrid chunk selection from the active document database, and it also includes a deterministic ReRanker stage.

Current practical truth:
- Retrieval is implemented and working.
- Retrieval is no longer dense-only; it now includes a real SPLADE scoring branch and weighted RRF fusion.
- ReRanker is implemented and working in code.
- However, the current BERT-style reranker direction is not accepted as the long-term solution, because in practical tests it often worsened ranking quality instead of improving it.

The currently agreed next implementation direction is:
- keep the existing Retrieval / ReRanker stage structure,
- keep the new hybrid Retrieval backbone,
- replace the current reranking strategy with a stronger future direction,
- immediate next step: ColBERT.

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
  - JSON agent loading and caching exist.
  - `LLMClient` exists.
  - `AgentPrompt` architecture exists.
- A2 PromptShaper is implemented and already wired.
  - It reads the current `SuperPrompt`.
  - It uses a JSON-configured agent prompt.
  - It calls the LLM.
  - It writes selected values back into `SuperPrompt`.
  - It updates stage/history.
- A2 PromptShaper is implemented, wired into the app, and updates SuperPrompt through the JSON-based agent stack.

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
- Snapshot keys such as `sp_pre`, `sp_a2`, `sp_rtv`, and `sp_rrk` exist so that stage-specific prompt states can be preserved as snapshots rather than overwritten mentally.
- Retrieval is already a live button path after PreProcessing and A2.
- ReRanker is also already wired as a live stage after Retrieval.
- The current Super-Prompt rendering path can now show Retrieval-related score information in the GUI.

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

### 2.10 Why the current ReRanker direction is not accepted as final

- Practical evaluation showed that the current BERT-style reranker often did not improve the already good Retrieval ranking.
- In important real examples, it made the ranking worse:
  - relevant chunks were demoted too aggressively,
  - some weaker or less useful chunks were promoted,
  - and the final ranking became less trustworthy than dense Retrieval alone.
- Therefore the current BERT-style reranking direction is considered unsatisfactory as the future production direction.

### 2.11 AWS Phase-1 deployment

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
  - Route53 → AWS public IPv4 → EC2 Ubuntu host → nginx → Docker → Streamlit.
- nginx is the public entry point, TLS terminates at nginx, and Streamlit runs behind it on port 8501.

### 2.12 AWS runtime data separation

- The AWS runtime model is already correctly separated.
- The Docker image is code-focused.
- Runtime project data remains outside the image on EC2/EBS under:
  - `/home/ubuntu/ragstream_data`
- Inside the container, this is mounted as:
  - `/app/data`
- The logical structure stays the same locally and on AWS:
  - `data/doc_raw/<project>`
  - `data/chroma_db/<project>`
  - `data/splade_db/<project>`
- This means project raw files, Chroma databases, and SPLADE stores are persistent and survive container replacement.

---

## 3. What exists only partially or as scaffold

### 3.1 A3 / A4 / A5 / Prompt Builder

- A3 NLI Gate is still at placeholder/scaffold level.
- A4 Condenser is still at placeholder/scaffold level.
- A5 Format Enforcer is not yet an active working stage.
- Prompt Builder is still not the final authoritative assembly stage in practical code execution.
- This means the late pipeline still remains to be implemented after the Retrieval / ReRanker direction is stabilized.

### 3.2 Memory / conversation memory

- Memory files and architecture references exist.
- Real history ingestion, episodic retrieval, and the two-layer memory model are not implemented yet as a working production path.
- Conversation memory is still one of the largest remaining planned subsystems.

### 3.3 Selected older structural items

- Some older requirement/UML concepts still exist in documents at a higher level than the current code.
- This is especially relevant where older wording still reflects:
  - earlier ingestion assumptions,
  - earlier retrieval scoring wording,
  - older reranker assumptions,
  - earlier rendering ownership assumptions,
  - or earlier retrieval-backend assumptions.
- The current implementation direction is already more concrete than those older placeholders.

---

## 4. Current implemented Retrieval details

This section records the Retrieval stage more precisely because it is already implemented and forms the current backbone.

### 4.1 Retrieval inputs

- Input object: current evolving `SuperPrompt`
- Retrieval text source:
  - `task`
  - `purpose`
  - `context`
- Runtime parameters:
  - active project
  - Retrieval Top-K from GUI

### 4.2 Retrieval chunking and embedding

- Retrieval query splitting reuses the same deterministic chunking culture as ingestion.
- Current values:
  - `chunk_size = 1200`
  - `overlap = 120`
- Important:
  - in the current codebase, this chunking is character-based, not token-based
- Dense embedding model:
  - `text-embedding-3-large`
- SPLADE branch:
  - active and implemented

### 4.3 Retrieval scoring

- Retrieval is no longer dense-only.
- Current implemented Retrieval structure:
  - dense ranking branch
  - SPLADE rescoring branch over the dense-selected candidate IDs
  - weighted RRF fusion
- Dense branch scoring:
  - similarity is computed between each stored chunk embedding and all query-piece embeddings
  - aggregation is not a simple max
  - current implemented dense retrieval score:
    - p-norm averaging
    - `p = 10`
- SPLADE branch scoring:
  - SPLADE computes its score only on the same top-k candidate IDs already selected by the dense branch
  - it does not run an independent competing top-k selection anymore in the current code path
- Final fused Retrieval score:
  - weighted reciprocal-rank fusion
  - current weighting:
    - dense branch weight = `5.9`
    - SPLADE branch weight = `0.0`

### 4.4 Retrieval output and write-back

- Selected chunk objects are written into `base_context_chunks`.
- Stage-specific retrieval output is written into `views_by_stage["retrieval"]`.
- The currently selected order is written into `final_selection_ids`.
- `stage` and `history_of_stages` are updated.
- The GUI-visible Super-Prompt then shows a `## Related Context` section built from the selected chunks.
- Retrieval-specific metadata needed by the projector is currently mapped in `Retriever` after neutral RRF merge and before hydration/write-back.
- Because SPLADE now scores the same dense-selected candidate IDs, the intended GUI/debug behavior is that each final Retrieval chunk can carry both dense and SPLADE score fields.

### 4.5 Retrieval robustness

- Retrieval already includes robustness work for stale/broken DB rows.
- Bad/stale entries are skipped instead of crashing the stage.
- This matters because runtime databases can outlive raw-file changes and the retrieval stage must not fail because of one stale entry.

---

## 5. Current implemented ReRanker details

This section records the ReRanker stage more precisely because it is already implemented, even though the direction is not accepted as final.

### 5.1 ReRanker inputs

- Input object: current evolving `SuperPrompt`
- ReRanking query source:
  - `task`
  - `purpose`
  - `context`
- Candidate source:
  - Retrieval candidates already stored in `views_by_stage["retrieval"]`
  - hydrated chunks already stored in `base_context_chunks`

### 5.2 ReRanker model and runtime

- Current model:
  - `cross-encoder/ms-marco-MiniLM-L-12-v2`
- Current runtime direction:
  - CPU-only deterministic stage

### 5.3 ReRanker behavior

- Build one semantic reranking query from:
  - `task`
  - `purpose`
  - `context`
- Dynamically clean chunk text before scoring.
- Score each `(query, chunk)` pair.
- Sort by reranker score.
- Write:
  - `views_by_stage["reranked"]`
  - `final_selection_ids`
  - updated `stage`
  - updated `history_of_stages`

### 5.4 Current practical conclusion

- ReRanker is implemented.
- ReRanker is usable for experimentation and analysis.
- But the current BERT-style reranker is not accepted as the future stable strategy.

---

## 6. Session decisions added on 14.04.2026

### 6.1 Ingestion direction finalized on 14.04.2026

- Parallel dense + SPLADE ingestion is now part of the real implementation direction, not only a future idea.
- The current agreed structural rule is:
  - one canonical chunking pass,
  - one canonical chunk ID scheme,
  - same chunk IDs and metadata in both dense and sparse stores.
- The SPLADE store is persisted separately under:
  - `data/splade_db/<project>`

### 6.2 Retrieval fusion decision on 14.04.2026

- Weighted RRF was accepted as the current Retrieval fusion strategy.
- Current decision:
  - dense branch weight = `0.75`
  - SPLADE branch weight = `0.25`
- Current practical conclusion:
  - results look acceptable enough to keep this weighting for now.

### 6.3 Architectural separation decision on 14.04.2026

- The neutral merger principle was clarified.
- Current agreed separation:
  - `rrf_merger.py` stays neutral and branch-agnostic,
  - `retriever.py` is the higher-level place that knows:
    - branch A = dense
    - branch B = SPLADE
  - retrieval-specific metadata names needed by rendering are created in `Retriever`, not inside the neutral merger.

### 6.4 Immediate next step decided on 14.04.2026

- Immediate next step:
  - ColBERT
- The next phase is therefore not another large Retrieval redesign from zero.
- The next phase is:
  - keep the current hybrid Retrieval backbone,
  - move the reranking direction toward ColBERT.

### 6.5 Candidate-set alignment decision on 14.04.2026

- Retrieval candidate-set alignment was clarified.
- The current agreed rule is:
  - dense Retrieval selects the active top-k candidate IDs first,
  - SPLADE must then score exactly those same candidate IDs,
  - SPLADE must not run an independent top-k search for different chunk IDs inside the Retrieval stage.
- Practical consequence:
  - the Retrieval-stage final display can now be expected to carry both dense and SPLADE score information for the same chunk set.

### 6.6 Current code-path weighting on 14.04.2026

- The current code-path weighting is now:
  - dense branch weight = `5.9`
  - SPLADE branch weight = `0.0`
- Practical consequence:
  - the final Retrieval order currently follows the dense ranking order,
  - while SPLADE scores can still be attached to the same candidate IDs for inspection/debugging.

---

## 7. Current agreed next implementation direction

The next implementation direction is no longer "implement ReRanker from zero".
The next implementation direction is to improve the current Retrieval / ReRanker design.

### 7.1 Retrieval direction

- Keep the new hybrid Retrieval backbone:
  - dense Retrieval
  - SPLADE scoring on the same dense-selected candidate IDs
  - weighted RRF fusion
- Keep the current weighting unless later practical evaluation shows a better weighting.

### 7.2 ReRanker direction

- The current BERT-style cross-encoder reranker should not remain the main long-term strategy.
- The agreed future direction is:
  - ColBERT instead of the current BERT-style reranker

### 7.3 Query splitting helper direction

- The current `smart_query_splitter.py` still uses deterministic linear windowing.
- A future smart splitter direction remains open.
- A likely next refinement later is:
  - meaning-based splitting under a bounded size limit
- But this is not the immediate next step.
- Immediate next step remains ColBERT.

### 7.4 A3 direction

- A3 should become a selection stage after ReRanking.
- A3 should classify chunks with labels such as:
  - `Must_Keep`
  - `Useful`
  - `BorderLine`
  - `Discarded`
- A3 should also detect duplicates / near-duplicates.
- Detailed A3 behavior belongs in the requirement files, not here.

---

## 8. Current AWS compute decision for the next phase

The current AWS deployment stays in place structurally.

### 8.1 What remains unchanged

- ECR workflow remains unchanged.
- Docker deployment model remains unchanged.
- nginx reverse proxy remains unchanged.
- HTTPS/TLS remains unchanged.
- Route53 remains unchanged.
- SSM secret handling remains unchanged.
- EBS-backed runtime data remains unchanged.
- The persistent runtime path model remains unchanged.

### 8.2 What is planned to change

- The current EC2 instance type is planned to be upgraded.
- Direction:
  - from `t3.small`
  - to `m7i-flex.xlarge`

### 8.3 Why this change is planned

- Retrieval is already working on the current deployment model.
- ReRanking experiments and future ColBERT-related work will be more CPU/RAM-demanding than Retrieval alone.
- The selected instance is intended to bring AWS runtime performance much closer to the local laptop class.
- The goal is to make the next retrieval/reranking phase practically usable on AWS without changing the surrounding deployment architecture.

---

## 9. What this means operationally now

RAGstream now includes working prompt processing, ingestion, retrieval, reranking, and AWS deployment layers.

The system now has:
- a working prompt entry path,
- a working A2 shaping path,
- a working project-based ingestion path,
- a working dense + SPLADE document persistence path,
- a working active-project GUI path,
- a working AWS public deployment,
- a working hybrid Retrieval stage,
- and a working ReRanker stage.

The project now includes controller-driven prompt processing, ingestion, retrieval, and reranking in code.
The system now has context retrieval and reranking stages in code.

The immediate development focus is now clear:
- keep the current hybrid Retrieval backbone,
- replace the current unsatisfactory reranking direction,
- move toward ColBERT,
- then continue with A3 / A4 / A5 / Prompt Builder,
- while keeping the AWS deployment architecture stable and only increasing compute capacity where needed.

---

## 10. Important note

- This file is an implementation status snapshot.
- It records the current working system and the currently agreed next direction.
- It is intentionally more practical than the requirement files.
- Future-direction sections here stay shorter on purpose.
- The detailed behavioral design belongs in the requirement files.
- If the implementation changes again, this file should be updated again accordingly.