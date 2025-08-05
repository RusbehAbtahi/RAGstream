@startuml RAG_TinyLlama_Full

'──────────────────────────────────────────────────────────────
'  GLOBAL SETTINGS
'──────────────────────────────────────────────────────────────
skinparam linetype ortho
skinparam classAttributeIconSize 0
skinparam packageStyle rectangle
hide empty members

'──────────────────────────────────────────────────────────────
'  1) INGESTION & MEMORY LAYER
'──────────────────────────────────────────────────────────────
package "Ingestion / Memory" {

    class DocumentLoader {
        + load_docs(paths: List[str]) : List[str]
        + watch_dir(path: str)        : None
        - _cache : Dict[str,str]
    }

    class Chunker {
        + chunk(text: str) : List[str]
        - window_size : int
        - overlap     : int
    }

    class Embedder {
        + embed(texts: List[str]) : ndarray
        - model_name : str
    }

    class VectorStore {
        + add(ids: List[str], vecs: ndarray) : None
        + query(vec: ndarray, k: int) : List[DocScore]
        + persist() : None
        - _client : chromadb.Client
    }

    DocumentLoader --> Chunker : sends\nraw text
    Chunker --> Embedder : chunks
    Embedder --> VectorStore : vecs + ids
}

'──────────────────────────────────────────────────────────────
' 2) RETRIEVAL & RERANKING ENGINE
'──────────────────────────────────────────────────────────────
package "Retrieval & Ranking" {

    class Reranker {
        + rerank(q:str, chunks:List[str]) : List[DocScore]
        - model : CrossEncoder
    }

    class AttentionWeights {
        + get(id:str) : float
        + set(id:str, w:float) : None
        - _w : Dict[str,float]
    }

    class Retriever {
        + retrieve(q:str) : List[str]
        - _vs : VectorStore
        - _emb : Embedder
        - _reranker : Reranker
        - _aw : AttentionWeights
    }

    Retriever --> VectorStore
    Retriever --> Embedder
    Retriever --> Reranker
    Retriever --> AttentionWeights : applies\nweights
}

'──────────────────────────────────────────────────────────────
' 3) TOOLING MODULE
'──────────────────────────────────────────────────────────────
package "Local Tooling" {

    abstract class BaseTool {
        + name : str
        + __call__(input:str) : str
    }

    class MathTool {
        + name = "math"
        + __call__(expr:str) : str
    }

    class PyTool {
        + name = "python"
        + __call__(code:str) : str
    }

    BaseTool <|-- MathTool
    BaseTool <|-- PyTool

    class ToolRegistry {
        - _tools : Dict[str,BaseTool]
        + register(t:BaseTool) : None
        + get(name:str) : BaseTool
    }

    class ToolDispatcher {
        - _reg : ToolRegistry
        + maybe_run(prompt:str) : Optional[str]
        - _detect(prompt:str) : Tuple[str,str]
    }

    ToolDispatcher --> ToolRegistry
    ToolRegistry --> BaseTool
}

'──────────────────────────────────────────────────────────────
' 4) PROMPT ORCHESTRATION
'──────────────────────────────────────────────────────────────
package "Prompt Orchestration" {

    class PromptBuilder {
        - template : str
        + build(q:str, ctx:List[str], tool:str) : str
    }

    class LLMClient {
        - model : str
        - api_key : str
        + generate(prompt:str) : str
    }
}

'──────────────────────────────────────────────────────────────
' 5) APPLICATION CONTROLLER & UI
'──────────────────────────────────────────────────────────────
package "Application Layer" {

    class Controller {
        - _retr : Retriever
        - _pb   : PromptBuilder
        - _llm  : LLMClient
        - _td   : ToolDispatcher
        - _aw   : AttentionWeights
        + answer(q:str) : str
    }

    class StreamlitUI {
        - _ctl : Controller
        + render() : None
    }

    StreamlitUI --> Controller : user actions
}

'──────────────────────────────────────────────────────────────
' 6) CROSS-PACKAGE DEPENDENCIES
'──────────────────────────────────────────────────────────────
Controller --> Retriever
Controller --> ToolDispatcher
Controller --> PromptBuilder
Controller --> LLMClient
Controller --> AttentionWeights

PromptBuilder ..> ToolDispatcher : receives\nTOOL_OUTPUT
PromptBuilder ..> Retriever      : receives\ncontext

@enduml
