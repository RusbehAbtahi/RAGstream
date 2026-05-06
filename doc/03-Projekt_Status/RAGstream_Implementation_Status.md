Updated based on your current report file. 

````markdown
# RAGstream_Implementation_Status.md

Last update: 06.05.2026

Purpose:
- This file is a compact implementation status snapshot.
- It records what is already working now.
- It also records the currently agreed next implementation direction.
- It is not a requirement file and not a final roadmap.
- For future updates, newly added decisions and implementation changes should be date-stamped inside the relevant section so chronological evolution remains visible.
- [03.05.2026 / KW18 2026] This update adds the implemented Memory Recording layer, the implemented Memory Ingestion layer, and the corrected TextForge / RagLog logging layer.
- [06.05.2026 / KW19 2026] This update adds the corrected MemoryRecord persistence authority split, initial Memory Retrieval, MemoryContextPack wiring, server-side Memory Files management, tabbed Streamlit structure, auto-created memory histories, and the future ActiveRetrievalBrief requirement.

---

## 1. High-level picture

RAGstream already has a stable foundation in ten major layers:

1. foundational prompt processing and GUI/controller structure,
2. JSON-based agent architecture with working A2, A3, and A4 stages,
3. project-based document ingestion with manifest-based file tracking,
4. hybrid document retrieval with dense first-pass selection + SPLADE scoring on the same candidate IDs + weighted RRF,
5. GUI-visible SuperPrompt rendering through `SuperPromptProjector`,
6. a working AWS Phase-1 deployment with persistent runtime data outside the image,
7. [03.05.2026 / KW18 2026] structured Memory Recording with durable `.ragmem`, `.ragmeta.json`, and SQLite persistence,
8. [03.05.2026 / KW18 2026] structured Memory Ingestion with dedicated memory vectors and TextForge / RagLog logging support,
9. [06.05.2026 / KW19 2026] initial Memory Retrieval with raw memory candidates, semantic chunks, episodic candidates, working memory, Direct Recall hook, and `MemoryContextPack`,
10. [06.05.2026 / KW19 2026] server-side Memory Files management through a dedicated FILES tab.

The pipeline now reaches from prompt input and A2 shaping to project-aware hybrid chunk selection from the active document database, and it also includes a deterministic ReRanker stage, a real A3 stage, and a live A4 Condenser that writes `S_CTX_MD`.

[03.05.2026 / KW18 2026] In addition to the document RAG pipeline, RAGstream now has a separate Memory subsystem path:

```text
accepted prompt + accepted response
→ Memory Recording
→ durable MemoryRecord truth
→ Memory Ingestion
→ dedicated memory vector store
→ Memory Retrieval
→ later Memory Merge / Compression
````

[06.05.2026 / KW19 2026] Memory Retrieval is now implemented as an initial raw retrieval stage. It is not yet Memory Compression and not yet final memory context generation.

Current practical truth:

* Retrieval is implemented and working.
* Retrieval is no longer dense-only; it now includes a real SPLADE scoring branch and weighted RRF fusion.
* ReRanker is implemented and working in code.
* A3 is implemented and working in code as a real usefulness-classification stage over reranked candidates.
* [24.04.2026] A4 Condenser is implemented and working in code as a real three-call evidence-condensation stage after A3.
* [24.04.2026] `SuperPromptProjector` now renders the GUI-visible prompt with clear separation between System, Configuration, User, Retrieved Context Summary, and Raw Retrieved Evidence.
* [03.05.2026 / KW18 2026] Memory Recording is implemented and working as a durable structured-memory capture layer.
* [03.05.2026 / KW18 2026] Memory Ingestion is implemented and working as a separate vector-preparation layer after durable memory save.
* [03.05.2026 / KW18 2026] TextForge / RagLog has been corrected into a usable project logger with sink-based routing/filtering and GUI/CLI/file/archive output behavior.
* [06.05.2026 / KW19 2026] `LogDeveloper` is now used for detailed developer diagnostics in new Memory Retrieval and file-management related code.
* [06.05.2026 / KW19 2026] Memory Retrieval is implemented enough to retrieve raw memory candidates and write them into the SuperPrompt state / GUI-visible retrieved context.
* [06.05.2026 / KW19 2026] The FILES tab is implemented as a server-side memory-history manager backed by SQLite and RAGstream file operations.
* However, the current BERT-style reranker direction is not accepted as the long-term solution, because in practical tests it often worsened ranking quality instead of improving it.

The currently agreed next implementation direction is:

* keep the existing Retrieval / ReRanker stage structure,
* keep the new hybrid Retrieval backbone,
* keep A3 as the current semantic usefulness gate,
* keep A4 as the current live condenser stage,
* keep the Memory Recording and Memory Ingestion truth stable,
* keep initial Memory Retrieval stable,
* continue with Memory Merge / Memory Compression later,
* preserve the ActiveRetrievalBrief idea for the future MemoryMerge stage,
* continue hardening the FILES tab as the official server-side memory-history manager,
* implement Prompt Builder next for the document-RAG pipeline continuation,
* postpone A5 to a later phase because its action may still change before implementation,
* keep ColBERT as the agreed later reranking improvement direction.

---

## 2. What is already implemented

### 2.1 Foundational app structure

* A Generation-1 Streamlit GUI exists.

  * Prompt input area exists.
  * Super-Prompt display area exists.
  * 8 pipeline buttons are visible.
  * Project-based ingestion controls exist.
  * Active project selection exists.
  * Embedded-file display for the selected project exists.
  * [03.05.2026 / KW18 2026] Manual Memory Feed exists.
  * [03.05.2026 / KW18 2026] Memory cards / memory display exists.
  * [03.05.2026 / KW18 2026] Runtime Log display exists and is connected to the TextForge / RagLog GUI sink.
  * [06.05.2026 / KW19 2026] The Streamlit app now has top-level tabs:

```text
MAIN
FILES
HARD RULES
METRICS
GENERAL SETTINGS
```

* [06.05.2026 / KW19 2026] The current tab responsibility is:

```text
MAIN
= current RAGstream working page

