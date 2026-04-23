# Architecture – RAGstream (21.04.2026)

Last sync: 21.04.2026

Note for future maintenance:
- When new implementation-aligned decisions or features are added here, they should be date-stamped inline so the chronology stays visible.

This document describes the end-to-end architecture of RAGstream and sits between the requirements and the UML diagrams. It explains how the main subsystems (Ingestion & Memory, RAG Pipeline, Agent Stack, Controller, GUI, and Session/History) fit together and how the core data models flow between them.

Relationship to the requirements:

* Requirements_Main.md defines the overall scope and shared concepts such as SuperPrompt.
* Requirements_RAG_Pipeline.md defines the 8-stage RAG pipeline and all SuperPrompt invariants along the pipeline.
* Requirements_AgentStack.md defines how LLM-using agents are built (AgentFactory, AgentPrompt, llm_client, JSON configs).
* Requirements_Orchestration_Controller.md defines what controller.py does and how it calls deterministic stages and agents.
* Requirements_Ingestion_Memory.md defines the ingestion pipeline, FileManifest, and how documents and history are stored.
* Requirements_GUI.md defines how the Streamlit GUI exposes the pipeline, ingestion, and history controls to the user.

Relationship to UML:

* The “skeleton” UML shows the main classes and connections for the whole system.
* Per-module UML diagrams (for ingestion, retrieval, orchestration, AgentStack, GUI, etc.) zoom into one part at a time.
* When there is a conflict, the requirement files are the behavioral truth, and the UML diagrams are the structural truth; this architecture file is the narrative glue between them.

The rest of this document reuses the previous Architecture_2 structure but assumes that detailed behavior and data invariants live in the six requirement files listed above. Where this document mentions concrete behavior (for example, FileManifest fields, Layer-G/E, or A2/A3/A4/A5 roles), it is intended only as a summary of the requirements, not a separate source of truth.

```text
                                     ┌───────────────────────────────────┐
                                     │      🔄  Ingestion Pipeline       │
                                     │───────────────────────────────────│
 User adds / updates docs  ─────────►│ 1  DocumentLoader (paths / watch) │
                                     │ 2  Chunker  (recursive splitter)  │
                                     │ 3  Dense Embedder                 │
                                     │ 4  SPLADE Embedder                │
                                     │ 5  DenseStore.add() (Chroma DB)   │
                                     │ 6  SparseStore.add() (SPLADE DB)  │
                                     └───────────────────────────────────┘
                         ▲              ▲
                         │ builds       │ required
                         │              │
                         │              │                                   ┌──────────────────────────────┐
    Project folder       │              └──────────────┐                    │      📂 data/chroma_db/      │
    (markdown, code,     │                             │                    │  per-project vector stores   │
    PDFs, notes, etc.)   │                             │                    └──────────────────────────────┘
                         │                             │
                         ▼                             ▼

                   ┌───────────────────────────────────────────────────────┐
                   │                    FileManifest                       │
                   │  (JSON; one per project; stable IDs + metadata)      │
                   │                                                       │
                   │  - path       (relative to project root)             │
                   │  - sha256     (content hash)                          │
                   │  - mtime      (last modified time)                    │
                   │  - size       (bytes)                                 │
                   │  - status     (active / deleted / ignored)           │
                   │  - tags       (optional: user tags, e.g. “REQ”, ...) │
                   │  - last_ingested_at                                  │
                   │                                                       │
                   │  -> append-only log; published atomically             │
                   └───────────────────────────────────────────────────────┘
```

The ingestion pipeline, FileManifest, and vector store behavior are defined in detail in Requirements_Ingestion_Memory.md. The architecture view above only fixes the fact that every chunk in the vector store must be traceable back to a FileManifest entry (path + sha256) so that RAG selection is deterministic and debuggable.

---

## High-level runtime view

Conceptually, RAGstream runs as a loop over “sessions” in the GUI:

