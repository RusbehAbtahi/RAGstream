# ragstream/app/ui_actions.py
# -*- coding: utf-8 -*-
"""
Small callback helpers for Streamlit button/form actions.
Keep controller calls and session-state mutations here.
"""

from __future__ import annotations

import copy
import time

from typing import Any

import streamlit as st

from ragstream.app.controller import AppController
from ragstream.memory.memory_actions import capture_memory_pair
from ragstream.memory.memory_manager import MemoryManager
from ragstream.orchestration.super_prompt import SuperPrompt


def _log_runtime(
    text: str,
    type: str = "INFO",
    sensitivity: str = "PUBLIC",
) -> None:
    logger = st.session_state.get("raglog")
    if logger is not None:
        logger(text, type, sensitivity)


def do_preprocess() -> None:
    ctrl: AppController = st.session_state.controller
    user_text = st.session_state.get("prompt_text", "")

    # Start a fresh pipeline run from clean SuperPrompt objects
    st.session_state.sp = SuperPrompt()
    st.session_state.sp_pre = SuperPrompt()
    st.session_state.sp_a2 = SuperPrompt()
    st.session_state.sp_rtv = SuperPrompt()
    st.session_state.sp_rrk = SuperPrompt()
    st.session_state.sp_a3 = SuperPrompt()
    st.session_state.sp_a4 = SuperPrompt()

    sp: SuperPrompt = st.session_state.sp
    sp = ctrl.preprocess(user_text, sp)

    st.session_state.sp = sp
    st.session_state.sp_pre = copy.deepcopy(sp)
    st.session_state["super_prompt_text"] = sp.prompt_ready


def do_a2_promptshaper() -> None:
    """A2 button callback."""
    ctrl: AppController = st.session_state.controller
    sp: SuperPrompt = st.session_state.sp

    sp = ctrl.run_a2_promptshaper(sp)

    st.session_state.sp = sp
    st.session_state.sp_a2 = copy.deepcopy(sp)
    st.session_state["super_prompt_text"] = sp.prompt_ready


def do_feed_memory_manually() -> None:
    """Manual memory feed button callback."""
    prompt_text = st.session_state.get("prompt_text", "")
    output_text = st.session_state.get("manual_memory_feed_text", "")

    if not (prompt_text or "").strip():
        _log_runtime("Prompt is empty. No memory record was created.", "WARN", "PUBLIC")
        return

    if not (output_text or "").strip():
        _log_runtime("Manual memory response is empty. No memory record was created.", "WARN", "PUBLIC")
        return

    memory_manager: MemoryManager = st.session_state.memory_manager

    if not memory_manager.title.strip():
        st.session_state["pending_manual_memory_pair"] = {
            "input_text": prompt_text,
            "output_text": output_text,
        }
        st.session_state["memory_title_required"] = True
        _log_runtime("Enter a memory title to create the first memory file.", "INFO", "PUBLIC")
        st.session_state["runtime_log_flash_until"] = time.time() + 5
        st.rerun()

    _save_memory_pair(
        input_text=prompt_text,
        output_text=output_text,
    )


def do_confirm_memory_title_and_save() -> None:
    """Confirm first memory title and save pending manual memory pair."""
    title = (st.session_state.get("memory_title_input", "") or "").strip()
    if not title:
        _log_runtime("Memory title must not be empty.", "WARN", "PUBLIC")
        return

    memory_manager: MemoryManager = st.session_state.memory_manager

    if not memory_manager.title.strip():
        memory_manager.start_new_history(title)
        _log_runtime(f"Memory file created: {memory_manager.filename_ragmem}", "INFO", "PUBLIC")

    pending_pair = st.session_state.get("pending_manual_memory_pair")
    if pending_pair:
        input_text = pending_pair.get("input_text", "")
        output_text = pending_pair.get("output_text", "")
    else:
        input_text = st.session_state.get("prompt_text", "")
        output_text = st.session_state.get("manual_memory_feed_text", "")

    _save_memory_pair(
        input_text=input_text,
        output_text=output_text,
    )


def _save_memory_pair(
    input_text: str,
    output_text: str,
) -> None:
    try:
        ctrl: AppController = st.session_state.controller
        memory_manager: MemoryManager = st.session_state.memory_manager

        active_project_name, embedded_files_snapshot = _get_active_project_snapshot(ctrl)
        gui_records_state = _collect_memory_gui_state(memory_manager)

        result = capture_memory_pair(
            memory_manager=memory_manager,
            input_text=input_text,
            output_text=output_text,
            source="manual_memory_feed",
            active_project_name=active_project_name,
            embedded_files_snapshot=embedded_files_snapshot,
            gui_records_state=gui_records_state,
        )

        if result.get("success"):
            _log_runtime(result.get("message", "Memory record saved."), "INFO", "PUBLIC")
            st.session_state["pending_manual_memory_pair"] = None
            st.session_state["memory_title_required"] = False
            st.session_state["manual_memory_feed_text"] = ""
            st.rerun()
        else:
            _log_runtime(result.get("message", "Memory record was not saved."), "WARN", "PUBLIC")

    except Exception as e:
        _log_runtime(str(e), "ERROR", "PUBLIC")


