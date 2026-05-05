Updated based on the existing status file plus the current Memory / Logger documents and current project tree/code index.    

````markdown
# RAGstream_Implementation_Status.md

Last update: 03.05.2026

Purpose:
- This file is a compact implementation status snapshot.
- It records what is already working now.
- It also records the currently agreed next implementation direction.
- It is not a requirement file and not a final roadmap.
- For future updates, newly added decisions and implementation changes should be date-stamped inside the relevant section so chronological evolution remains visible.
- [03.05.2026 / KW18 2026] This update adds the implemented Memory Recording layer, the implemented Memory Ingestion layer, and the corrected TextForge / RagLog logging layer.

---

## 1. High-level picture

RAGstream already has a stable foundation in eight major layers:

1. foundational prompt processing and GUI/controller structure,
2. JSON-based agent architecture with working A2, A3, and A4 stages,
3. project-based document ingestion with manifest-based file tracking,
4. hybrid document retrieval with dense first-pass selection + SPLADE scoring on the same candidate IDs + weighted RRF,
5. GUI-visible SuperPrompt rendering through `SuperPromptProjector`,
6. a working AWS Phase-1 deployment with persistent runtime data outside the image,
7. [03.05.2026 / KW18 2026] structured Memory Recording with durable `.ragmem`, `.ragmeta.json`, and SQLite persistence,
8. [03.05.2026 / KW18 2026] structured Memory Ingestion with dedicated memory vectors and TextForge / RagLog logging support.

The pipeline now reaches from prompt input and A2 shaping to project-aware hybrid chunk selection from the active document database, and it also includes a deterministic ReRanker stage, a real A3 stage, and a live A4 Condenser that writes `S_CTX_MD`.

[03.05.2026 / KW18 2026] In addition to the document RAG pipeline, RAGstream now has a separate Memory subsystem path:

```text
accepted prompt + accepted response
→ Memory Recording
→ durable MemoryRecord truth
→ Memory Ingestion
→ dedicated memory vector store
→ later Memory Retrieval / Memory Compression
````

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
* However, the current BERT-style reranker direction is not accepted as the long-term solution, because in practical tests it often worsened ranking quality instead of improving it.

The currently agreed next implementation direction is:

* keep the existing Retrieval / ReRanker stage structure,
* keep the new hybrid Retrieval backbone,
* keep A3 as the current semantic usefulness gate,
* keep A4 as the current live condenser stage,
* keep the Memory Recording and Memory Ingestion truth stable,
* implement Memory Retrieval next for the Memory subsystem,
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
* The current GUI supports prompt processing, project creation, file ingestion, active project selection, embedded-file display, manual memory recording, and runtime log visibility.

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
* [03.05.2026 / KW18 2026] Memory context is not yet injected into SuperPrompt. The implemented state stops at Memory Recording + Memory Ingestion. Memory Retrieval and MemoryContextPack injection remain next work.

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
* The corrected application import pattern is:

```python
from ragstream.textforge.RagLog import LogALL as logger
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
* The GUI log now receives public runtime messages through the GUI sink.
* The CLI and file/archive sinks can receive more detailed internal messages according to their own sink configuration.
* [03.05.2026 / KW18 2026] The previous `st.session_state.raglog` helper/wrapper direction has been rejected. Application modules should import the public RagLog function directly instead of passing logger objects through Streamlit state.

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
└── files/
    ├── *.ragmem
    └── *.ragmeta.json