FILES
= server-side memory-history manager

HARD RULES
= placeholder for later hard-rule editor

METRICS
= placeholder for logs / token usage / diagnostics / observability

GENERAL SETTINGS
= placeholder for runtime and application settings
```

* [06.05.2026 / KW19 2026] The tab structure is defined in `ui_streamlit.py`, while the MAIN tab still calls the existing `render_page()` from `ui_layout.py`.
* The current GUI supports prompt processing, project creation, file ingestion, active project selection, embedded-file display, manual memory recording, runtime log visibility, and server-side memory-file management.

### 2.2 Deterministic prompt preprocessing

* Deterministic Pre-Processing is implemented.

  * Markdown/header parsing exists.
  * Schema-based field mapping exists.
  * MUST/default handling exists.
  * `prompt_ready` generation exists for the current preprocessing path.
* This stage is already part of the live GUI/controller wiring and acts as the first normalization layer for user input.
* [03.05.2026 / KW18 2026] PreProcessing logging now uses the corrected project-level RagLog import pattern.

### 2.3 JSON-based agent architecture

* JSON-based agent infrastructure is implemented.

  * `AgentFactory` exists.
  * JSON agent loading and transparent config-level caching exist.
  * `LLMClient` exists.
  * [24.04.2026] `LLMClient.responses(...)` exists for A4 / reasoning-style calls, in addition to the existing `chat(...)` path.
  * `AgentPrompt` architecture exists.
* A2 PromptShaper is implemented and already wired.

  * It reads the current `SuperPrompt`.
  * It uses a JSON-configured agent prompt.
  * It calls the LLM.
  * It writes selected values back into `SuperPrompt`.
  * [24.04.2026] It now applies deterministic selector sanitization after parsing and before write-back; invalid, cross-field, invented, malformed, and duplicate ids are removed.
  * [24.04.2026] If a field becomes empty after sanitization, A2 preserves the existing preprocessing value instead of applying catalog defaults.
  * It updates stage/history.
* A3 NLI Gate is implemented and already wired.

  * It reads the reranked candidate set from the current `SuperPrompt`.
  * It uses the JSON-configured neutral Agent Stack.
  * It performs usefulness-only classification.
  * It writes `views_by_stage["a3"]`, `extras["a3_selection_band"]`, `extras["a3_item_decisions"]`, and `final_selection_ids`.
* [24.04.2026] A4 Condenser is now implemented and wired as the next live LLM-based stage after A3.
* [24.04.2026] The current immediate next implementation target for the document-RAG pipeline is Prompt Builder. A5 is intentionally postponed for a later phase because its final action is still open to revision.

### 2.4 SuperPrompt as shared state

* `SuperPrompt` exists as the central shared prompt object.
* It already stores:

  * canonical body fields,
  * stage,
  * stage history,
  * retrieval-related fields,
  * recent conversation placeholder fields,
  * rendered prompt fields.
* In the current implementation direction, `SuperPrompt` is the evolving shared state object across the pipeline rather than a one-off prompt string.
* A general `compose_prompt_ready()` path is part of the recent implementation direction so that later stages can reuse one central render logic instead of keeping rendering scattered across multiple modules.
* [24.04.2026] `SuperPromptProjector` now renders the GUI-visible SuperPrompt into explicit sections:

  * `## System`
  * `## Configuration`
  * `## User`
  * `## Retrieved Context`
* [24.04.2026] A4 condensed context is displayed under `## Retrieved Context / ### Retrieved Context Summary`; raw chunks are displayed under `### Raw Retrieved Evidence` for development/audit visibility.
* [06.05.2026 / KW19 2026] `SuperPrompt` now includes `memory_context_pack` as a runtime field.
* [06.05.2026 / KW19 2026] `SuperPromptProjector` now renders raw memory retrieval candidates from `sp.extras["memory_debug_markdown"]` under the Retrieved Context section.
* [06.05.2026 / KW19 2026] Memory retrieval output is intentionally raw at this stage. It is not yet compressed memory and not yet final prompt context.

### 2.5 Project-based ingestion

* Project-based ingestion is implemented and connected to the GUI.

  * Create Project button exists.
  * Add Files button exists.
  * Files are copied into `data/doc_raw/<project>`.
  * Ingestion runs automatically afterward.
* The project-specific storage model is implemented:

  * `data/doc_raw/<project>`
  * `data/chroma_db/<project>`
  * `data/splade_db/<project>`
  * `file_manifest.json` belongs to the matching Chroma DB project folder.
* The embedded-files list for the active project is visible in the GUI through the manifest/controller path.

### 2.6 Parallel dense + SPLADE document ingestion backend

* Parallel dense + SPLADE ingestion is implemented.

  * Loader exists.
  * Chunker exists.
  * Dense Embedder exists.
  * SPLADE Embedder exists.
  * Chroma vector store exists.
  * SPLADE vector store exists.
  * `IngestionManager` exists.
  * manifest-based diff/hash logic exists.
  * deterministic stable chunk IDs exist.
