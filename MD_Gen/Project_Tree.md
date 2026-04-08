# Local Project Tree

```
/home/rusbeh_ab/project/RAGstream
├── Run.txt
├── Test.py
├── __init__.py
├── diag_chroma_test.py
├── diag_chroma_wo_ort.txt
├── ragstream_all_py.txt
├── requirements-dev.txt
├── requirements.txt
├── requirements_large_20251205.txt
├── test_openai_hello.py
├── ragstream
│   ├── __init__.py
│   ├── __pycache__
│   ├── agents
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   ├── a1_dci.py
│   │   ├── a2_promptshaper.py
│   │   ├── a3_nli_gate.py
│   │   └── a4_condenser.py
│   ├── app
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   ├── agents.py
│   │   ├── controller.py
│   │   ├── controller_legacy.py
│   │   ├── ui_streamlit.py
│   │   └── ui_streamlit_demo.py
│   ├── config
│   │   ├── __init__.py
│   │   ├── prompt_schema.json
│   │   └── settings.py
│   ├── ingestion
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   ├── chroma_vector_store_base.py
│   │   ├── chunker.py
│   │   ├── embedder.py
│   │   ├── file_manifest.py
│   │   ├── ingestion_manager.py
│   │   ├── loader.py
│   │   └── vector_store_chroma.py
│   ├── memory
│   │   ├── __init__.py
│   │   └── conversation_memory.py
│   ├── orchestration
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   ├── agent_factory.py
│   │   ├── agent_prompt.py
│   │   ├── agent_prompt_helpers
│   │   │   ├── __init__.py
│   │   │   ├── __pycache__
│   │   │   ├── compose_texts.py
│   │   │   ├── config_loader.py
│   │   │   ├── field_normalizer.py
│   │   │   ├── json_parser.py
│   │   │   └── schema_map.py
│   │   ├── llm_client.py
│   │   ├── prompt_builder.py
│   │   └── super_prompt.py
│   ├── preprocessing
│   │   ├── __pycache__
│   │   ├── name_matcher.py
│   │   ├── preprocessing.py
│   │   └── prompt_schema.py
│   ├── retrieval
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   ├── attention.py
│   │   ├── chunk.py
│   │   ├── doc_score.py
│   │   ├── reranker.py
│   │   ├── retriever.py
│   │   └── retriever_old.py
│   └── utils
│       ├── __init__.py
│       ├── __pycache__
│       ├── logging.py
│       └── paths.py
└── data
    ├── A2_SLM_Training
    │   ├── A2_dataset_list.json
    │   ├── Create_DataSet.py
    │   ├── conversations.json
    │   └── file_manifest.json
    ├── agents
    │   └── a2_promptshaper
    │       ├── 001.json
    │       └── 002.json
    ├── chroma_db
    │   ├── project1
    │   │   ├── 2d71b43d-3226-411e-8ff2-2cede3dcb9a0
    │   └── project2
    │       ├── 526ca8ff-c00e-4657-b10c-94f6a376684e
    │       └── file_manifest.json
    ├── doc_raw
    │   └── project2
    ├── np_store
    │   └── project1
    └── project1
```
