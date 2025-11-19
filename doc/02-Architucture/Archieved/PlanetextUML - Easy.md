@startuml RAGstream2_Full

'──────────────────────────────────────────────────────────────
'  GLOBAL SETTINGS
'──────────────────────────────────────────────────────────────
skinparam linetype ortho
skinparam classAttributeIconSize 0
skinparam packageStyle rectangle
hide empty members

'──────────────────────────────────────────────────────────────
'  0) CONFIG & UTILS
'──────────────────────────────────────────────────────────────
package "Config & Utils" {
    class Settings {
        + get(key:str, default:Any=None) : Any
        - _CACHE : Dict[str,Any]
    }

    class Paths {
        + PATHS : TypedDict(root:Path,\n\
                            data:Path,\n\
                            raw_docs:Path,\n\
                            chroma_db:Path,\n\
                            vector_pkls:Path,\n\
                            logs:Path)
        + ROOT  : Path
    }

    class SimpleLogger {
        + log(msg:str)   : None
        + error(msg:str) : None
        - _logger : logging.Logger
    }
}

'──────────────────────────────────────────────────────────────
'  1) INGESTION & MEMORY LAYER
'──────────────────────────────────────────────────────────────
package "Ingestion / Memory" {

    class DocumentLoader {
        + load_documents(subfolder:str) : List[Tuple[str,str]]
        - root : Path
    }

    class Chunker {
        + split(file_path:str, text:str,\n\
                chunk_size:int=500,\n\
                overlap:int=100) : List[Tuple[str,str]]
    }

    class Embedder {
        + embed(texts:List[str]) : List[List[float]]
        - model : str
        - client : OpenAI
    }

    interface IVectorStore {
        + add(ids:List[str], vectors:List[List[float]],\n\
              meta:List[Dict]) : None
        + query(vector:List[float], k:int=10) : List[str]
        + snapshot(timestamp:str) : None
    }

    class VectorStoreNP implements IVectorStore {
        + add(ids,vectors,meta) : None
        + query(vector,k=10) : List[str]
        + snapshot(ts:str) : None
        - persist_path : Path
        - db_file : Path
        - _ids : List[str]
        - _meta : List[Dict]
        - _emb : ndarray
        - _id2idx : Dict[str,int]
    }

    class VectorStoreChroma implements IVectorStore {
        + add(ids,vectors,meta) : None
        + query(vector,k=10) : List[str]
        + snapshot(ts:str) : None
        - client : chromadb.\n\ PersistentClient
        - collection : chromadb.\n\ Collection
    }

    class VectorStoreRouter {
        + VectorStore : IVectorStore
        - select_by_env() : IVectorStore
    }

    DocumentLoader --> Chunker : raw text
    Chunker --> Embedder : chunks
    Embedder --> IVectorStore : ids + vectors
    Paths ..> DocumentLoader : uses PATHS.raw_docs
    Paths ..> VectorStoreNP  : uses PATHS.vector_pkls
    Paths ..> VectorStoreChroma : uses PATHS.chroma_db
}

'──────────────────────────────────────────────────────────────
'  2) RETRIEVAL & RANKING
'──────────────────────────────────────────────────────────────
package "Retrieval & Ranking" {

    class DocScore {
        + id : str
        + score : float
    }

    class Reranker {
        + rerank(ids:List[str], query:str) : List[str]
    }

    class AttentionWeights <<legacy>> {
        + weight(scores:Dict[str,float]) : Dict[str,float]
    }

    class Retriever {
        + retrieve(query:str, k:int=10) : List[DocScore]
        - _vs : IVectorStore
        - _emb : Embedder
        - _reranker : Reranker
    }

    Retriever --> IVectorStore
    Retriever --> Embedder
    Retriever --> Reranker
    Retriever ..> DocScore
}

