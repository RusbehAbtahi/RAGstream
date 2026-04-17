# ragstream/app/ui_layout.py
# -*- coding: utf-8 -*-
"""
Layout / geometry helpers for Streamlit UI.
Keep columns, containers, labels and visual order here.
"""

from __future__ import annotations

import html

import streamlit as st

from ragstream.app.controller import AppController
from ragstream.app.ui_actions import (
    do_a2_promptshaper,
    do_a3_nli_gate,
    do_add_files,
    do_create_project,
    do_preprocess,
    do_reranker,
    do_retrieval,
)


def inject_base_css() -> None:
    """Global CSS for simple spacing and boxes."""
    st.markdown(
        """
        <style>
            /* Hide Streamlit header/toolbar to reduce top gap */
            header {visibility: hidden;}
            div[data-testid="stHeader"] {display: none;}
            div[data-testid="stToolbar"] {display: none;}

            /* Tighten page paddings to push content up/left */
            .block-container {
                padding-top: 0.2rem;
                padding-bottom: 0rem;
                padding-left: 0.6rem;
                padding-right: 0.6rem;
            }

            /* Big, bold custom field titles */
            .field-title {
                font-size: 1.8rem;
                font-weight: 800;
                line-height: 1.2;
                margin-bottom: 0.35rem;
            }

            /* Make row gaps compact */
            div[data-testid="stHorizontalBlock"]{
                gap: 0.4rem !important;
            }

            /* Memory card style */
            .memory-box {
                border-radius: 0.45rem;
                padding: 0.55rem 0.7rem;
                border: 1px solid #d8d8d8;
                font-size: 0.95rem;
                line-height: 1.35;
                white-space: normal;
                word-break: break-word;
            }

            .memory-input-box {
                background-color: #ffffff;
            }

            .memory-output-box {
                background-color: #f3f4f6;
            }

            .memory-label {
                font-size: 0.82rem;
                font-weight: 700;
                margin-bottom: 0.25rem;
                color: #4b5563;
                letter-spacing: 0.02em;
            }

            .memory-plain-text {
                white-space: pre-wrap;
                font-size: 0.95rem;
                line-height: 1.35;
                margin: 0;
                font-family: inherit;
            }

            /* Make small select boxes look compact */
            div[data-baseweb="select"] > div {
                min-height: 34px;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page() -> None:
    """
    Two-column layout:

    LEFT:
      Prompt
      Super-Prompt

    RIGHT:
      Memory Demo
      Buttons / Top-K / project controls / status
    """
    # Main 2-column layout
    gutter_l, col_left, spacer, col_right, gutter_r = st.columns([0.6, 4, 0.25, 4, 0.6], gap="small")

    with gutter_l:  # left gutter
        st.empty()

    with col_right:
        render_right_panel()

    with spacer:
        st.empty()

    with col_left:
        render_left_panel()

    with gutter_r:  # right gutter
        st.empty()


def render_left_panel() -> None:
    """Left panel: Prompt at top, Super-Prompt below."""
    # Prompt section
    st.markdown('<div class="field-title">Prompt</div>', unsafe_allow_html=True)
    st.text_area(
        label="Prompt (hidden)",
        key="prompt_text",
        height=240,
        label_visibility="collapsed",
    )

    st.markdown("<div style='height:0.45rem'></div>", unsafe_allow_html=True)

    # Super-Prompt section
    st.markdown('<div class="field-title">Super-Prompt</div>', unsafe_allow_html=True)
    st.text_area(
        label="Super-Prompt (hidden)",
        key="super_prompt_text",
        height=780,
        label_visibility="collapsed",
    )


def render_right_panel() -> None:
    """Right panel: Memory Demo at top, all controls below."""
    ctrl: AppController = st.session_state.controller
    retrieval_ready = getattr(ctrl, "retriever", None) is not None
    reranker_ready = getattr(ctrl, "reranker", None) is not None

    # Memory Demo section
    st.markdown('<div class="field-title">MEMORY DEMO</div>', unsafe_allow_html=True)
    render_memory_demo(height=420)

    st.markdown("<div style='height:0.45rem'></div>", unsafe_allow_html=True)

    # Row 1: 4 pipeline buttons
    b1c1, b1c2, b1c3, b1c4 = st.columns(4, gap="small")

    with b1c1:  # Pre-Processing button
        if st.button("Pre-Processing", key="btn_preproc", use_container_width=True):
            do_preprocess()

    with b1c2:  # A2-PromptShaper button
        if st.button("A2-PromptShaper", key="btn_a2", use_container_width=True):
            do_a2_promptshaper()

    with b1c3:  # Retrieval button
        if st.button(
            "Retrieval",
            key="btn_retrieval",
            use_container_width=True,
            disabled=not retrieval_ready,
        ):
            do_retrieval()

    with b1c4:  # ReRanker button
        if st.button(
            "ReRanker",
            key="btn_reranker",
            use_container_width=True,
            disabled=not reranker_ready,
        ):
            do_reranker()

    # Row 2: 4 pipeline buttons
    b2c1, b2c2, b2c3, b2c4 = st.columns(4, gap="small")

    with b2c1:  # A3 NLI Gate button
        if st.button("A3 NLI Gate", key="btn_a3", use_container_width=True):
            do_a3_nli_gate()

    with b2c2:  # A4 button
        st.button("A4 Condenser", key="btn_a4", use_container_width=True)

    with b2c3:  # A5 button
        st.button("A5 Format Enforcer", key="btn_a5", use_container_width=True)

    with b2c4:  # Prompt Builder button
        st.button("Prompt Builder", key="btn_builder", use_container_width=True)

    topk_c, gap_c, opt_c1, opt_c2 = st.columns([0.5, 1, 1, 1],
                                               gap="small")  # row: Top-K + spacer + 2 checkboxes

    with topk_c:  # number input: Retrieval Top-K
        st.number_input(
            "Retrieval Top-K",
            min_value=1,
            max_value=1000,
            step=1,
            key="retrieval_top_k",
        )

    with gap_c:  # empty spacer between Top-K and first checkbox
        st.empty()

    with opt_c1:  # checkbox: use Retrieval Splade
        st.checkbox(
            "use Retrieval Splade",
            key="use_retrieval_splade",
        )

    with opt_c2:  # checkbox: use Reranking Colbert
        st.checkbox(
            "use Reranking Colbert",
            key="use_reranking_colbert",
        )

    st.markdown("<div style='height:0.45rem'></div>", unsafe_allow_html=True)

    # Project controls / file ingestion
    render_project_area(ctrl)


def render_memory_demo(height: int = 420) -> None:
    """Memory Demo list."""
    memory_entries = st.session_state["a2_memory_demo_entries"]

    try:
        memory_container = st.container(height=height)
    except TypeError:
        memory_container = st.container()

    with memory_container:  # Memory container
        if not memory_entries:
            st.info("No memory entries yet.")
        else:
            for entry in memory_entries:
                entry_id = entry["id"]
                tag_key = f"a2_memory_tag_{entry_id}"

                if tag_key not in st.session_state:
                    st.session_state[tag_key] = entry.get("tag", "Green")

                input_col, tag_col = st.columns([8.8, 1.0], gap="small")

                with input_col:  # Memory INPUT box
                    input_html = html.escape(entry.get("input_text", "")).replace("\n", "<br>")
                    st.markdown(
                        f"""
                        <div class="memory-box memory-input-box">
                            <div class="memory-label">INPUT</div>
                            <div class="memory-plain-text">{input_html}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                with tag_col:  # Memory TAG selectbox
                    selected_tag = st.selectbox(
                        "Tag",
                        options=["Platin", "GOLD", "SILVER", "Green", "Black"],
                        key=tag_key,
                        label_visibility="collapsed",
                    )
                    entry["tag"] = selected_tag

                output_html = html.escape(entry.get("output_text", "")).replace("\n", "<br>")
                st.markdown(
                    f"""
                    <div class="memory-box memory-output-box">
                        <div class="memory-label">OUTPUT</div>
                        <div class="memory-plain-text">{output_html}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.markdown("<div style='height:0.40rem'></div>", unsafe_allow_html=True)


def render_project_area(ctrl: AppController) -> None:
    """Project selector, embedded files, Create Project and Add Files forms."""
    projects = ctrl.list_projects()

    # Apply pending project switch before widget creation
    pending_project = st.session_state.get("pending_active_project")
    if pending_project is not None:
        if projects and pending_project in projects:
            st.session_state["active_project"] = pending_project
        st.session_state["pending_active_project"] = None

    # Active project selectbox
    if projects:
        if st.session_state.get("active_project") not in projects:
            st.session_state["active_project"] = projects[0]

        st.selectbox(
            "Active DB / Project",
            options=projects,
            key="active_project",
        )
    else:
        st.selectbox(
            "Active DB / Project",
            options=["(no projects yet)"],
            index=0,
            disabled=True,
        )

    # Embedded Files view
    active_project = st.session_state.get("active_project")
    if projects and active_project in projects:
        embedded_info = ctrl.get_embedded_files(active_project)

        st.markdown("<div style='height:0.25rem'></div>", unsafe_allow_html=True)
        st.markdown(
            '<div class="field-title" style="font-size:1.05rem;">Embedded Files</div>',
            unsafe_allow_html=True,
        )

        if embedded_info.get("success"):
            embedded_files = embedded_info.get("files", [])
            embedded_text = "\n".join(embedded_files) if embedded_files else "(no embedded files yet)"
            st.text_area(
                label="Embedded Files (hidden)",
                value=embedded_text,
                height=120,
                disabled=True,
                label_visibility="collapsed",
            )
        else:
            st.error(embedded_info.get("message", "Could not read embedded file list."))

    # Project forms row
    create_col, add_col = st.columns(2, gap="small")

    with create_col:  # Create Project form
        with st.form("create_project_form", clear_on_submit=False):  # form: create project
            st.text_input("Project Name", key="new_project_name")
            create_clicked = st.form_submit_button("Create Project", use_container_width=True)

            if create_clicked:
                do_create_project()

    with add_col:  # Add Files form
        with st.form("add_files_form", clear_on_submit=False):  # form: add files
            add_projects = ctrl.list_projects()

            if add_projects:
                current_active_project = st.session_state.get("active_project")
                if current_active_project in add_projects:
                    default_add_project = current_active_project
                else:
                    default_add_project = add_projects[0]

                st.selectbox(
                    "Choose Project",
                    options=add_projects,
                    key="add_files_project",
                    index=add_projects.index(default_add_project),
                )

                st.file_uploader(
                    "Select .txt / .md files from your local machine",
                    type=["txt", "md"],
                    accept_multiple_files=True,
                    key="ingestion_uploaded_files",
                )

                add_clicked = st.form_submit_button("Add Files", use_container_width=True)

                if add_clicked:
                    do_add_files()
            else:
                st.info("Create a project first, then add files.")

    # Status area
    status = st.session_state.get("ingestion_status")
    if status:
        if status.get("type") == "success":
            st.success(status.get("message", ""))
        else:
            st.error(status.get("message", ""))
        for detail in status.get("details", []):
            st.caption(detail)