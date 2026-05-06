# ragstream/app/ui_streamlit.py
# -*- coding: utf-8 -*-
"""
Run on a free port, e.g.:
  /home/rusbeh_ab/venvs/ragstream/bin/python -m streamlit run /home/rusbeh_ab/project/RAGstream/ragstream/app/ui_streamlit.py --server.port 8503
"""

from __future__ import annotations

import json
import threading

from pathlib import Path
from typing import Any

import streamlit as st

from ragstream.app.controller import AppController
from ragstream.app.ui_layout import inject_base_css, render_page
from ragstream.app.ui_files import render_files_tab
from ragstream.app.ui_metrics import render_metrics_tab
from ragstream.app.ui_settings import render_settings_tab
from ragstream.ingestion.embedder import Embedder
from ragstream.memory.memory_chunker import MemoryChunker
from ragstream.memory.memory_ingestion_manager import MemoryIngestionManager
from ragstream.memory.memory_manager import MemoryManager
from ragstream.memory.memory_vector_store import MemoryVectorStore
from ragstream.orchestration.super_prompt import SuperPrompt
from ragstream.textforge.RagLog import LogALL as logger
from ragstream.textforge.RagLog import LogDeveloper as logger_dev


def _load_runtime_config(project_root: Path) -> dict[str, Any]:
    """
    Read ragstream/config/runtime_config.json during Streamlit startup.

    This config is used for Memory Retrieval limits and later runtime defaults.
    """
    config_path = project_root / "ragstream" / "config" / "runtime_config.json"

    if not config_path.exists():
        logger(f"runtime_config.json not found: {config_path}", "WARN", "PUBLIC")
        return {}

    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("runtime_config.json root must be a JSON object.")

        logger("runtime_config.json loaded in Streamlit session.", "INFO", "INTERNAL")

        logger_dev(
            "runtime_config.json loaded in Streamlit session\n"
            + json.dumps(data, ensure_ascii=False, indent=2, default=str),
            "DEBUG",
            "CONFIDENTIAL",
        )

        return data

    except Exception as e:
        logger(f"Failed to load runtime_config.json: {e}", "ERROR", "PUBLIC")
        return {}


def init_session_state() -> None:
    """
    Create one controller + one SuperPrompt set per user session.

    Startup also initializes:
    - MemoryManager
    - MemoryVectorStore
    - MemoryIngestionManager
    - MemoryRetriever wiring through AppController.configure_memory_retrieval(...)
    """
    project_root = Path(__file__).resolve().parents[2]

    if "runtime_config" not in st.session_state:
        st.session_state.runtime_config = _load_runtime_config(project_root)

    if "controller" not in st.session_state:
        ctrl = AppController()
        st.session_state.controller = ctrl

    if "textforge_gui_log" not in st.session_state:
        st.session_state["textforge_gui_log"] = ""

    if "memory_manager" not in st.session_state:
        memory_root = project_root / "data" / "memory"
        sqlite_path = memory_root / "memory_index.sqlite3"

        st.session_state.memory_manager = MemoryManager(
            memory_root=memory_root,
            sqlite_path=sqlite_path,
            title="",
        )

    if "memory_vector_store" not in st.session_state:
        memory_root = project_root / "data" / "memory"
        memory_vector_root = memory_root / "vector_db"

        memory_embedder = Embedder(model="text-embedding-3-large")

        st.session_state.memory_vector_store = MemoryVectorStore(
            persist_dir=str(memory_vector_root),
            collection_name="memory_vectors",
            embedder=memory_embedder,
        )

    if "memory_chunker" not in st.session_state:
        st.session_state.memory_chunker = MemoryChunker()

    if "memory_ingestion_manager" not in st.session_state:
        st.session_state.memory_ingestion_manager = MemoryIngestionManager(
            memory_manager=st.session_state.memory_manager,
            memory_chunker=st.session_state.memory_chunker,
            memory_vector_store=st.session_state.memory_vector_store,
        )

        logger(
            "Memory ingestion layer ready: data/memory/vector_db/ | collection=memory_vectors",
            "INFO",
            "PUBLIC",
        )

    if "memory_retrieval_configured" not in st.session_state:
        st.session_state["memory_retrieval_configured"] = False

    if not st.session_state["memory_retrieval_configured"]:
        ctrl: AppController = st.session_state.controller
        ctrl.configure_memory_retrieval(
            memory_manager=st.session_state.memory_manager,
            memory_vector_store=st.session_state.memory_vector_store,
            runtime_config=st.session_state.runtime_config,
        )
        st.session_state["memory_retrieval_configured"] = True

    if "heavy_init_started" not in st.session_state:
        st.session_state["heavy_init_started"] = False

    if not st.session_state["heavy_init_started"]:
        ctrl = st.session_state.controller

        t = threading.Thread(
            target=ctrl.initialize_heavy_components,
            daemon=True,
        )
        t.start()

        st.session_state["heavy_init_started"] = True

    if "sp" not in st.session_state:
        st.session_state.sp = SuperPrompt()
    if "sp_pre" not in st.session_state:
        st.session_state.sp_pre = SuperPrompt()
    if "sp_a2" not in st.session_state:
        st.session_state.sp_a2 = SuperPrompt()
    if "sp_rtv" not in st.session_state:
        st.session_state.sp_rtv = SuperPrompt()
    if "sp_rrk" not in st.session_state:
        st.session_state.sp_rrk = SuperPrompt()
    if "sp_a3" not in st.session_state:
        st.session_state.sp_a3 = SuperPrompt()
    if "sp_a4" not in st.session_state:
        st.session_state.sp_a4 = SuperPrompt()

    if "super_prompt_text" not in st.session_state:
        st.session_state["super_prompt_text"] = ""

    if "ingestion_status" not in st.session_state:
        st.session_state["ingestion_status"] = None

    if "new_project_name" not in st.session_state:
        st.session_state["new_project_name"] = ""

    if "pending_active_project" not in st.session_state:
        st.session_state["pending_active_project"] = None

    if "retrieval_top_k" not in st.session_state:
        st.session_state["retrieval_top_k"] = 30

    if "use_retrieval_splade" not in st.session_state:
        st.session_state["use_retrieval_splade"] = False

    if "use_reranking_colbert" not in st.session_state:
        st.session_state["use_reranking_colbert"] = False

    if "manual_memory_feed_text" not in st.session_state:
        st.session_state["manual_memory_feed_text"] = ""

def render_tabs() -> None:
    """
    Top-level Streamlit tabs.

    MAIN keeps the existing RAGstream page.
    Other tabs are separated into their own UI modules so ui_layout.py
    does not become overloaded.
    """
    tab_main, tab_files, tab_hard_rules, tab_metrics, tab_settings = st.tabs(
        [
            "MAIN",
            "FILES",
            "HARD RULES",
            "METRICS",
            "GENERAL SETTINGS",
        ]
    )

    with tab_main:
        render_page()

    with tab_files:
        render_files_tab()

    with tab_hard_rules:
        st.markdown("## Hard Rules")
        st.info("Hard Rules tab placeholder.")

    with tab_metrics:
        render_metrics_tab()

    with tab_settings:
        render_settings_tab()


def main() -> None:
    st.set_page_config(page_title="RAGstream", layout="wide")

    inject_base_css()

    st.title("RAGstream")

    init_session_state()

    render_tabs()


if __name__ == "__main__":
    main()