* The ingestion model now uses one canonical chunking pass and writes the same chunk IDs and metadata into both branches:

  * dense branch → `data/chroma_db/<project>`
  * sparse branch → `data/splade_db/<project>`
* This means ingestion is no longer conceptually dense-only.

### 2.7 Retrieval is implemented as a hybrid stage

* Retrieval is implemented as a deterministic, project-aware hybrid stage.
* Its logic now is:

  * read retrieval query text from the current `SuperPrompt`,
  * use `task`, `purpose`, and `context` as the retrieval source,
  * split the retrieval query into overlapping pieces,
  * run the dense embedding branch on the active project's Chroma document store,
  * select the dense top-k candidate IDs,
  * run the SPLADE sparse branch on the active project's SPLADE store for exactly those same dense-selected candidate IDs,
  * fuse both ranked lists with weighted RRF,
  * reconstruct the real chunk text from `doc_raw/<project>` using the same chunking logic as ingestion,
  * write the result back into `SuperPrompt`.
* Retrieval ranks chunks, reconstructs their text from `doc_raw/<project>`, and writes the selected chunks into `base_context_chunks`.
* [06.05.2026 / KW19 2026] `AppController.run_retrieval(...)` now also calls Memory Retrieval if `MemoryRetriever` is configured.
* [06.05.2026 / KW19 2026] Pressing the Retrieval button now produces both document retrieval output and raw memory retrieval output. It still does not run A3, A4, MemoryMerge, or memory compression.

### 2.8 Retrieval-related GUI/controller integration

* The Retrieval Top-K field exists in the GUI.
* The active project selector exists in the GUI.
* Snapshot keys such as `sp_pre`, `sp_a2`, `sp_rtv`, `sp_rrk`, and `sp_a3` exist so that stage-specific prompt states can be preserved as snapshots rather than overwritten mentally.
* Retrieval is already a live button path after PreProcessing and A2.
* ReRanker is also already wired as a live stage after Retrieval.
* A3 is already wired as a live stage after ReRanker.
* The current Super-Prompt rendering path can now show Retrieval-related score information in the GUI.
* [17.04.2026] The GUI/controller startup path is split into light startup plus background heavy initialization so the page appears before Retrieval / ReRanker warm-up is complete.
* [17.04.2026] Optional slow-component bypass controls are already live in Generation-1:

  * `use Retrieval Splade`
  * `use Reranking Colbert`
* [06.05.2026 / KW19 2026] `ui_streamlit.py` now configures Memory Retrieval during Streamlit startup after `MemoryManager` and `MemoryVectorStore` exist.
* [06.05.2026 / KW19 2026] `ui_actions.py` has a defensive `_ensure_memory_retrieval_configured(...)` helper so older sessions can still configure Memory Retrieval before running Retrieval.

### 2.9 ReRanker is implemented

* ReRanker is implemented as a deterministic stage.
* It is no longer only a planned step.
* The currently implemented ReRanker direction is:

  * BERT-style cross-encoder reranking
  * CPU-only runtime
  * current model:

    * `cross-encoder/ms-marco-MiniLM-L-12-v2`
* Its logic is:

  * read the Retrieval candidates already stored in `SuperPrompt`,
  * rebuild one reranking query from:

    * `task`
    * `purpose`
    * `context`
  * dynamically clean chunk text before scoring,
  * score each `(query, chunk)` pair with the cross-encoder,
  * sort by reranker score,
  * write the reranked view back into `SuperPrompt`.
* ReRanker reranks Retrieval candidates and writes the reranked view back into `SuperPrompt`.
* [06.05.2026 / KW19 2026] ReRanker currently operates only on document retrieval results. Memory candidates remain separately stored in `SuperPrompt`.

### 2.10 A3 is implemented as a real stage

* A3 is implemented as a real semantic stage.
* It is no longer only a placeholder or abstract future idea.
* The current implemented A3 direction is:

  * usefulness-only classification over reranked candidates,
  * one global `selection_band`,
  * one usefulness decision per candidate chunk,
  * deterministic useful-first selection with borderline fallback.
* Important current A3 truth:

  * long real chunk ids are not shown to the LLM,
  * local chunk ids `1..N` are used in the prompt and mapped back internally,
  * chunk-internal heading markers are sanitized to avoid prompt-structure conflicts,
  * duplicate marking has been intentionally removed.
* A3 already performs meaningful semantic filtering and is considered good enough to keep as the current stage truth while the next work moves to Prompt Builder.
* [06.05.2026 / KW19 2026] A3 does not yet process raw memory candidates. Memory-specific semantic filtering is reserved for later MemoryMerge / Memory Compression design.

### 2.11 Why the current ReRanker direction is not accepted as final

* Practical evaluation showed that the current BERT-style reranker often did not improve the already good Retrieval ranking.
* In important real examples, it made the ranking worse:

  * relevant chunks were demoted too aggressively,
  * some weaker or less useful chunks were promoted,
  * and the final ranking became less trustworthy than dense Retrieval alone.
* Therefore the current BERT-style reranking direction is considered unsatisfactory as the future production direction.

### 2.12 A4 Condenser is implemented

* [24.04.2026] A4 Condenser is implemented as a live stage after A3.
* [24.04.2026] The implementation files are:

  * `ragstream/agents/a4_condenser.py`
  * `ragstream/agents/a4_det_processing.py`
  * `ragstream/agents/a4_llm_helper.py`
