# RAGstream_Implementation_Status.md

Last update: 2026-03-16

Purpose:
- This file is a compact implementation status snapshot.
- It records what is already working now.
- It also records the currently agreed next implementation direction.
- It is not a requirement file and not a final roadmap.

---

## 1. High-level picture

RAGstream already has a stable foundation in four major layers:

1. foundational prompt processing and GUI/controller structure,
2. JSON-based agent architecture with a working A2 PromptShaper stage,
3. project-based Chroma ingestion with manifest-based file tracking,
4. a working AWS Phase-1 deployment with persistent runtime data outside the image.

The most recent implementation wave completed the first real context-selection stage: Retrieval. This means the pipeline now reaches from prompt input and A2 shaping to project-aware chunk selection from the active document database.

The next concrete implementation step is ReRanker. The selected direction is a BERT-style cross-encoder reranker that will read the Retrieval candidates already stored in `SuperPrompt`, produce a stronger semantic ranking, and then hand the reranked context to the later A3/A4/A5 / Prompt Builder stages.

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
- The current GUI is therefore no longer only a visual shell. It already supports real operational flows for prompt processing and project/document handling. fileciteturn61file12 fileciteturn61file5

### 2.2 Deterministic prompt preprocessing

- Deterministic Pre-Processing is implemented.
  - Markdown/header parsing exists.
  - Schema-based field mapping exists.
  - MUST/default handling exists.
  - `prompt_ready` generation exists for the current preprocessing path.
- This stage is already part of the live GUI/controller wiring and acts as the first normalization layer for user input. fileciteturn61file12

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
- This means the agent stack is not theoretical anymore. A2 is already a working live stage in the current app. fileciteturn61file12

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
- A general `compose_prompt_ready()` path is part of the recent implementation direction so that later stages can reuse one central render logic instead of keeping rendering scattered across multiple modules. fileciteturn62file18

### 2.5 Project-based ingestion

- Project-based ingestion is implemented and connected to the GUI.
  - Create Project button exists.
  - Add Files button exists.
  - Files are copied into `data/doc_raw/<project>`.
  - Ingestion runs automatically afterward.
- The project-specific storage model is implemented:
  - `data/doc_raw/<project>`
  - `data/chroma_db/<project>`
  - `file_manifest.json` belongs to the matching project DB folder.
- The embedded-files list for the active project is visible in the GUI through the manifest/controller path. fileciteturn61file12 fileciteturn61file14

### 2.6 Chroma-based document ingestion backend

- Chroma-based ingestion is implemented.
  - Loader exists.
  - Chunker exists.
  - Embedder exists.
  - Chroma vector store exists.
  - `IngestionManager` exists.
  - manifest-based diff/hash logic exists.
  - deterministic stable chunk IDs exist.
- This layer is already aligned with the Chroma-based architecture and is no longer in the earlier NumPy-store phase. fileciteturn61file12 fileciteturn61file14

### 2.7 Retrieval is now implemented

- Retrieval is now a real implemented stage, not only a placeholder idea.
- The implemented Retrieval stage is deterministic and project-aware.
- Its logic is:
  - read retrieval query text from the current `SuperPrompt`,
  - use `task`, `purpose`, and `context` as the retrieval source,
  - split the retrieval query into overlapping pieces,
  - read the active project's Chroma document store,
  - compare each stored chunk embedding against all query-piece embeddings,
  - aggregate scores with LogAvgExp (`tau = 9`),
  - keep the top-k chunks,
  - reconstruct the real chunk text from `doc_raw/<project>` using the same chunking logic as ingestion,
  - write the result back into `SuperPrompt`.
- Retrieval therefore already performs true context selection and not just abstract ranking. fileciteturn62file1 fileciteturn62file3

### 2.8 Retrieval-related GUI/controller integration

- The Retrieval Top-K field exists in the GUI.
- The active project selector exists in the GUI.
- Snapshot keys such as `sp_pre`, `sp_a2`, and `sp_rtv` were introduced in the recent implementation direction so that stage-specific prompt states can be preserved as snapshots rather than overwritten mentally.
- The recent implementation direction also introduces Retrieval as the next live button path after PreProcessing and A2, together with `SuperPrompt`-based rendering of the selected context in the GUI. fileciteturn61file5 fileciteturn62file17

### 2.9 AWS Phase-1 deployment

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
- nginx is the public entry point, TLS terminates at nginx, and Streamlit runs behind it on port 8501. fileciteturn57file2 fileciteturn57file13

### 2.10 AWS runtime data separation

- The AWS runtime model is already correctly separated.
- The Docker image is code-focused.
- Runtime project data remains outside the image on EC2/EBS under:
  - `/home/ubuntu/ragstream_data`
- Inside the container, this is mounted as:
  - `/app/data`
- The logical structure stays the same locally and on AWS:
  - `data/doc_raw/<project>`
  - `data/chroma_db/<project>`
- This means project raw files and Chroma databases are persistent and survive container replacement. fileciteturn57file2

---

## 3. What exists only partially or as scaffold

### 3.1 ReRanker

- ReRanker is still the next major missing implemented stage.
- The direction is already agreed, but the real working stage is not implemented yet.
- In other words: Retrieval is now the first real context-selection step, but semantic reranking is still pending.

### 3.2 A3 / A4 / A5 / Prompt Builder

