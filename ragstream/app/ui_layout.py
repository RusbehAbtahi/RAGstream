# ragstream/app/ui_layout.py
# -*- coding: utf-8 -*-
"""
Layout / geometry helpers for Streamlit UI.
Keep columns, containers, labels and visual order here.
"""

from __future__ import annotations

import html
import time

import streamlit as st

from ragstream.app.controller import AppController
from ragstream.app.ui_actions import (
    do_a2_promptshaper,
    do_a3_nli_gate,
    do_a4_condenser,
    do_add_files,
    do_confirm_memory_title_and_save,
    do_create_project,
    do_feed_memory_manually,
    do_preprocess,
    do_reranker,
    do_retrieval,
)


TAG_COLORS: dict[str, str] = {
    "Gold": "#D4AF37",
    "Green": "#00A86B",
    "Black": "#111111",
}


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

            .memory-tag-indicator {
                display: flex;
                align-items: center;
                gap: 0.35rem;
                margin-bottom: 0.25rem;
                min-height: 24px;
            }

            .memory-tag-square {
                width: 18px;
                height: 18px;
                border-radius: 0.25rem;
                border: 1px solid rgba(0, 0, 0, 0.25);
                box-shadow: 0 1px 2px rgba(0, 0, 0, 0.16);
                flex: 0 0 auto;
            }

            .memory-tag-name {
                font-size: 0.78rem;
                color: #374151;
                line-height: 1.0;
                white-space: nowrap;
            }



            /* Manual memory feed button */
            div[data-testid="stButton"] > button[kind="primary"] {
                background-color: #3F48CC !important;
                border-color: #3F48CC !important;
                color: white !important;
            }

            div[data-testid="stButton"] > button[kind="primary"]:hover {
                background-color: #3F48CC !important;
                border-color: #3F48CC !important;
                color: white !important;
            }

            div[data-testid="stButton"] > button[kind="primary"]:focus {
                background-color: #3F48CC !important;
                border-color: #3F48CC !important;
                color: white !important;
            }

            div[data-testid="stButton"] > button[kind="primary"] p {
                color: white !important;
            }

            /* Manual memory feed edit box */
            textarea[aria-label="Manual Memory Feed (hidden)"] {
                background-color: #EAF7FF !important;
            }



            /* TextForge GUI log box */
            .textforge-log-box {
                background-color: #EAFBEA;
                border: 1px solid #B7E4B7;
                border-radius: 0.45rem;
                padding: 0.55rem 0.70rem;
                min-height: 140px;
                max-height: 180px;
                overflow-y: auto;
                white-space: normal;
                word-break: break-word;
                font-family: monospace;
                font-size: 0.88rem;
                line-height: 1.35;
            }

            /* Make small select boxes look compact */
            div[data-baseweb="select"] > div {
                min-height: 34px;
            }

            /* Direct Recall Key field: special red border */
            div[data-testid="stTextInput"]:has(input[aria-label="Direct Recall Key"]) div[data-baseweb="input"] {
                border: 2px solid #D11A2A !important;
                border-radius: 0.45rem !important;
                box-shadow: none !important;
            }

            div[data-testid="stTextInput"]:has(input[aria-label="Direct Recall Key"]) div[data-baseweb="input"]:focus-within {
                border: 2px solid #D11A2A !important;
                box-shadow: 0 0 0 1px rgba(209, 26, 42, 0.25) !important;
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
      Memory
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
    """Right panel: Memory at top, all controls below."""
    ctrl: AppController = st.session_state.controller
    retrieval_ready = getattr(ctrl, "retriever", None) is not None
    reranker_ready = getattr(ctrl, "reranker", None) is not None

    # Memory section
    render_memory_records(height=420)

    st.markdown("<div style='height:0.45rem'></div>", unsafe_allow_html=True)

    # Manual memory feed row
    manual_feed_c1, manual_feed_c2 = st.columns([1, 3], gap="small")

    with manual_feed_c1:  # Manual memory feed button
        if st.button(
            "Feed Memory Manually",
            key="btn_feed_memory_manually",
            use_container_width=True,
            type="primary",
        ):
            do_feed_memory_manually()

    with manual_feed_c2:  # Manual memory feed edit box
        st.text_area(
            label="Manual Memory Feed (hidden)",
            key="manual_memory_feed_text",
            height=68,
            label_visibility="collapsed",
            placeholder="Paste LLM reply here for manual memory feed.",
        )

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
        if st.button("A4 Condenser", key="btn_a4", use_container_width=True):
            do_a4_condenser()

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

    # TextForge GUI log / status log
    render_textforge_gui_log(height=150)

    st.markdown("<div style='height:0.45rem'></div>", unsafe_allow_html=True)

    # Project controls / file ingestion
    render_project_area(ctrl)


def render_textforge_gui_log(height: int = 150) -> None:
    """Render the TextForge GUI log box."""
    st.markdown(
        '<div class="field-title" style="font-size:1.05rem;">Runtime Log</div>',
        unsafe_allow_html=True,
    )

    log_text = st.session_state.get("textforge_gui_log", "")
    if not log_text:
        log_text = "(no log messages yet)"

    lines = log_text.splitlines()
    if lines:
        first_line = html.escape(lines[0])
        older_lines = "<br>".join(
            f"<i>{html.escape(line)}</i>"
            for line in lines[1:]
        )
        if older_lines:
            log_html = f"{first_line}<br>{older_lines}"
        else:
            log_html = first_line
    else:
        log_html = ""

    flash_active = time.time() < st.session_state.get("runtime_log_flash_until", 0)

    if flash_active:
        log_box_style = (
            f"min-height:{height}px; max-height:{height}px;"
            "background-color:#FFE5E5; border-color:#FF9A9A;"
        )
    else:
        log_box_style = f"min-height:{height}px; max-height:{height}px;"

    st.markdown(
        f'<div class="textforge-log-box" style="{log_box_style}">{log_html}</div>',
        unsafe_allow_html=True,
    )


def render_memory_records(height: int = 420) -> None:
    """Memory record list."""
    memory_manager = st.session_state.memory_manager

    if memory_manager.filename_ragmem:
        memory_title = f"Memory — {memory_manager.filename_ragmem}"
    else:
        memory_title = "Memory"

    st.markdown(
        f'<div class="field-title">{html.escape(memory_title)}</div>',
        unsafe_allow_html=True,
    )

    if st.session_state.get("memory_title_required"):
        render_memory_title_form()

    memory_entries = memory_manager.records

    try:
        memory_container = st.container(height=height)
    except TypeError:
        memory_container = st.container()

    with memory_container:  # Memory container
        if not memory_entries:
            st.info("No memory records yet.")
        else:
            for record in memory_entries:
                tag_key = f"memory_tag_{record.record_id}"
                source_mode_key = f"memory_retrieval_source_mode_{record.record_id}"
                keywords_key = f"memory_user_keywords_{record.record_id}"
                direct_recall_key = f"memory_direct_recall_key_{record.record_id}"

                tag_options = list(memory_manager.tag_catalog)
                record_tag = record.tag if record.tag in tag_options else "Green"

                if tag_key not in st.session_state:
                    st.session_state[tag_key] = record_tag
                elif st.session_state[tag_key] not in tag_options:
                    st.session_state[tag_key] = "Green"

                if source_mode_key not in st.session_state:
                    st.session_state[source_mode_key] = getattr(record, "retrieval_source_mode", "QA")
                elif st.session_state[source_mode_key] not in {"QA", "Q", "A"}:
                    st.session_state[source_mode_key] = "QA"

                if keywords_key not in st.session_state:
                    st.session_state[keywords_key] = ", ".join(record.user_keywords)

                if direct_recall_key not in st.session_state:
                    st.session_state[direct_recall_key] = getattr(record, "direct_recall_key", "")

                selected_tag = st.session_state.get(tag_key, record_tag)
                tag_color = TAG_COLORS.get(selected_tag, "#6B7280")

                input_col, meta_col = st.columns([7.8, 2.0], gap="small")

                with input_col:  # Memory INPUT box
                    input_html = html.escape(record.input_text).replace("\n", "<br>")
                    st.markdown(
                        f"""
                        <div class="memory-box memory-input-box">
                            <div class="memory-label">INPUT</div>
                            <div class="memory-plain-text">{input_html}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                with meta_col:  # Memory metadata controls
                    tag_square_col, tag_select_col = st.columns([0.22, 1.0], gap="small")

                    with tag_square_col:
                        st.markdown(
                            f"""
                            <div class="memory-tag-indicator">
                                <span class="memory-tag-square" style="background-color:{tag_color};"></span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    with tag_select_col:
                        st.selectbox(
                            "Tag",
                            options=tag_options,
                            key=tag_key,
                            label_visibility="collapsed",
                        )

                    st.selectbox(
                        "Retrieval Source Mode",
                        options=["QA", "Q", "A"],
                        key=source_mode_key,
                        format_func={
                            "QA": "Retrieve Q+A",
                            "Q": "Retrieve only Q",
                            "A": "Retrieve only A",
                        }.get,
                        label_visibility="collapsed",
                    )

                   # st.text_input(
                    #    "User Keywords",
                     #   key=keywords_key,
                      #  label_visibility="collapsed",
                       # placeholder="keywords",
                    #)

                    st.text_input(
                        "Direct Recall Key",
                        key=direct_recall_key,
                        placeholder="Direct Recall Key",
                     #   label_visibility="collapsed",
                    )

                output_html = html.escape(record.output_text).replace("\n", "<br>")
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


def render_memory_title_form() -> None:
    """Ask for first memory title before creating the first .ragmem file."""
    with st.form("memory_title_form", clear_on_submit=False):
        st.text_input(
            "Memory Title",
            key="memory_title_input",
            placeholder="Example: Memory Design",
        )
        submitted = st.form_submit_button("Create Memory File", use_container_width=True)

        if submitted:
            do_confirm_memory_title_and_save()


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