* [24.04.2026] A4 uses three exact JSON configurations:

  * `data/agents/a4_condenser/chunk_phraser/a4_1_001.json`
  * `data/agents/a4_condenser/chunk_classifier/a4_2_001.json`
  * `data/agents/a4_condenser/final_condenser/a4_3_001.json`
* [24.04.2026] The implemented workflow is:

  * prepare selected A3-useful chunks,
  * run Chunk Phraser,
  * prepare active class definitions,
  * run Chunk Classifier,
  * build grouped chunk package,
  * run Final Condenser,
  * finalize A4 output into SuperPrompt.
* [24.04.2026] A4 writes:

  * `S_CTX_MD`,
  * `views_by_stage["a4"]`,
  * `final_selection_ids`,
  * A4 diagnostic fields in `sp.extras`,
  * `stage = "a4"` and stage history.
* [24.04.2026] A4 uses `LLMClient.responses(...)` and stable `prompt_cache_key="a4_condenser_shared_prefix"` through `A4LLMHelper`.
* [24.04.2026] The final condenser prompt was corrected so A4 produces neutral internal context, not a polished final answer to the user.
* [24.04.2026] If classifier output is empty or unusable, A4 continues through fallback grouping instead of crashing; the warning belongs in logs/status, not inside the final SuperPrompt.
* [06.05.2026 / KW19 2026] A4 currently condenses document evidence, not MemoryContextPack content.

### 2.13 GUI-visible SuperPrompt rendering hardening

* [24.04.2026] `SuperPromptProjector.compose_prompt_ready()` now renders the GUI-visible SuperPrompt with stable top-level separation:

  * `## System`
  * `## Configuration`
  * `## User`
  * `## Retrieved Context`
* [24.04.2026] The real user task appears only under `## User / ### Task`.
* [24.04.2026] A4 `S_CTX_MD` appears under `## Retrieved Context / ### Retrieved Context Summary` with a neutral guard sentence explaining that it is supporting context, not part of the task.
* [24.04.2026] Raw retrieved chunks appear under `## Retrieved Context / ### Raw Retrieved Evidence`.
* [24.04.2026] Raw source Markdown headings inside retrieved chunks are neutralized to markers such as `[H1]`, `[H2]`, and `[H3]`.
* [24.04.2026] This hardening prevents retrieved or condensed context from visually merging with the user task.
* [06.05.2026 / KW19 2026] Raw memory retrieval candidates are displayed below raw retrieved document evidence when available.
* [06.05.2026 / KW19 2026] This current memory display is intentionally a development/audit view, not the final compressed memory answer context.

### 2.14 AWS Phase-1 deployment

* AWS Phase-1 deployment is implemented and working.
* The current live deployment already provides:

  * GitHub Actions builds and pushes Docker image to ECR,
  * EC2 pulls the latest image and starts the container,
  * nginx reverse proxy is working,
  * HTTPS/TLS is working,
  * Route53 update is working,
  * SSM secret loading is working,
  * persistent runtime data on EC2/EBS is working.
* The public network path is already stable:

  * Route53 → AWS public IPv4 → EC2 → nginx → Docker → Streamlit.
* [03.05.2026 / KW18 2026] The Memory subsystem uses the same project-relative runtime-data principle under `data/memory/`. AWS documentation may still explicitly mention `doc_raw` and `chroma_db`; the Memory data path should be aligned with the persistent `/app/data` mount before AWS production use of Memory.
* [06.05.2026 / KW19 2026] The current architecture is still local-first / single-user / single-workspace, even if deployed on AWS. It is not yet a multi-user SaaS design.
* [06.05.2026 / KW19 2026] Future multi-user extension remains possible through stable ownership identifiers such as `user_id` and `workspace_id` in SQLite, but this is not part of the current implementation.

### 2.15 TextForge / RagLog logging is implemented and corrected

* [03.05.2026 / KW18 2026] TextForge / RagLog is implemented as the project logging subsystem.
* The implemented logging files are:

  * `ragstream/textforge/TextForge.py`
  * `ragstream/textforge/TextSink.py`
  * `ragstream/textforge/FileSink.py`
  * `ragstream/textforge/CliSink.py`
  * `ragstream/textforge/GUISink.py`
  * `ragstream/textforge/RagLog.py`
* The logger architecture uses:

  * one `TextForge` facade,
  * multiple sinks,
  * sink-level type filtering,
  * sink-level sensitivity filtering,
  * `b_enable` routing flags.
* The current intended public logger functions in `RagLog.py` are:

  * `LogALL`
  * `LogNoGUI`
  * `LogConf`
  * [06.05.2026 / KW19 2026] `LogDeveloper`
* The corrected application import pattern is:

```python
from ragstream.textforge.RagLog import LogALL as logger
```

* [06.05.2026 / KW19 2026] New developer-diagnostic modules should additionally use:

```python
from ragstream.textforge.RagLog import LogDeveloper as logger_dev
```

* The important corrected rule is:

  * `type` and `sensitivity` are message labels,
  * their default values are only fallback defaults,
  * `LogALL`, `LogNoGUI`, and `LogConf` must not apply additional semantic filtering,
  * filtering happens inside the sinks through `accept_types` and `accept_sensitivities`.
* Current sink routing intention:

  * `LogALL` routes to archive, public run file, CLI, and GUI.
  * `LogNoGUI` routes to archive, public run file, and CLI.
  * `LogConf` routes only to archive.
  * `LogDeveloper` routes detailed internal diagnostics according to the developer logging flag/configuration.