1. The user selects a project (which fixes the active `data/chroma_db/<project>/`, `data/splade_db/<project>/`, and the project FileManifest).
2. The GUI creates or reuses a controller instance with an associated SuperPrompt.
3. The user writes a free-form prompt and either steps through the pipeline or runs it automatically.
4. The controller calls deterministic functions (preprocessing, retrieval, reranking) and the currently live LLM-based agents (A2, A3) in the order defined in Requirements_RAG_Pipeline.md. A4 Condenser and Prompt Builder are the next immediate implementation targets; A5 is intentionally postponed for a later phase.
5. The GUI displays the evolving SuperPrompt; optionally, the user sends an external reply and marks it for history ingestion.

The core data carriers from the requirements:

* SuperPrompt — the central “what we are doing now” object, owned by the controller and passed through the 8 stages.
* FileManifest — the authoritative, append-only record of project documents and their versions.
* VectorStores — the dense Chroma store plus the parallel SPLADE sparse store that together support hybrid retrieval.
* Conversation log + Layer-G/E — the history representation (append-only log for G, selection-only vector store for E).

---

## RAG Pipeline and Agent Stack (summary of REQ_RAG_PIPELINE + REQ_AGENTSTACK)

At the heart of RAGstream is the 8-step pipeline described in Requirements_RAG_Pipeline.md:

```text
GUI / Controller
      │
      ▼
  A0  PreProcessing        (optional deterministic cleanup; may call a small agent)
      │
      ▼
  A2  Prompt Shaper        (LLM agent: shapes problem, sets system / task / tone, etc.)
      │
      ▼
      Retrieval            (deterministic: build query from task/purpose/context, run dense + SPLADE first-pass retrieval, fuse with weighted RRF)
      │
      ▼
      ReRanker             (deterministic: current bounded reranking stage; immediate next direction is ColBERT)
      │
      ▼
  A3  NLI Gate             (LLM agent: usefulness-only classification over reranked candidates)
      │
      ▼
  A4  Condenser            (LLM agent: condense the selected set into SuperPrompt.S_CTX_MD)
      │
      ▼
  A5  Format Enforcer      (LLM agent: postponed for a later phase; future action may be revised)
      │
      ▼
      Prompt Builder       (deterministic: final prompt assembly from SuperPrompt fields)
      │
      ▼
 (optional external LLM call)
```

The Agent Stack used by the LLM-based stages is defined in Requirements_AgentStack.md. In the current implementation-aligned architecture this means:

* AgentFactory — neutral config loader/resolver with `load_config(...)`, `get_agent(...)`, and transparent config-level caching.
* AgentPrompt — neutral prompt engine created via `from_config(...)`, with `compose(...)` and `parse(...)` as the current live public methods.
* llm_client — thin wrapper around the LLM API via `LLMClient.chat(...)`.

Current operational truth on 21.04.2026:

* A2 and A3 are the live Agent Stack consumers in the code path.
* A3 is usefulness-only; duplicate marking was intentionally removed.
* A4 Condenser is the next immediate Agent Stack consumer to be implemented.
* A5 remains in the long-range pipeline contract, but it is postponed and its future action may still change before implementation.

The architecture relies on these properties from the requirements:

* Agents are stateless; all persistent state is in SuperPrompt or in external stores (vector stores, logs, history).
* Each pipeline stage takes a SuperPrompt and returns a new SuperPrompt (or the same object mutated in-place, but following the invariants from Requirements_RAG_Pipeline.md).
* Deterministic stages never call the LLM; agent stages always go via AgentFactory + AgentPrompt + llm_client.

---

## Controller and GUI (summary of REQ_CONTROLLER + REQ_GUI)

The controller and GUI work together as the orchestrator and human-facing surface.

Controller (AppController in `controller.py`, see Requirements_Orchestration_Controller.md):