- A3 NLI Gate is still at placeholder/scaffold level.
- A4 Condenser is still at placeholder/scaffold level.
- A5 Format Enforcer is not yet a real active working stage.
- Prompt Builder is still not the final authoritative assembly stage in practical code execution.
- This means the late pipeline still remains to be implemented after Retrieval and ReRanker are stabilized. fileciteturn61file13

### 3.3 Memory / conversation memory

- Memory files and architecture references exist.
- Real history ingestion, episodic retrieval, and the two-layer memory model are not implemented yet as a working production path.
- Conversation memory is still one of the largest remaining planned subsystems. fileciteturn61file13 fileciteturn61file14

### 3.4 Selected older structural items

- Some older requirement/UML concepts still exist in documents at a higher level than the current code.
- This is especially relevant where older wording still reflects:
  - id-only retrieval stage views,
  - earlier rendering ownership assumptions,
  - or earlier retrieval-backend assumptions.
- The current implementation direction is already more concrete than those older placeholders.

---

## 4. Current implemented Retrieval details

This section records the Retrieval stage more precisely because it is the most recent major completed step.

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
  - `chunk_size = 500`
  - `overlap = 100`
- Embedding model:
  - `text-embedding-3-large` fileciteturn62file1

### 4.3 Retrieval scoring

- Similarity is computed between each stored chunk embedding and all query-piece embeddings.
- Aggregation is not a simple max.
- Current agreed retrieval score:
  - LogAvgExp
  - `tau = 9.0`
- Retrieval remains deterministic and separate from ReRanker. fileciteturn62file1

### 4.4 Retrieval output and write-back

- Selected chunk objects are written into `base_context_chunks`.
- Stage-specific retrieval output is written into `views_by_stage`.
- The currently selected order is written into `final_selection_ids`.
- `stage` and `history_of_stages` are updated.
- The GUI-visible Super-Prompt then shows a `## Related Context` section built from the selected chunks. fileciteturn62file1 fileciteturn62file18

### 4.5 Retrieval robustness

- Retrieval already includes robustness work for stale/broken DB rows.
- Bad/stale entries are skipped instead of crashing the stage.
- This matters because runtime databases can outlive raw-file changes and the retrieval stage must not fail because of one stale entry.

---

## 5. Current agreed next step: ReRanker

The next implementation step is ReRanker.

### 5.1 Why ReRanker is next

- Retrieval is already fast and broad.
- Retrieval is now good enough to collect candidate chunks from the right project database.
- The next required improvement is precision, not recall.
- ReRanker will therefore operate on the chunk set already selected by Retrieval.

### 5.2 Selected ReRanker direction

- The selected direction is a BERT-style cross-encoder reranker.
- Current agreed model direction:
  - `cross-encoder/ms-marco-MiniLM-L-6-v2`
- The reranker will not replace Retrieval.
- It will consume Retrieval results and produce a stronger semantic ranking.

### 5.3 Planned ReRanker flow

- Read the current `SuperPrompt`.
- Read the chunk candidates already selected by Retrieval.
- For each candidate chunk, score the pair:
  - `(Prompt_MD, chunk_text)`
- Sort the candidates by reranker score.
- Keep the top reranked subset.
- Write the reranked stage back into `SuperPrompt`.
- Refresh the GUI-visible Super-Prompt from the updated object state.

### 5.4 Expected practical effect

- Retrieval remains the fast recall stage.
- ReRanker becomes the precision-improving semantic stage.
- This is the intended bridge from naive vector retrieval to stronger context quality before A3 and A4.

---

## 6. Current AWS compute decision for the next phase

The current AWS deployment stays in place structurally.

### 6.1 What remains unchanged

- ECR workflow remains unchanged.
- Docker deployment model remains unchanged.
- nginx reverse proxy remains unchanged.
- HTTPS/TLS remains unchanged.
- Route53 remains unchanged.
- SSM secret handling remains unchanged.
- EBS-backed runtime data remains unchanged.
- The persistent runtime path model remains unchanged.

### 6.2 What is planned to change

- The current EC2 instance type is planned to be upgraded.
- Direction:
  - from `t3.small`
  - to `m7i-flex.xlarge`

### 6.3 Why this change is planned

- Retrieval is already working on the current deployment model.
- ReRanker will be substantially more CPU/RAM-demanding than Retrieval.
- The selected instance is intended to bring AWS runtime performance much closer to the local laptop class.
- The goal is to make the future ReRanker stage practically usable on AWS without changing the surrounding deployment architecture.

---

## 7. What this means operationally now

RAGstream has already passed the purely architectural/planning phase.

The system now has:
- a working prompt entry path,
- a working A2 shaping path,
- a working project-based ingestion path,
- a working Chroma document store,
- a working active-project GUI path,
- a working AWS public deployment,
- and a now-completed first Retrieval implementation wave.

The project is therefore no longer “planning + ingestion only.”
The system now has a real first context-retrieval pipeline stage.

The immediate development focus is now clear:
- implement ReRanker,
- then continue with A3 / A4 / A5 / Prompt Builder,
- while keeping the AWS deployment architecture stable and only increasing compute capacity where needed.

---

## 8. Important note

- This file is an implementation status snapshot.
- It records the current working system and the currently agreed next step.
- It is intentionally more practical than the requirement files.
- If the implementation changes again, this file should be updated again accordingly.