* The GUI log now receives public runtime messages through the GUI sink.
* The CLI and file/archive sinks can receive more detailed internal messages according to their own sink configuration.
* [03.05.2026 / KW18 2026] The previous `st.session_state.raglog` helper/wrapper direction has been rejected. Application modules should import the public RagLog function directly instead of passing logger objects through Streamlit state.
* [06.05.2026 / KW19 2026] Memory Retrieval developer diagnostics log detailed payloads such as vector hits, SQLite candidates, metadata, scores, and packed memory context through `logger_dev`.
* [06.05.2026 / KW19 2026] MAIN Runtime Log is append-style operational logging. FILES status messages are intentionally latest-action status only and overwrite previous FILES action state to avoid UI noise.

### 2.16 Memory Recording is implemented

* [03.05.2026 / KW18 2026] Memory Recording is implemented as a first-class RAGstream subsystem.
* It is not runtime logging.
* It is not TextForge / RagLog.
* It is not a sink.
* It manages structured, reusable memory records.
* The implemented memory recording files are:

  * `ragstream/memory/memory_record.py`
  * `ragstream/memory/memory_manager.py`
  * `ragstream/memory/memory_actions.py`
* The central objects are:

  * `MemoryRecord`
  * `MemoryManager`
* `MemoryRecord` represents one accepted prompt/response memory unit.
* `MemoryManager` owns one active memory history and maintains:

  * `file_id`,
  * memory filenames,
  * live `records`,
  * metainfo,
  * `.ragmem` persistence,
  * `.ragmeta.json` persistence,
  * SQLite synchronization.
* `memory_actions.py` provides the workflow boundary for capturing memory pairs from the GUI and later from model/tool capture paths.
* The implemented persistent memory layout is:

```text
data/memory/
├── memory_index.sqlite3
├── vector_db/
└── files/
    ├── *.ragmem
    └── *.ragmeta.json
```

* Current Memory Recording behavior:

  * full Q/A remains the permanent truth,
  * `.ragmem` stores durable stable body data,
  * `.ragmeta.json` stores current readable editable metadata,
  * SQLite indexes memory histories and records,
  * GUI tag/source-mode/direct-recall edits are synchronized through MemoryManager logic.
* [06.05.2026 / KW19 2026] The persistence authority split was corrected:

```text
.ragmem
= stable append-only memory body

.ragmeta.json
= current readable/editable metadata mirror

SQLite
= current query/index layer
```

* [06.05.2026 / KW19 2026] Editable GUI metadata must not be written as authoritative mutable data into `.ragmem`.
* [06.05.2026 / KW19 2026] Editable GUI metadata includes:

```text
tag
user_keywords
retrieval_source_mode
direct_recall_key
```

* [06.05.2026 / KW19 2026] `.ragmem` should only contain stable body fields such as:

```text
record_id
parent_id
created_at_utc
input_text
output_text
source
input_hash
output_hash
```

* [06.05.2026 / KW19 2026] `sync_gui_edits(...)` updates RAM, `.ragmeta.json`, and SQLite. It must not rewrite `.ragmem`.
* [06.05.2026 / KW19 2026] `load_history(...)` loads stable body from `.ragmem` and overlays current metadata from `.ragmeta.json`.
* [06.05.2026 / KW19 2026] User Keywords were removed from the GUI, but the field remains in the data model as an empty/future-use metadata field.
* [06.05.2026 / KW19 2026] First memory history creation is now automatic. The previous manual “enter Memory Title before first save” flow was removed.
* [06.05.2026 / KW19 2026] When the first MemoryRecord is saved and no active memory history exists, RAGstream auto-creates the memory history name using the first available YAKE/auto keyword, with fallback to active project name, source, or `Memory`.
* [06.05.2026 / KW19 2026] Manual memory creation through the FILES tab is also supported through the `New Memory` action.
* Memory Recording intentionally does not perform:

  * semantic retrieval,
  * compression,
  * final memory-context generation.

### 2.17 Memory Ingestion is implemented

* [03.05.2026 / KW18 2026] Memory Ingestion is implemented as a separate layer after Memory Recording.
* The implemented memory ingestion files are:

  * `ragstream/memory/memory_ingestion_manager.py`
  * `ragstream/memory/memory_chunker.py`
  * `ragstream/memory/memory_vector_store.py`
* The central objects are:

  * `MemoryIngestionManager`
  * `MemoryChunker`
  * `MemoryVectorStore`
* The dedicated memory vector store is separate from document vector stores.
* The implemented memory vector path is:

```text
data/memory/vector_db/
```

* The conceptual Chroma collection is:

```text
memory_vectors
```

* Memory Ingestion reads accepted `MemoryRecord` objects from the live `MemoryManager.records`.
* Memory Ingestion creates deterministic vector entries for:

  * `record_handle`
  * `question`
  * `answer`
* The `record_handle` vector supports broad record discovery.
* The question vectors support matching a current question against earlier questions.
* The answer vectors support finding useful old answer material.
* Every memory vector entry links back to its parent `MemoryRecord` through metadata.
* Memory Ingestion keeps full Q/A truth in Memory Recording. The vector layer is only a retrieval index.
* Memory Ingestion uses embeddings but does not call an LLM.
* Memory Ingestion does not summarize, compress, or infer intent.
* Memory Ingestion is intended to be idempotent:

  * existing vectors for a record can be removed/replaced,
  * re-ingesting the same record should not create duplicate vector entries.
