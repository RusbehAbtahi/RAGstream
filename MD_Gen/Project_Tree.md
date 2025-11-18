# Local Project Tree

```
/home/rusbeh_ab/project/RAGstream
├── Run.txt
├── Test.py
├── __init__.py
├── diag_chroma_test.py
├── diag_chroma_wo_ort.txt
├── requirements-dev.txt
├── requirements.txt
├── ragstream
│   ├── __init__.py
│   ├── __pycache__
│   ├── app
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   ├── agents
│   │   │   ├── __init__.py
│   │   │   ├── a1_dci.py
│   │   │   ├── a2_prompt_shaper.py
│   │   │   ├── a3_nli_gate.py
│   │   │   └── a4_condenser.py
│   │   ├── agents.py
│   │   ├── controller.py
│   │   ├── controller_legacy.py
│   │   ├── ui_sections
│   │   ├── ui_streamlit.py
│   │   └── ui_streamlit_2.py
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
│   │   └── retriever.py
│   └── utils
│       ├── __init__.py
│       ├── logging.py
│       └── paths.py
├── training/slm_a2/data
│   ├── processed
│   │   ├── finetuned_model_id.txt
│   ├── processed_win384
│   └── raw
│       ├── A2_dataset_list.json
├── training/slm_a2/models_local
│   ├── a2_lora_20251031_1430
│   └── a2_lora_20251031_1807
│       ├── adapter_config.json
│       ├── added_tokens.json
│       ├── merges.txt
│       ├── special_tokens_map.json
│       ├── tokenizer.json
│       ├── tokenizer_config.json
│       └── vocab.json
└── training/slm_a2/scripts
    ├── a2_convert_for_openai.py
    ├── a2_finetune.py
    ├── clean_and_split_dataset.py
    ├── clean_and_window_384.py
    ├── hello_qwen.py
    ├── infer_base.py
    ├── test_a2_ft.py
    └── train_lora.py
```
