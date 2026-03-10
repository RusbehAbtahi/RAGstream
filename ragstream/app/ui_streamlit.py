# -*- coding: utf-8 -*-
"""
Run on a free port, e.g.:
  /home/rusbeh_ab/venvs/ragstream/bin/python -m streamlit run /home/rusbeh_ab/project/RAGstream/ragstream/app/ui_streamlit_2.py --server.port 8503
"""

from __future__ import annotations
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
    if "super_prompt_text" not in st.session_state:
        st.session_state["super_prompt_text"] = ""
    if "ingestion_status" not in st.session_state:
        st.session_state["ingestion_status"] = None
    if "new_project_name" not in st.session_state:
        st.session_state["new_project_name"] = ""

    # Layout: gutters left/right, two main columns, small spacer between
    gutter_l, col_left, spacer, col_right, gutter_r = st.columns([0.6, 4, 0.25, 4, 0.6], gap="small")

    with gutter_l:
        st.empty()

    # LEFT: Prompt + two rows of pipeline buttons
    with col_left:
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
                st.session_state["super_prompt_text"] = sp.prompt_ready

        with b1c2:
            clicked_a2 = st.button("A2-PromptShaper", key="btn_a2", use_container_width=True)
            if clicked_a2:
                ctrl: AppController = st.session_state.controller
                sp: SuperPrompt = st.session_state.sp
                sp = ctrl.run_a2_promptshaper(sp)
                st.session_state.sp = sp
                st.session_state["super_prompt_text"] = sp.prompt_ready

        with b1c3:
            st.button("Retrieval", key="btn_retrieval", use_container_width=True)
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

        # Added on 10.03.2026:
        # New project-based ingestion controls placed below the agent buttons.
        st.markdown("<div style='height:0.45rem'></div>", unsafe_allow_html=True)

        ctrl: AppController = st.session_state.controller
        projects = ctrl.list_projects()

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

        create_col, add_col = st.columns(2, gap="small")

        with create_col:
            with st.form("create_project_form", clear_on_submit=False):
                st.text_input("Project Name", key="new_project_name")
                create_clicked = st.form_submit_button("Create Project", use_container_width=True)
                if create_clicked:
                    try:
                        result = ctrl.create_project(st.session_state.get("new_project_name", ""))
                        st.session_state["active_project"] = result["project_name"]
                        st.session_state["ingestion_status"] = {
                            "type": "success",
                            "message": f"Project created: {result['project_name']}",
                            "details": [
                                f"doc_raw: {result['raw_dir']}",
                                f"chroma_db: {result['chroma_dir']}",
                                f"manifest: {result['manifest_path']}",
                            ],
                        }
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
                    if st.session_state.get("active_project") not in add_projects:
                        st.session_state["active_project"] = add_projects[0]

                    st.selectbox(
                        "Choose Project",
                        options=add_projects,
                        key="add_files_project",
                        index=add_projects.index(st.session_state.get("active_project", add_projects[0])),
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
                                st.session_state["active_project"] = result["project_name"]
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

        # Added on 10.03.2026:
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