* Runtime flow now exists:

```text
Manual Memory Feed
→ memory_actions.py
→ MemoryManager.capture_pair(...)
→ durable MemoryRecord saved
→ MemoryIngestionManager.ingest_record_async(...)
→ MemoryChunker builds entries
→ MemoryVectorStore writes vectors
→ data/memory/vector_db/ updated
```

* Required ordering is implemented conceptually and in wiring:

  * memory truth is saved first,
  * vector ingestion is scheduled after durable save.
* If Memory Ingestion fails, Memory Recording remains valid.
* [03.05.2026 / KW18 2026] Async ingestion was introduced so normal GUI interaction does not wait for embedding/vector writing.
* [03.05.2026 / KW18 2026] A Streamlit `ScriptRunContext` warning was observed when the background ingestion thread logged through the GUI sink. The agreed fix is to attach the current Streamlit script context to the ingestion thread before `thread.start()` so `GuiSink` can update `st.session_state` without warning.
* [06.05.2026 / KW19 2026] `MemoryVectorStore` now supports deletion by `file_id` through `delete_file(...)` and counting by `file_id` through `count_file(...)`.
* [06.05.2026 / KW19 2026] Rename-safe memory design decision: memory vector metadata should not depend on `filename_ragmem` or `filename_meta`. Vector metadata should use stable identifiers such as `file_id`, `record_id`, `role`, and block/vector ids.
* [06.05.2026 / KW19 2026] Filenames remain mutable path/display fields, not vector identity fields.

### 2.18 Initial Memory Retrieval is implemented

* [06.05.2026 / KW19 2026] Initial Memory Retrieval is implemented.
* The new implemented files are:

```text
ragstream/retrieval/retriever_mem.py
ragstream/memory/memory_context_pack.py
ragstream/memory/memory_index_lookup.py
ragstream/memory/memory_scoring.py
```

* The existing files updated for initial Memory Retrieval were:

```text
ragstream/app/controller.py
ragstream/app/ui_actions.py
ragstream/app/ui_streamlit.py
ragstream/orchestration/super_prompt.py
ragstream/orchestration/superprompt_projector.py
ragstream/memory/memory_vector_store.py
ragstream/config/runtime_config.json
```

* `retriever_mem.py` is located under `ragstream/retrieval/` because it is a retrieval-stage orchestrator.
* Helper modules remain under `ragstream/memory/`.
* The current Memory Retrieval design separates:

```text
MemoryRetriever
= stage orchestrator

MemoryIndexLookup
= SQLite + .ragmem body lookup

MemoryScorer
= vector-hit scoring and parent-record aggregation

MemoryContextPack
= runtime container for raw memory retrieval output
```

* `MemoryContextPack` is a runtime object only.
* `MemoryContextPack` is not durable memory truth.
* `MemoryContextPack` currently carries:

```text
working_memory_candidates
episodic_candidates
semantic_memory_chunks
direct_recall_candidate
selection_diagnostics
token_budget_report
```

* Current retrieval result groups:

  * working memory candidates,
  * episodic parent-record candidates,
  * raw semantic memory chunks,
  * optional Direct Recall candidate,
  * diagnostics.
* Memory Retrieval currently reads from:

  * current `SuperPrompt`,
  * active `MemoryManager`,
  * `MemoryVectorStore`,
  * `memory_index.sqlite3`,
  * runtime config under `memory_retrieval`.
* Memory Retrieval currently writes into:

  * `sp.memory_context_pack`,
  * `sp.extras["memory_context_pack"]`,
  * `sp.extras["memory_debug_markdown"]`,
  * `sp.extras["memory_retrieval_counts"]`.
* Memory Retrieval does not run:

  * A3,
  * A4,
  * MemoryMerge,
  * final memory compression,
  * final prompt building.
* [06.05.2026 / KW19 2026] Memory Retrieval is triggered when the normal Retrieval button runs, after document retrieval.
* [06.05.2026 / KW19 2026] `runtime_config.json` now contains `memory_retrieval` configuration, including:

  * tag catalog,
  * retrieval source modes,
  * parent score weights,
  * working memory limits,
  * episodic memory limits,
  * Direct Recall limits,
  * semantic memory chunk limits.

### 2.19 Server-side Memory Files tab is implemented

* [06.05.2026 / KW19 2026] The FILES tab is implemented as the official server-side memory-history manager.
* Implemented files:

```text
ragstream/app/ui_files.py
ragstream/app/ui_actions_files.py
ragstream/memory/memory_file_manager.py
```

* `ui_files.py` owns the FILES tab layout.
* `ui_actions_files.py` owns thin Streamlit callbacks.
* `memory_file_manager.py` owns real backend file operations.
* The FILES tab now lists memory histories from SQLite, not by raw manual file browsing.
* The FILES tab displays:

```text
Filename
Created
Updated
Records
```

* The table uses native `st.dataframe` row selection.
* The table supports frontend column sorting.
* The table uses soft alternating row coloring with:

```text
#E2FBD8
```

* Current known table-color limitation:

  * native `st.dataframe` frontend sorting does not re-run Python styling logic,
  * therefore alternating row colors remain based on backend order,
  * default backend order is still `updated_at_utc DESC`.
* The FILES tab supports:

```text
New Memory
Load
Rename
Delete
```

