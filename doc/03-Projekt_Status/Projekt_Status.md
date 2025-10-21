# RAGstream Project STATUS — IST (2025-10-21)

This report consolidates the current codebase against the latest Requirements, Architecture, and UML. Sources read: Requirements.md, Architecture_2.md, UML_Simple.txt, Project_Tree.md, and the full code index in ragstream_python.md.     

---

## 1) High-level picture

Implemented now

* Document ingestion pipeline is complete and Chroma-backed: loader → chunker → embedder (OpenAI) → vector store (Chroma) → manifest diff/publish, orchestrated by IngestionManager. 
* Deterministic FileManifest with atomic publish and ingestion diffing is in place. 
* Core config and paths utilities exist; minimal Settings cache is implemented. 

Partially implemented / placeholders

* Retrieval path compiles but is out of date: Retriever still targets the old NumPy store (VectorStoreNP), not Chroma; Reranker is a stub. 
* AppController and A1..A4 agents exist but are skeletal; there is also a duplicate “agents.py” alongside per-agent modules. 
* PromptBuilder and LLMClient are stubs. 
* Streamlit UI is a minimal shell (no switches, eligibility pool, Exact File Lock UI, transparency panels, or history controls yet). 

Not implemented yet (per Requirements/Architecture)

* ConversationMemory two-layer model (G/E, selection-only embeddings, persistence JSONL + Chroma history store) is only a placeholder.   
* Debug Logger (feature-2) with trace/vars files and rotation is not present; only SimpleLogger exists.  
* A0 FileScopeSelector and A5 Schema/Format Enforcer from the UML/Requirements are not present as modules.  

---

## 2) Detailed status by layer (compared to Requirements/UML/Architecture)

Config & Utils

* utils/paths.py defines project roots and paths, including chroma_db and legacy vector_pkls; comments mark chroma_db as “planned” while ingestion already uses Chroma. This explains the mixed state with retrieval still pointing to vector_pkls. 
* config/settings.py provides a cached env accessor. 
* utils/logging.py implements SimpleLogger only; UML/Requirements also mention DebugLogger with logWriteText/logWriteVar and rotation, which is not implemented.   

Ingestion / Knowledge Store

* Implemented modules: loader.py (UTF-8/latin-1 fallback), chunker.py (deterministic windows), embedder.py (OpenAI text-embedding-3-large), chroma_vector_store_base.py (PersistentClient, add/query/snapshot/delete_where), vector_store_chroma.py (helpers, make_chunk_id, delete_file_version), file_manifest.py (compute_sha256/load/diff/publish_atomic), ingestion_manager.py (scan→diff→chunk→embed→upsert→cleanup→publish, returns stats including embedded_bytes). This matches the current Architecture and Requirements (ING-01..06), including stable chunk IDs and per-project Chroma persistence.   
* Chroma snapshot support exists via snapshot() in the base store. 
* Alignment note: Architecture/Requirements explicitly require Chroma for vectors; code conforms for ingestion.  

Conversation History (two-layer G/E)

* conversation_memory.py is a thin placeholder (empty getters). No JSONL persistence, no selection-only history embeddings, no Eligibility Pool alignment or external-reply import. These are specified in Requirements CH-01..CH-12 and described in Architecture, but not yet implemented in code.   
* UML and Architecture reference HistoryStoreChroma and HistoryEmbeddingWorker; these do not exist yet.  

Retrieval & Ranking

* retriever.py still imports VectorStoreNP (NumPy) and PATHS["vector_pkls"]; it computes cosine using NP internals and returns DocScore. This contradicts the migration to Chroma specified in Requirements/Architecture; vector_store_np.py does not exist in the current tree, so Retriever is not aligned and would not run as-is without that legacy module.  
* Reranker is a no-op; cross-encoder rerank from Requirements (RET-02) is not yet wired.  
* DocScore dataclass is present. 
* UML expects Retriever → Reranker, which structurally exists, but the storage backend is not updated to Chroma. 

Agents & Application Layer

* AppController wires A1..A4, Retriever, Reranker, PromptBuilder, LLMClient, ConversationMemory, and supports “exact_lock” short-circuit. Flow mirrors UML/Architecture (A2 propose → A1 ❖FILES → retrieval unless locked → A4 condense → A2 audit and optional single re-run → PromptBuilder → LLMClient). However, it depends on the outdated Retriever. 
* Agents exist in two places: a combined app/agents.py (A1..A4) and per-agent modules a1_dci.py, a2_prompt_shaper.py, a3_nli_gate.py, a4_condenser.py. Both sets are stubs returning placeholders (e.g., "❖ FILES\n", trivial headers, identity filters, empty S_ctx sections). This duplicates code and needs consolidation; Requirements and UML also define A0 (FileScopeSelector) and A5 (Schema/Format Enforcer), which are absent.   
* Streamlit UI is a shell with title and descriptive text; Requirements UI-01..UI-12 features (eligibility checkboxes, Exact File Lock toggle, super-prompt preview, transparency, cost ceiling, external reply import, history persistence controls) are not implemented yet.  

Prompt Orchestration

* PromptBuilder.build returns "PROMPT"; LLMClient.complete returns "ANSWER"; estimate_cost is a stub. Architecture/Requirements define authority order and cost ceilings, but these are not implemented beyond placeholders.   

Debug / Logging

* UML/Architecture include DebugLogger (trace/vars, rotation) for developer diagnostics; not implemented. Only SimpleLogger is present and explicitly “ephemeral console messages only.”  

Directory/Module tree alignment

* The live tree matches the code index and shows ingestion, retrieval, orchestration, app, memory, utils. No vector_store_np.py is present (confirming the retrieval mismatch). 

---

## 3) Summary tables (what exists now)

Implemented (working scope expected)

* Ingestion pipeline end-to-end with Chroma persistence, including deterministic IDs and manifest management; snapshotting supported. 
* Settings/Paths utilities; basic SimpleLogger. 

Implemented (stubs/placeholders)

* AppController orchestration skeleton; A1..A4 agent shells; UI shell; PromptBuilder/LLMClient stubs; Reranker stub; ConversationMemory placeholder. 

Specified but not yet implemented

* Retrieval on Chroma (current code still references VectorStoreNP).  
* A0 FileScopeSelector and A5 Schema/Format Enforcer.  
* ConversationMemory persistence (JSONL), selection-only Layer-E embeddings store (HistoryStoreChroma), HistoryEmbeddingWorker, Eligibility alignment, external reply import.  
* Debug Logger with trace/vars files and rotation. 

---

## 4) Mismatches and current blockers

* Retrieval backend mismatch: Retriever imports a non-existent NumPy store (VectorStoreNP) and PATHS["vector_pkls"], while ingestion writes to Chroma; this must be ported before end-to-end queries can work against the new vectors.  
* Agents duplication: app/agents.py vs per-agent modules; choose one pattern and delete the other to avoid drift. 
* Missing A0/A5 modules required by UML/Requirements.  
* ConversationMemory designed in Requirements/Architecture is not implemented; current controller references it but receives empty data.  
* UI lacks the Eligibility Pool, Exact File Lock toggle, transparency, history controls, cost ceiling display, and external-reply import specified in UI-01..UI-12. 

---

## 5) One-line IST verdict

RAGstream’s ingestion system is production-ready on Chroma with deterministic manifesting; orchestration, retrieval, history, UI, and debug logging are scaffolded but require implementation and a retrieval port to Chroma to reach the Architecture/Requirements baseline.    
