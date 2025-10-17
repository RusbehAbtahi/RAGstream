# Local Project Tree

```
/home/rusbeh_ab/project/RAGstream
├── __init__.py
├── diag_chroma_test.py
├── diag_chroma_wo_ort.txt
├── requirements-dev.txt
├── requirements.txt
└── ragstream
    ├── __init__.py
    ├── __pycache__
    ├── app
    │   ├── __init__.py
    │   ├── agents
    │   │   ├── __init__.py
    │   │   ├── a1_dci.py
    │   │   ├── a2_prompt_shaper.py
    │   │   ├── a3_nli_gate.py
    │   │   └── a4_condenser.py
    │   ├── agents.py
    │   ├── controller.py
    │   └── ui_streamlit.py
    ├── config
    │   ├── __init__.py
    │   └── settings.py
    ├── ingestion
    │   ├── __init__.py
    │   ├── chroma_vector_store_base.py
    │   ├── chunker.py
    │   ├── embedder.py
    │   ├── file_manifest.py
    │   ├── ingestion_manager.py
    │   ├── loader.py
    │   └── vector_store_chroma.py
    ├── memory
    │   ├── __init__.py
    │   └── conversation_memory.py
    ├── orchestration
    │   ├── __init__.py
    │   ├── llm_client.py
    │   └── prompt_builder.py
    ├── retrieval
    │   ├── __init__.py
    │   ├── attention.py
    │   ├── doc_score.py
    │   ├── reranker.py
    │   └── retriever.py
    └── utils
        ├── __init__.py
        ├── logging.py
        └── paths.py
```
