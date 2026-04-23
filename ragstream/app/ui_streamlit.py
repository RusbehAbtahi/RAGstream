# ragstream/app/ui_streamlit.py
# -*- coding: utf-8 -*-
"""
Run on a free port, e.g.:
  /home/rusbeh_ab/venvs/ragstream/bin/python -m streamlit run /home/rusbeh_ab/project/RAGstream/ragstream/app/ui_streamlit.py --server.port 8503
"""

from __future__ import annotations

import threading

import streamlit as st

from ragstream.app.controller import AppController
from ragstream.app.ui_layout import inject_base_css, render_page
from ragstream.orchestration.super_prompt import SuperPrompt


def init_session_state() -> None:
    """Create one controller + one SuperPrompt set per user session."""
    if "controller" not in st.session_state:
        ctrl = AppController()
        st.session_state.controller = ctrl

    if "heavy_init_started" not in st.session_state:
        st.session_state["heavy_init_started"] = False

    if not st.session_state["heavy_init_started"]:
        ctrl: AppController = st.session_state.controller

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
        # Temporary project switch key
        st.session_state["pending_active_project"] = None

    if "retrieval_top_k" not in st.session_state:
        st.session_state["retrieval_top_k"] = 30

    if "use_retrieval_splade" not in st.session_state:
            st.session_state["use_retrieval_splade"] = False

    if "use_reranking_colbert" not in st.session_state:
            st.session_state["use_reranking_colbert"] = False

    if "a2_memory_demo_entries" not in st.session_state:
        st.session_state["a2_memory_demo_entries"] = []

    if "a2_memory_demo_counter" not in st.session_state:
        st.session_state["a2_memory_demo_counter"] = 0


def main() -> None:
    st.set_page_config(page_title="RAGstream", layout="wide")

    # Base CSS / compact styles
    inject_base_css()

    # Page title
    st.title("RAGstream")

    # Session bootstrap / background heavy init
    init_session_state()

    # Page layout
    render_page()
    if st.session_state.pop("pending_a2_memory_refresh", False):
       st.rerun()

if __name__ == "__main__":
    main()