def _get_active_project_snapshot(ctrl: AppController) -> tuple[str | None, list[str]]:
    active_project = st.session_state.get("active_project")

    if not active_project or active_project == "(no projects yet)":
        return None, []

    try:
        embedded_info = ctrl.get_embedded_files(active_project)
    except Exception:
        return active_project, []

    if embedded_info.get("success"):
        return active_project, list(embedded_info.get("files", []))

    return active_project, []


def _collect_memory_gui_state(memory_manager: MemoryManager) -> list[dict[str, Any]]:
    gui_state: list[dict[str, Any]] = []

    for record in memory_manager.records:
        tag_key = f"memory_tag_{record.record_id}"
        keywords_key = f"memory_user_keywords_{record.record_id}"

        tag = st.session_state.get(tag_key, record.tag)
        user_keywords_text = st.session_state.get(
            keywords_key,
            ", ".join(record.user_keywords),
        )

        gui_state.append(
            {
                "record_id": record.record_id,
                "tag": tag,
                "user_keywords": _parse_user_keywords(user_keywords_text),
            }
        )

    return gui_state


def _parse_user_keywords(text: str) -> list[str]:
    raw_items = str(text or "").replace("\n", ",").split(",")

    result: list[str] = []
    seen: set[str] = set()

    for item in raw_items:
        keyword = item.strip()
        if not keyword:
            continue

        key = keyword.lower()
        if key in seen:
            continue

        result.append(keyword)
        seen.add(key)

    return result


def do_retrieval() -> None:
    """Retrieval button callback."""
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
            return

        top_k = int(st.session_state.get("retrieval_top_k", 100))
        use_retrieval_splade = bool(st.session_state.get("use_retrieval_splade", False))

        sp = ctrl.run_retrieval(
            sp,
            project_name,
            top_k,
            use_retrieval_splade=use_retrieval_splade,
        )
        sp.compose_prompt_ready()

        st.session_state.sp = sp
        st.session_state.sp_rtv = copy.deepcopy(sp)
        st.session_state["super_prompt_text"] = sp.prompt_ready

    except Exception as e:
        st.error(str(e))


def do_reranker() -> None:
    """ReRanker button callback."""
    try:
        ctrl: AppController = st.session_state.controller
        sp: SuperPrompt = st.session_state.sp

        use_reranking_colbert = bool(st.session_state.get("use_reranking_colbert", False))

        sp = ctrl.run_reranker(
            sp,
            use_reranking_colbert=use_reranking_colbert,
        )
        sp.compose_prompt_ready()

        st.session_state.sp = sp
        st.session_state.sp_rrk = copy.deepcopy(sp)
        st.session_state["super_prompt_text"] = sp.prompt_ready

    except Exception as e:
        st.error(str(e))


def do_a3_nli_gate() -> None:
    """A3 button callback."""
    try:
        ctrl: AppController = st.session_state.controller
        sp: SuperPrompt = st.session_state.sp

        sp = ctrl.run_a3(sp)

        st.session_state.sp = sp
        st.session_state.sp_a3 = copy.deepcopy(sp)
        st.session_state["super_prompt_text"] = sp.prompt_ready

    except Exception as e:
        st.error(str(e))


def do_a4_condenser() -> None:
    """A4 button callback."""
    try:
        ctrl: AppController = st.session_state.controller
        sp: SuperPrompt = st.session_state.sp

        sp = ctrl.run_a4(sp)
        sp.compose_prompt_ready()

        st.session_state.sp = sp
        st.session_state.sp_a4 = copy.deepcopy(sp)
        st.session_state["super_prompt_text"] = sp.prompt_ready

    except Exception as e:
        st.error(str(e))


def do_create_project() -> None:
    """Create Project form callback."""
    try:
        ctrl: AppController = st.session_state.controller
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


def do_add_files() -> None:
    """Add Files form callback."""
    try:
        ctrl: AppController = st.session_state.controller

        result = ctrl.import_files_to_project(
            st.session_state.get("add_files_project", ""),
            uploaded_files=st.session_state.get("ingestion_uploaded_files"),
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