'──────────────────────────────────────────────────────────────
'  3) AGENTS (A1–A4)
'──────────────────────────────────────────────────────────────
package "Agents (app/agents)" {

    class A1_DCI {
        + build_files_block(named_files:List[str],\n\
                            lock:bool) : str
        - pack_threshold_tokens : int
        - file_manifest : Optional[Any]
    }

    class A2_PromptShaper {
        + propose(question:str) :\n\
         Dict[str,str]  ' {intent, domain, headers}
    }

    class A3_NLIGate {
        + filter(candidates:List[str],\n\
                 question:str) : List[str]
        - theta : float
    }

    class A4_Condenser {
        + condense(kept:List[str]\n\
                   ) : List[str] \n\
          ' S_ctx lines: Facts/Constraints/Open Issues
    }
}

'──────────────────────────────────────────────────────────────
'  4) LOCAL TOOLING
'──────────────────────────────────────────────────────────────
package "Local Tooling" {

    abstract class BaseTool {
        + name : str
        + __call__(instruction:str) : str
    }

    class MathTool {
        + name = "math"
        + __call__(expr:str) : str
    }

    class PyTool {
        + name = "py"
        + __call__(code:str) : str
    }

    BaseTool <|-- MathTool
    BaseTool <|-- PyTool

    class ToolRegistry {
        + discover() : None
        + get(name:str) : BaseTool
        - _registry : Dict[str,BaseTool]
    }

    class ToolDispatcher {
        + maybe_dispatch(prompt:str) :\n\
         Tuple[str,str]  ' (tool_output, stripped_prompt)
    }

    ToolDispatcher --> ToolRegistry
    ToolRegistry --> BaseTool
}

'──────────────────────────────────────────────────────────────
'  5) PROMPT ORCHESTRATION
'──────────────────────────────────────────────────────────────
package "Prompt Orchestration" {

    class PromptBuilder {
        + build(question:str,\n\
                files_block:str,\n\
                s_ctx:List[str],\n\
                shape:Dict=None,\n\
                tool:str=None) : str
        - template : str
    }

    class LLMClient {
        + complete(prompt:str) : str
        + estimate_cost(tokens:int) : float
        - model : str
    }
}

'──────────────────────────────────────────────────────────────
'  6) APPLICATION LAYER (Controller & UI)
'──────────────────────────────────────────────────────────────
package "Application Layer" {

    class AppController {
        + handle(user_prompt:str,\n\
                 named_files:List[str],\n\
                 exact_lock:bool) : str
        - shaper : A2_PromptShaper
        - dci : A1_DCI
        - gate : A3_NLIGate
        - condenser : A4_Condenser
        - retriever : Retriever
        - reranker : Reranker
        - prompt_builder : PromptBuilder
        - llm : LLMClient
        - tool_dispatcher : ToolDispatcher
        - eligibility_pool : Set[str]
        - exact_lock : bool
    }

    class StreamlitUI {
        + render() : None
        - ctrl : AppController
    }

    StreamlitUI --> AppController : user actions
}

'──────────────────────────────────────────────────────────────
'  7) CROSS-PACKAGE DEPENDENCIES & FLOW
'──────────────────────────────────────────────────────────────
' Controller Orchestration
AppController --> A2_PromptShaper : propose()
AppController --> A1_DCI          : build_files_block()
AppController --> Retriever       : retrieve() [if not exact_lock]
AppController --> Reranker        : rerank()
AppController --> A3_NLIGate      : filter()
AppController --> A4_Condenser    : condense() -> S_ctx
AppController --> PromptBuilder   : build()
AppController --> LLMClient       : complete()
AppController --> ToolDispatcher  : maybe_dispatch()

' Ingestion path
DocumentLoader --> Chunker
Chunker --> Embedder
Embedder --> IVectorStore

' PromptBuilder inputs
PromptBuilder ..> A1_DCI        : receives ❖ FILES
PromptBuilder ..> A4_Condenser  : receives S_ctx

' Misc
class AllClasses
Settings ..> LLMClient : API keys/config

Settings ..> Embedder  : API keys/config
SimpleLogger ..> AllClasses : logging

note right of AppController
  Authority order in PromptBuilder:
  [Hard Rules] → [Project Memory] → [❖ FILES]
  → [S_ctx] → [Task/Mode]
end note

note bottom of VectorStoreNP
  Current default on Windows:
  NumPy-backed exact cosine
  with .pkl snapshots.
end note

note bottom of VectorStoreChroma
  Planned on-disk Chroma collection
  (enabled when environment allows).
end note

@enduml