```

* The current GUI supports manual memory capture:

  * user prompt text is taken from the Prompt field,
  * accepted answer/output is pasted into Manual Memory Feed,
  * the first memory file is created only after a title is provided,
  * the MemoryRecord is stored durably,
  * memory cards are displayed in the Streamlit GUI.
* Current Memory Recording behavior:

  * full Q/A remains the permanent truth,
  * `.ragmem` stores the durable memory text,
  * `.ragmeta.json` stores sidecar metadata rebuilt from records,
  * SQLite indexes memory histories and records,
  * GUI tag/user-keyword edits are synchronized through MemoryManager logic.
* Memory Recording intentionally does not perform:

  * vector ingestion,
  * semantic retrieval,
  * compression,
  * SuperPrompt memory injection.

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

---

## 3. What is intentionally not complete yet

### 3.1 Prompt Builder

* `prompt_builder.py` exists as a project module and the deterministic final-assembly concept is defined in the requirements.
* It is not yet the completed final operational stage in the current Generation-1 GUI flow.
* [24.04.2026] Prompt Builder is now the immediate next target after the successful A4 implementation.
* [24.04.2026] Prompt Builder should reuse or align with the current `SuperPromptProjector` structure so GUI preview and final-send prompt assembly do not diverge.
* [03.05.2026 / KW18 2026] Prompt Builder remains incomplete. The KW18 Memory work did not replace this pipeline milestone.

### 3.2 A5 Format Enforcer

* A5 exists in the long-range 8-stage contract, but it is not a live completed operational stage.
* [21.04.2026] A5 is intentionally postponed to a later phase.
* [21.04.2026] Its future action may be revised before implementation, so the current requirement contract should be treated as provisional rather than implementation-locked.

### 3.3 Memory Retrieval, Memory Compression, and SuperPrompt memory injection

* [03.05.2026 / KW18 2026] The older broad “conversation history ingestion” wording is no longer accurate as a description of the current Memory implementation.
* Memory Recording is now implemented.
* Memory Ingestion is now implemented.
* What remains intentionally incomplete is:

  * Memory Retrieval,
  * MemoryContextPack reconstruction,
  * Memory Compression,
  * tag-governed memory retrieval,
  * cross-chat / cross-history import,
  * SuperPrompt memory-section injection,
  * advanced memory-management GUI.
* Memory Retrieval must later search:

  * record-handle vectors,
  * question vectors,
  * answer vectors.
* Memory Retrieval must group hits at parent `MemoryRecord` level, not treat memory vectors as isolated anonymous chunks.
* The intended output of later Memory Retrieval is:

```text
MemoryContextPack
=
old question anchor
+
relevant answer block/window
+
record metadata/reference
```

* Memory Compression remains runtime-only and must never overwrite:

  * `MemoryRecord.input_text`,
  * `MemoryRecord.output_text`,
  * `.ragmem`,
  * `.ragmeta.json`,
  * `memory_index.sqlite3`.

### 3.4 Logger production hardening

* [03.05.2026 / KW18 2026] TextForge / RagLog is implemented and corrected, but further production hardening may still be useful.
* Open points for later hardening:

  * final decision about normal vs developer logging mode,
  * final retention/rotation policy for archive and public run logs,
  * final AWS log persistence policy under `/app/data`,
  * possible regression tests for sink routing and filtering,
  * possible thread-safety hardening around GUI logging and background workers.
* These points do not block the current Memory Recording / Memory Ingestion implementation.

---

## 4. Current immediate implementation plan

### 4.1 Immediate next work order

[24.04.2026] The agreed document-RAG pipeline work order was:

1. keep current Retrieval / ReRanker / A3 / A4 truth stable,
2. implement Prompt Builder,
3. postpone A5,
4. revisit ReRanker improvement with ColBERT after the pipeline is stable through A4 and Prompt Builder.

[03.05.2026 / KW18 2026] After the KW18 Memory work, the current Memory-subsystem work order is:

1. keep Memory Recording stable,
2. keep Memory Ingestion stable,
3. implement Memory Retrieval,
4. reconstruct parent-aware `MemoryContextPack`,
5. only then decide Memory Compression and SuperPrompt memory-section injection.

These two tracks are related but separate:

```text
Document-RAG pipeline next:
  Prompt Builder

Memory subsystem next:
  Memory Retrieval
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
* [03.05.2026 / KW18 2026] The biggest missing operational gap in the Memory subsystem is now Memory Retrieval:

  * Memory Recording already stores the durable truth,
  * Memory Ingestion already prepares searchable vectors,
  * Retrieval must now reconstruct useful parent-aware Q/A context rather than returning isolated vector chunks.
* Therefore the highest leverage in the Memory subsystem is Memory Retrieval, not more Memory Recording redesign.

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
* [03.05.2026 / KW18 2026] corrected TextForge / RagLog logging with archive/file/CLI/GUI sink routing.

[24.04.2026] The immediate next document-RAG milestone is Prompt Builder. A4 Condenser is implemented and live; A5 is postponed and may be redefined before it is built.

[03.05.2026 / KW18 2026] The immediate next Memory milestone is Memory Retrieval. Memory Recording and Memory Ingestion are now implemented; Memory Retrieval must next search memory vectors, group hits by parent `MemoryRecord`, and reconstruct a reduced Q/A-shaped `MemoryContextPack`.

```
```