* Owns the current SuperPrompt instance and controls its lifecycle.
* Uses a light `__init__()` plus `initialize_heavy_components()` so Retrieval / ReRanker resources can warm in the background instead of blocking first paint.
* Currently exposes live stage methods for `preprocess(...)`, `run_a2_promptshaper(...)`, `run_retrieval(...)`, `run_reranker(...)`, and `run_a3(...)`, plus project-ingestion helpers.
* Keeps shared helper instances such as AgentFactory, LLMClient, A2PromptShaper, A3NLIGate, Retriever, and Reranker as controller-owned infrastructure objects.
* Owns project/data-root decisions (`doc_raw`, `chroma_db`, `splade_db`) and keeps the GUI thin.

GUI (Generation-1 Streamlit GUI split across `ui_streamlit.py`, `ui_layout.py`, and `ui_actions.py`, see Requirements_GUI.md):

* `ui_streamlit.py` handles bootstrap, session setup, controller creation, and background heavy-init startup.
* `ui_layout.py` owns page geometry and widget placement.
* `ui_actions.py` owns button callbacks and session-state mutations after controller calls.
* The current layout is two-sided: Prompt + Super-Prompt on the left; Memory Demo, pipeline buttons, Retrieval/ReRanker controls, and project controls on the right.
* The GUI currently includes `Retrieval Top-K`, `use Retrieval Splade`, and `use Reranking Colbert` controls, and it keeps downstream stage contracts stable even when the slow components are bypassed.

The architecture viewpoint here is that the GUI is thin: it never implements business logic or data invariants; it only forwards user actions to the controller and renders data it receives.

---

## Ingestion & Memory (summary of REQ_INGESTION_MEMORY)

The ingestion subsystem turns project files and (later) conversation history into vectorized knowledge usable by the RAG pipeline.

Static documents:

* Directory layout under `data/` separates raw documents (`data/doc_raw/`) from the dense store (`data/chroma_db/<project>/`) and the sparse store (`data/splade_db/<project>/`).
* Loader, chunker, dense embedder, SPLADE embedder, and vector store modules form one parallel ingestion pipeline that can be run via CLI or GUI.
* [14.04.2026] The current ingestion architecture uses one canonical chunking pass and writes the same chunk IDs and metadata into both the dense and sparse document stores.
* FileManifest is the single source of truth for “which files and versions are active in this project”.

Conversation history (future / partial):

* Every session writes an append-only text log (Layer-G) under `PATHS.logs/`, which can be replayed later.
* A separate history vector store (Layer-E) stores embeddings for selected history entries, with tags and metadata.
* Layer-E is selection-only: deletions or changes require explicit user approval and are implemented via metadata rules rather than destructive deletes.

The architecture guarantees that both document chunks and history chunks are always traceable via metadata back to their origin (file path + hash, or session log + entry id), which is essential for debugging and for controlled retrieval.

---

## ConversationMemory and Layer-G / Layer-E

From the controller’s point of view, ConversationMemory is a read-only, queryable view of past interactions.

```text
                    ┌──────────────────────────────────────────────┐
                    │           🧠 ConversationMemory              │
                    │----------------------------------------------│
                    │ G (recency window in RAM)                    │
                    │   - tail of the append-only session log      │
                    │   - fast, cheap, no embeddings               │
                    │                                              │
                    │ E (episodic / semantic index)                │
                    │   - Chroma-based store for selected entries  │
                    │   - metadata: tags, session, role, stage     │
                    │   - selection-only; no silent deletions      │
                    └──────────────────────────────────────────────┘
                                 ▲
                                 │ read-only
                                 │
                 ┌─────────────────────────────────────────────────────┐
                 │                    Controller                       │
                 │  - passes G/E slices into A2 / A3 / A4 agents       │
                 │  - never mutates ConversationMemory directly        │
                 └─────────────────────────────────────────────────────┘
```

Details of how G and E are built and updated live in Requirements_Ingestion_Memory.md. The architecture only fixes:

* The controller and agents see G/E as read-only inputs.
* History persistence and clearing remain explicit user-controlled actions in the future history layer; they are not silent background behaviors.
* Retrieval from history uses the same deterministic principles as document retrieval (filters + tags + top-k, not opaque black boxes).

---

## Eligibility Pool, Determinism, and Debugging

The architecture assumes a strong emphasis on determinism and debuggability, as reflected across the requirements:

* Eligibility Pool — a set of candidate chunks (from documents and history) that are eligible for a given stage, subject to per-file ON/OFF switches and tag rules. The Eligibility Pool concept appears in Requirements_RAG_Pipeline.md and Requirements_Orchestration_Controller.md; architecture only fixes that all RAG-related decisions run over an explicit, inspectable candidate set.
* No silent deletions — vector stores and history stores do not silently lose data; removals or deactivations are expressed via FileManifest status fields, tags, or explicit “ignore” rules.
* Explainability — every stage decision (especially Retrieval ranking, ReRanker fusion, and A3 usefulness labeling / post-selection) is traceable via logs and, where appropriate, via structured fields in SuperPrompt (e.g. `views_by_stage`, `history_of_stages`).

These principles are enforced by the controller and Agent Stack orchestration but belong to the requirements as the ultimate behavioral contract.

---

## Debug Logger and Transparency

The debug logger is a developer-oriented facility:

* Each GUI session writes under `PATHS.logs/` with a timestamped stem.
* `debug_trace_*.log` records actions and explanations in a compact, human-readable form.
* `debug_vars_*.log` records variable dumps when `vars_enabled=True`.
* Logging is flush+fsync-based so that diagnostic information survives crashes.

Transparency for the user is handled in the GUI:

* Panels show which files, chunks, and history entries were selected or dropped at each stage.
* A summary view explains in plain language why certain sources were kept or excluded.

The architectural point is that debug logging and user transparency are separate: debug logs are for you as the developer; transparency panels are for runtime introspection.

---

## Persistence & Modularity

Dense document vectors persist as Chroma on-disk collections under `data/chroma_db/`. Sparse document representations persist separately under `data/splade_db/`. This allows you to:

* keep dense and sparse retrieval physically separate but logically aligned,
* swap embedding or sparse models with a controlled migration path,
* back up and restore project knowledge,
* and run multiple projects side by side without collisions.

FileManifest and logs live on the filesystem in JSON / text files; their formats are simple by design so that you can inspect and edit them manually when needed.

Modules are kept small and focused, following the mapping in Requirements_Knowledge_Map.md (MOD_* names). Architecture.md does not duplicate that mapping; it only assumes that:

* ingestion/, retrieval/, orchestration/, tooling/, and app/ each own their part of the behavior;
* cross-cutting concerns (SuperPrompt, logging, paths) sit in utils/ or dedicated modules referenced from the requirements.

---

## Non-Functional Targets (mirroring the requirements)

The non-functional targets (performance, cost, robustness, extensibility) are specified more precisely in the requirements and backlog, but at architecture level the main points are:

* Local-first, research-grade: everything can run on your local machine without external services beyond the LLM API and embeddings.
* Deterministic where possible: ingestion, retrieval, reranking, and selection logic are deterministic functions over FileManifest and the aligned dense/sparse stores.
* Agentic but controlled: LLM-based stages are stateless, small, and driven by explicit JSON configs rather than ad-hoc prompts.
* Extensible: new agents or stages can be added without breaking existing ones, as long as they respect the SuperPrompt and Agent Stack contracts.
* [21.04.2026] Late-stage implementation priority is now explicit: after the current Retrieval / ReRanker / A3 base, the next immediate implementation targets are A4 Condenser and Prompt Builder, while A5 remains postponed.

---

# Sync Report (21.04.2026 update)

**Precisely applied changes (minimal edits only):**

* Added a current sync date at the top and a small maintenance note for future inline date-stamps.
* Updated the architecture narrative from dense-only document persistence to parallel dense + SPLADE document persistence.
* Updated the high-level runtime wording so project selection now fixes both `chroma_db/<project>` and `splade_db/<project>`.
* Updated Retrieval wording from generic RRF to weighted RRF.
* Corrected the ReRanker wording so it no longer claims that ColBERT is already the active implementation; ColBERT remains the immediate next direction.
* Updated persistence/modularity wording so dense Chroma and sparse SPLADE stores are both part of the architecture.