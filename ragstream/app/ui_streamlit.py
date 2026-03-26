# -*- coding: utf-8 -*-
"""
Run on a free port, e.g.:
  /home/rusbeh_ab/venvs/ragstream/bin/python -m streamlit run /home/rusbeh_ab/project/RAGstream/ragstream/app/ui_streamlit.py --server.port 8503
"""

from __future__ import annotations
import copy
import html

import streamlit as st

from ragstream.app.controller import AppController
from ragstream.orchestration.super_prompt import SuperPrompt


def main() -> None:
    st.set_page_config(page_title="RAGstream", layout="wide")

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

            /* Make the row gaps compact */
            div[data-testid="stHorizontalBlock"]{
                gap: 0.4rem !important;
            }

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

    st.title("RAGstream")

    # one controller + one SuperPrompt per user session
    if "controller" not in st.session_state:
        st.session_state.controller = AppController()
    if "sp" not in st.session_state:
        st.session_state.sp = SuperPrompt()
    if "sp_pre" not in st.session_state:
        st.session_state.sp_pre = SuperPrompt()
    if "sp_a2" not in st.session_state:
        st.session_state.sp_a2 = SuperPrompt()
    if "sp_rtv" not in st.session_state:
        st.session_state.sp_rtv = SuperPrompt()
    if "super_prompt_text" not in st.session_state:
        st.session_state["super_prompt_text"] = ""
    if "ingestion_status" not in st.session_state:
        st.session_state["ingestion_status"] = None
    if "new_project_name" not in st.session_state:
        st.session_state["new_project_name"] = ""
    if "pending_active_project" not in st.session_state:
        # Temporary project switch key. We use this instead of modifying
        # the widget-owned key "active_project" after that widget exists.
        st.session_state["pending_active_project"] = None
    if "retrieval_top_k" not in st.session_state:
        st.session_state["retrieval_top_k"] = 100
    if "a2_memory_demo_entries" not in st.session_state:
        st.session_state["a2_memory_demo_entries"] = []
    if "a2_memory_demo_counter" not in st.session_state:
        st.session_state["a2_memory_demo_counter"] = 0

    # Layout: gutters left/right, two main columns, small spacer between
    gutter_l, col_left, spacer, col_right, gutter_r = st.columns([0.6, 4, 0.25, 4, 0.6], gap="small")

    with gutter_l:
        st.empty()

    # LEFT: Memory Demo + Prompt + two rows of pipeline buttons
    with col_left:
        st.markdown('<div class="field-title">MEMORY DEMO</div>', unsafe_allow_html=True)

        memory_entries = st.session_state["a2_memory_demo_entries"]

        try:
            memory_container = st.container(height=780)
        except TypeError:
            memory_container = st.container()

        with memory_container:
            if not memory_entries:
                st.info("No memory entries yet.")
            else:
                for entry in memory_entries:
                    entry_id = entry["id"]
                    tag_key = f"a2_memory_tag_{entry_id}"

                    if tag_key not in st.session_state:
                        st.session_state[tag_key] = entry.get("tag", "Green")

                    input_col, tag_col = st.columns([8.8, 1.0], gap="small")

                    with input_col:
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

                    with tag_col:
                        selected_tag = st.selectbox(
                            "Tag",
                            options=["Platin", "GOLD", "SILVER", "Green", "Black"],
                            key=tag_key,
                            index=["Platin", "GOLD", "SILVER", "Green", "Black"].index(
                                st.session_state[tag_key]
                            ),
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

        st.markdown("<div style='height:0.45rem'></div>", unsafe_allow_html=True)

        st.markdown('<div class="field-title">Prompt</div>', unsafe_allow_html=True)
        st.text_area(
            label="Prompt (hidden)",
            key="prompt_text",
            height=240,
            label_visibility="collapsed",
        )

        # Small vertical spacer
        st.markdown("<div style='height:0.35rem'></div>", unsafe_allow_html=True)

        # Row 1: 4 buttons
        b1c1, b1c2, b1c3, b1c4 = st.columns(4, gap="small")
        with b1c1:
            clicked = st.button("Pre-Processing", key="btn_preproc", use_container_width=True)
            if clicked:
                ctrl: AppController = st.session_state.controller
                sp: SuperPrompt = st.session_state.sp
                user_text = st.session_state.get("prompt_text", "")
                sp = ctrl.preprocess(user_text, sp)
                st.session_state.sp = sp
                st.session_state.sp_pre = copy.deepcopy(sp)
                st.session_state["super_prompt_text"] = sp.prompt_ready

        with b1c2:
            clicked_a2 = st.button("A2-PromptShaper", key="btn_a2", use_container_width=True)
            if clicked_a2:
                ctrl: AppController = st.session_state.controller
                sp: SuperPrompt = st.session_state.sp

                sp = ctrl.run_a2_promptshaper(sp)
                entry = ctrl.build_a2_memory_demo_entry(sp)

                next_id = st.session_state.get("a2_memory_demo_counter", 0) + 1
                st.session_state["a2_memory_demo_counter"] = next_id
                entry["id"] = next_id

                st.session_state[f"a2_memory_tag_{next_id}"] = "Green"
                st.session_state["a2_memory_demo_entries"].append(entry)

                st.session_state.sp = sp
                st.session_state.sp_a2 = copy.deepcopy(sp)
                st.session_state["super_prompt_text"] = sp.prompt_ready

                st.rerun()

        with b1c3:
            clicked_retrieval = st.button("Retrieval", key="btn_retrieval", use_container_width=True)
            if clicked_retrieval:
                try:
                    ctrl: AppController = st.session_state.controller
                    sp: SuperPrompt = st.session_state.sp

                    project_name = st.session_state.get("active_project")
                    if not project_name:
                        available_projects = ctrl.list_projects()
                        if available_projects:
                            project_name = available_projects[0]
                            st.session_state["active_project"] = project_name

                    if not project_name or project_name == "(no projects yet)":
                        st.error("No active project is available for Retrieval.")
                    else:
                        top_k = int(st.session_state.get("retrieval_top_k", 100))
                        sp = ctrl.run_retrieval(sp, project_name, top_k)
                        sp.compose_prompt_ready()

                        st.session_state.sp = sp
                        st.session_state.sp_rtv = copy.deepcopy(sp)
                        st.session_state["super_prompt_text"] = sp.prompt_ready

                except Exception as e:
                    st.error(str(e))

        with b1c4:
            st.button("ReRanker", key="btn_reranker", use_container_width=True)

        # Row 2: 4 buttons
        b2c1, b2c2, b2c3, b2c4 = st.columns(4, gap="small")
        with b2c1:
            st.button("A3 NLI Gate", key="btn_a3", use_container_width=True)
        with b2c2:
            st.button("A4 Condenser", key="btn_a4", use_container_width=True)
        with b2c3:
            st.button("A5 Format Enforcer", key="btn_a5", use_container_width=True)
        with b2c4:
            st.button("Prompt Builder", key="btn_builder", use_container_width=True)

        st.number_input(
            "Retrieval Top-K (number of chunks)",
            min_value=1,
            max_value=1000,
            step=1,
            key="retrieval_top_k",
        )

        # New project-based ingestion controls placed below the agent buttons.
        st.markdown("<div style='height:0.45rem'></div>", unsafe_allow_html=True)

        ctrl: AppController = st.session_state.controller
        projects = ctrl.list_projects()

        # Apply requested project switch before the "active_project" widget
        # is created in this run. This avoids the Streamlit session-state error.
        pending_project = st.session_state.get("pending_active_project")
        if pending_project is not None:
            if projects and pending_project in projects:
                st.session_state["active_project"] = pending_project
            st.session_state["pending_active_project"] = None

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

        # Show the files that are actually ingested/embedded for the currently
        # active project by reading the standardized manifest through the controller.
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

        create_col, add_col = st.columns(2, gap="small")

        with create_col:
            with st.form("create_project_form", clear_on_submit=False):
                st.text_input("Project Name", key="new_project_name")
                create_clicked = st.form_submit_button("Create Project", use_container_width=True)
                if create_clicked:
                    try:
                        result = ctrl.create_project(st.session_state.get("new_project_name", ""))
                        st.session_state["ingestion_status"] = {
                            "type": "success",
                            "message": f"Project created: {result['project_name']}",
                            "details": [
                                f"doc_raw: {result['raw_dir']}",
                                f"chroma_db: {result['chroma_dir']}",
                                f"manifest: {result['manifest_path']}",
                            ],
                        }
                        st.session_state["pending_active_project"] = result["project_name"]
                        st.rerun()
                    except Exception as e:
                        st.session_state["ingestion_status"] = {
                            "type": "error",
                            "message": str(e),
                            "details": [],
                        }

        with add_col:
            with st.form("add_files_form", clear_on_submit=False):
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
                    uploaded_files = st.file_uploader(
                        "Select .txt / .md files from your local machine",
                        type=["txt", "md"],
                        accept_multiple_files=True,
                        key="ingestion_uploaded_files",
                    )
                    add_clicked = st.form_submit_button("Add Files", use_container_width=True)
                    if add_clicked:
                        try:
                            result = ctrl.import_files_to_project(
                                st.session_state.get("add_files_project", ""),
                                uploaded_files=uploaded_files,
                            )
                            if result.get("success"):
                                st.session_state["ingestion_status"] = {
                                    "type": "success",
                                    "message": (
                                        f"Files added to {result['project_name']} "
                                        f"and ingestion finished."
                                    ),
                                    "details": [
                                        f"copied files: {result.get('copied_count', 0)}",
                                        f"files scanned: {result.get('files_scanned', 0)}",
                                        f"to process: {result.get('to_process', 0)}",
                                        f"unchanged: {result.get('unchanged', 0)}",
                                        f"vectors upserted: {result.get('vectors_upserted', 0)}",
                                        f"manifest: {result.get('manifest_path', '')}",
                                    ] + [
                                        f"rejected: {item}" for item in result.get("rejected_files", [])
                                    ],
                                }
                                st.session_state["pending_active_project"] = result["project_name"]
                                st.rerun()
                            else:
                                st.session_state["ingestion_status"] = {
                                    "type": "error",
                                    "message": result.get("message", "No files were added."),
                                    "details": [
                                        f"rejected: {item}" for item in result.get("rejected_files", [])
                                    ],
                                }
                        except Exception as e:
                            st.session_state["ingestion_status"] = {
                                "type": "error",
                                "message": str(e),
                                "details": [],
                            }
                else:
                    st.info("Create a project first, then add files.")

        # Small status/debug area for the new ingestion workflow.
        status = st.session_state.get("ingestion_status")
        if status:
            if status.get("type") == "success":
                st.success(status.get("message", ""))
            else:
                st.error(status.get("message", ""))
            for detail in status.get("details", []):
                st.caption(detail)

    # SPACER between columns
    with spacer:
        st.empty()

    # RIGHT: Super-Prompt box
    with col_right:
        st.markdown('<div class="field-title">Super-Prompt</div>', unsafe_allow_html=True)
        st.text_area(
            label="Super-Prompt (hidden)",
            key="super_prompt_text",
            height=240,
            label_visibility="collapsed",
        )

    with gutter_r:
        st.empty()


if __name__ == "__main__":
    main()