* `New Memory` creates an empty `.ragmem` + `.ragmeta.json`, inserts a SQLite `memory_files` row, and makes the new history active.
* `Load` calls `MemoryManager.load_history(file_id)` and makes the selected memory history active.
* `Rename` renames the physical `.ragmem` and `.ragmeta.json`, updates SQLite `memory_files`, and updates file-level fields inside `.ragmeta.json`.
* `Delete` deletes:

```text
physical .ragmem
physical .ragmeta.json
SQLite memory_files row
SQLite memory_records rows
memory vectors by file_id
```

* Delete uses a two-step confirmation flow where the user must type:

```text
delete
```

* [06.05.2026 / KW19 2026] Memory histories must be managed through RAGstream. Manual external rename/delete of `.ragmem` or `.ragmeta.json` can break the link between SQLite file_id and physical files.
* [06.05.2026 / KW19 2026] SQLite `memory_files` is the authority for memory-history listing and path resolution.
* [06.05.2026 / KW19 2026] Filenames are mutable path/display fields. `file_id` is the stable identity.

### 2.20 Future ActiveRetrievalBrief requirement was captured

* [06.05.2026 / KW19 2026] The future `ActiveRetrievalBrief` design decision was captured for later MemoryMerge / Memory Compression work.
* The core idea is:

```text
Each MemoryRecord gets its own immutable cumulative ActiveRetrievalBrief.
```

* It is not one global mutable brief.
* It is a query-independent historical snapshot attached to each MemoryRecord.
* It represents the conversation/work context from the beginning of the active memory history up to that MemoryRecord.
* Runtime should normally use:

```text
latest clean non-Black ActiveRetrievalBrief
```

* Future fields:

```text
qa_summary
active_retrieval_brief
active_retrieval_brief_contributor_ids
```

* Intended future use for document retrieval:

```text
TASK
+ PURPOSE
+ CONTEXT
+ latest clean ActiveRetrievalBrief
```

* Intended future use for memory retrieval:

```text
current query support
+ latest clean ActiveRetrievalBrief
```

* The brief should be generated by LLM semantic rules, not by fixed 50/50 or 70/30 numeric weighting.
* The updater rules should preserve stable context, add durable new information, treat corrections as high-importance scope constraints, ignore noise/insults as topic content, and keep the brief compact.
* `active_retrieval_brief_contributor_ids` are required so Black-tagged records can be avoided by selecting the latest brief whose contributors do not include Black records.
* This belongs to future MemoryMerge / Memory Compression, not the current raw Memory Retrieval stage.

---

## 3. What is intentionally not complete yet

### 3.1 Prompt Builder

* `prompt_builder.py` exists as a project module and the deterministic final-assembly concept is defined in the requirements.
* It is not yet the completed final operational stage in the current Generation-1 GUI flow.
* [24.04.2026] Prompt Builder is now the immediate next target after the successful A4 implementation.
* [24.04.2026] Prompt Builder should reuse or align with the current `SuperPromptProjector` structure so GUI preview and final-send prompt assembly do not diverge.
* [03.05.2026 / KW18 2026] Prompt Builder remains incomplete. The KW18 Memory work did not replace this pipeline milestone.
* [06.05.2026 / KW19 2026] The initial Memory Retrieval and FILES tab work did not replace Prompt Builder. Prompt Builder remains a separate document-RAG pipeline milestone.

### 3.2 A5 Format Enforcer

* A5 exists in the long-range 8-stage contract, but it is not a live completed operational stage.
* [21.04.2026] A5 is intentionally postponed to a later phase.
* [21.04.2026] Its future action may be revised before implementation, so the current requirement contract should be treated as provisional rather than implementation-locked.

### 3.3 Memory Merge, Memory Compression, and final memory context

* [03.05.2026 / KW18 2026] The older broad “conversation history ingestion” wording is no longer accurate as a description of the current Memory implementation.
* Memory Recording is now implemented.
* Memory Ingestion is now implemented.
* [06.05.2026 / KW19 2026] Initial raw Memory Retrieval is now implemented.
* What remains intentionally incomplete is:

  * MemoryMerge,
  * Memory Compression,
  * compressed episodic-memory summaries,
  * compressed working-memory context,
  * Direct Recall final handling,
  * ActiveRetrievalBrief generation/update,
  * final memory-context preparation for the final prompt,
  * advanced memory-management GUI beyond the current FILES tab.
* Initial Memory Retrieval searches and reconstructs raw candidates.
* Later MemoryMerge must decide what to keep, compress, summarize, and inject.
* Memory Compression remains runtime-only and must never overwrite:

  * `MemoryRecord.input_text`,
  * `MemoryRecord.output_text`,
  * stable `.ragmem` body fields,
  * the durable truth of `.ragmeta.json`,
  * the durable truth of `memory_index.sqlite3`.

### 3.4 Logger production hardening

* [03.05.2026 / KW18 2026] TextForge / RagLog is implemented and corrected, but further production hardening may still be useful.
* Open points for later hardening:

  * final decision about normal vs developer logging mode,
  * final retention/rotation policy for archive and public run logs,
  * final AWS log persistence policy under `/app/data`,
  * possible regression tests for sink routing and filtering,
  * possible thread-safety hardening around GUI logging and background workers.
* These points do not block the current Memory Recording / Memory Ingestion / initial Memory Retrieval implementation.
* [06.05.2026 / KW19 2026] Metrics / Observability should be treated as a broader future UI area than just “logs.” The METRICS tab should later include logs, token usage, retrieval counts, memory retrieval diagnostics, cost estimates, latency, success/failure status, and developer/debug summaries.

### 3.5 Multi-user support

* [06.05.2026 / KW19 2026] RAGstream is currently local-first / single-user / single-workspace.
* Even on AWS, the current intended deployment is one private instance, not a multi-user SaaS system.
* Future extension is possible through stable ownership fields such as:

```text
user_id
workspace_id
file_id
record_id
```

* The future professional pattern would be:

```text
SQLite source of truth:
user_id → workspace_id → file_id → record_id → paths / metadata / vector references
```

* Files can remain in shared server-side storage as long as SQLite controls ownership, paths, and visibility.
* This is not implemented yet and is not required for the current single-user development path.

---

## 4. Current immediate implementation plan

### 4.1 Immediate next work order

[24.04.2026] The agreed document-RAG pipeline work order was:

1. keep current Retrieval / ReRanker / A3 / A4 truth stable,
2. implement Prompt Builder,
3. postpone A5,
4. revisit ReRanker improvement with ColBERT after the pipeline is stable through A4 and Prompt Builder.

[03.05.2026 / KW18 2026] After the KW18 Memory work, the Memory-subsystem work order was:

1. keep Memory Recording stable,
2. keep Memory Ingestion stable,
3. implement Memory Retrieval,
4. reconstruct parent-aware `MemoryContextPack`,
5. only then decide Memory Compression and SuperPrompt memory-section injection.

[06.05.2026 / KW19 2026] Current status after this chat:

1. Memory Recording is stable enough to continue.
2. Memory Ingestion is stable enough to continue.
3. Initial Memory Retrieval is implemented.
4. Raw `MemoryContextPack` exists and is injected into SuperPrompt state / GUI preview.
5. Server-side FILES tab exists for Memory history management.
6. The next Memory-subsystem direction is MemoryMerge / Memory Compression, not another redesign of Recording/Ingestion.
7. The FILES tab should continue to be polished only where needed for presentation quality and safe server-side operations.
8. ActiveRetrievalBrief is captured as a future requirement for MemoryMerge.

The two tracks remain related but separate:

```text
Document-RAG pipeline next:
  Prompt Builder

Memory subsystem next:
  MemoryMerge / Memory Compression / ActiveRetrievalBrief later
```

### 4.2 Why this order is now preferred

* Retrieval is already strong enough to continue development.
* ReRanker is live enough to keep the stage contract while its long-term replacement is still open.
* A3 is already good enough to be treated as a real stage.
* [24.04.2026] A4 is now implemented and good enough to be treated as the current condenser stage.
* The biggest missing operational gap in the end-to-end document-RAG pipeline is now downstream of A4:

  * final deterministic prompt assembly,
  * production decision on raw evidence vs. debug/audit evidence visibility.
* Therefore the highest leverage in the document-RAG pipeline remains Prompt Builder, not more A3/A4 redesign.
* [03.05.2026 / KW18 2026] The biggest missing operational gap in the Memory subsystem was Memory Retrieval:

  * Memory Recording already stores the durable truth,
  * Memory Ingestion already prepares searchable vectors,
  * Retrieval had to reconstruct useful parent-aware Q/A context rather than returning isolated vector chunks.
* [06.05.2026 / KW19 2026] That initial Memory Retrieval gap is now closed at raw-candidate level.
* The next Memory gap is higher-level selection/compression:

  * which memory episodes to keep,
  * how to compress them,
  * how Direct Recall should override normal memory,
  * how ActiveRetrievalBrief should support weak or corrective user turns,
  * how final memory context should enter Prompt Builder.

---

## 5. Compact bottom-line statement

RAGstream is no longer only an ingestion + retrieval prototype.
It already has:

* working preprocessing,
* working JSON-based Agent Stack,
* working A2,
* working project-based ingestion,
* working hybrid Retrieval,
* working deterministic ReRanker,
* working A3 usefulness filtering,
* [24.04.2026] working A4 evidence condensation into `S_CTX_MD`,
* [24.04.2026] hardened GUI-visible SuperPrompt rendering,
* working AWS Phase-1 deployment,
* [03.05.2026 / KW18 2026] working Memory Recording with `.ragmem`, `.ragmeta.json`, and SQLite persistence,
* [03.05.2026 / KW18 2026] working Memory Ingestion into a dedicated memory vector store,
* [03.05.2026 / KW18 2026] corrected TextForge / RagLog logging with archive/file/CLI/GUI sink routing,
* [06.05.2026 / KW19 2026] corrected MemoryRecord persistence authority split,
* [06.05.2026 / KW19 2026] auto-created memory histories from first accepted MemoryRecord,
* [06.05.2026 / KW19 2026] initial Memory Retrieval with `MemoryContextPack`,
* [06.05.2026 / KW19 2026] raw memory retrieval display inside SuperPrompt rendering,
* [06.05.2026 / KW19 2026] server-side FILES tab for New / Load / Rename / Delete memory histories,
* [06.05.2026 / KW19 2026] file-level delete cleanup across physical files, SQLite, and memory vectors,
* [06.05.2026 / KW19 2026] future ActiveRetrievalBrief requirement captured for MemoryMerge.

[24.04.2026] The immediate next document-RAG milestone is Prompt Builder. A4 Condenser is implemented and live; A5 is postponed and may be redefined before it is built.

[06.05.2026 / KW19 2026] The immediate next Memory milestone is MemoryMerge / Memory Compression. Memory Recording, Memory Ingestion, initial Memory Retrieval, and server-side Memory Files management are now implemented; the next work must decide how raw memory candidates become compressed, controlled, final memory context.

```
```
