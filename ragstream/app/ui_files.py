# ragstream/app/ui_files.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import pandas as pd
import streamlit as st

from ragstream.app.ui_actions_files import (
    do_files_confirm_delete_history,
    do_files_create_history,
    do_files_delete_request,
    do_files_load_history,
    do_files_rename_history,
)


TABLE_STRIPE_COLOR = "#E2FBD8"

# Same visual width as: [New memory name] [New]
# The remaining right side stays empty.
CONTENT_COLS = [3.0, 4.5]


def render_files_tab() -> None:
    """Server-side FILES tab for memory history management."""
    st.markdown("## Files")

    memory_manager = st.session_state.memory_manager
    histories = memory_manager.list_histories()

    _repair_selected_file_id(histories)
    _render_new_memory_area()

    if not histories:
        st.info("No memory histories found.")
        _render_status()
        return

    _render_history_table(histories)

    selected_file_id = str(st.session_state.get("files_selected_file_id", "") or "").strip()
    selected = _history_by_file_id(histories, selected_file_id)

    st.markdown("### Selected Memory History")

    if not selected:
        st.info("Select one memory history from the table above.")
        _render_status()
        return

    _render_selected_card(selected)
    _render_action_area(selected)
    _render_status()


def _render_new_memory_area() -> None:
    """Render compact New Memory action."""
    st.markdown("### New Memory")

    name_col, btn_col, gap_col = st.columns([2.2, 0.8, 4.5], gap="small")

    with name_col:
        st.text_input(
            "New memory name",
            key="files_new_memory_title",
            placeholder="New memory name",
            label_visibility="collapsed",
        )

    with btn_col:
        if st.button("New", key="btn_files_new", use_container_width=True):
            do_files_create_history()

    with gap_col:
        st.empty()


def _render_history_table(histories: list[dict]) -> None:
    """
    Render memory histories as a selectable dataframe.

    User selects one row in the table, then uses the action buttons below.
    """
    st.markdown("### Memory Histories")

    rows: list[dict[str, str]] = []

    for item in histories:
        rows.append(
            {
                "Filename": str(item.get("filename_ragmem", "") or ""),
                "Created": str(item.get("created_at_utc", "") or ""),
                "Updated": str(item.get("updated_at_utc", "") or ""),
                "Records": str(int(item.get("record_count", 0) or 0)),
                "_file_id": str(item.get("file_id", "") or ""),
            }
        )

    df = pd.DataFrame(rows)

    if df.empty:
        st.info("No memory histories found.")
        return

    visible_df = df[["Filename", "Created", "Updated", "Records"]].copy()
    styled_df = visible_df.style.apply(_stripe_table_rows, axis=1)

    table_col, spacer_col = st.columns(CONTENT_COLS, gap="small")

    with table_col:
        event = st.dataframe(
            styled_df,
            key="files_history_table",
            use_container_width=True,
            hide_index=True,
            height=320,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "Filename": st.column_config.TextColumn(
                    "Filename",
                    width="medium",
                ),
                "Created": st.column_config.TextColumn(
                    "Created",
                    width="small",
                ),
                "Updated": st.column_config.TextColumn(
                    "Updated",
                    width="small",
                ),
                "Records": st.column_config.TextColumn(
                    "Records",
                    width="small",
                ),
            },
        )

    with spacer_col:
        st.empty()

    selected_rows = _get_selected_rows(event)
    if selected_rows:
        row_index = int(selected_rows[0])
        if 0 <= row_index < len(df):
            st.session_state["files_selected_file_id"] = str(df.iloc[row_index]["_file_id"])


def _render_selected_card(selected: dict) -> None:
    """Render compact selected-file information."""
    filename = str(selected.get("filename_ragmem", "") or "")
    file_id = str(selected.get("file_id", "") or "")
    created = str(selected.get("created_at_utc", "") or "")
    updated = str(selected.get("updated_at_utc", "") or "")
    records = int(selected.get("record_count", 0) or 0)

    card_col, gap_col = st.columns(CONTENT_COLS, gap="small")

    with card_col:
        st.markdown(
            f"""
            <div style="
                border:1px solid #d8d8d8;
                border-radius:0.55rem;
                padding:0.65rem 0.85rem;
                background-color:#fafafa;
            ">
                <div style="font-weight:700; font-size:1.02rem;">{filename}</div>
                <div style="font-size:0.84rem; color:#555;">file_id: {file_id}</div>
                <div style="font-size:0.84rem; color:#555;">created: {created}</div>
                <div style="font-size:0.84rem; color:#555;">updated: {updated}</div>
                <div style="font-size:0.84rem; color:#555;">records: {records}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with gap_col:
        st.empty()


def _render_action_area(selected: dict) -> None:
    """Render Load / New / Rename / Delete actions for the selected history."""
    file_id = str(selected.get("file_id", "") or "").strip()

    rename_key = f"files_rename_title_{file_id}"
    delete_pending_key = f"files_delete_pending_{file_id}"
    delete_confirm_key = f"files_delete_confirm_text_{file_id}"

    st.markdown("### Actions")

    action_col, gap_col = st.columns(CONTENT_COLS, gap="small")

    with action_col:
        if st.button("Load", key=f"btn_files_load_{file_id}", use_container_width=True):
            do_files_load_history()

        rename_text_col, rename_btn_col = st.columns([2.1, 1.0], gap="small")
        with rename_text_col:
            st.text_input(
                "Rename field",
                key=rename_key,
                placeholder="New name",
                label_visibility="collapsed",
            )
        with rename_btn_col:
            if st.button("Rename", key=f"btn_files_rename_{file_id}", use_container_width=True):
                do_files_rename_history()

        if not st.session_state.get(delete_pending_key, False):
            if st.button("Delete", key=f"btn_files_delete_request_{file_id}", use_container_width=True):
                do_files_delete_request()
        else:
            st.warning('Type "delete" to confirm deletion.')
            confirm_text_col, confirm_btn_col = st.columns([2.1, 1.0], gap="small")

            with confirm_text_col:
                st.text_input(
                    "Delete confirmation",
                    key=delete_confirm_key,
                    placeholder='type "delete"',
                    label_visibility="collapsed",
                )

            with confirm_btn_col:
                if st.button(
                    "Confirm Delete",
                    key=f"btn_files_confirm_delete_{file_id}",
                    use_container_width=True,
                ):
                    do_files_confirm_delete_history()

    with gap_col:
        st.empty()


def _render_status() -> None:
    """Render latest FILES action status."""
    status = st.session_state.get("files_action_status")
    if not status:
        return

    status_col, gap_col = st.columns(CONTENT_COLS, gap="small")

    with status_col:
        if status.get("type") == "success":
            st.success(status.get("message", ""))
        else:
            st.error(status.get("message", ""))

    with gap_col:
        st.empty()


def _repair_selected_file_id(histories: list[dict]) -> None:
    """
    Keep selected file_id only if it still exists.

    Important:
    - Do not auto-select newest file.
    - User selection must be explicit.
    """
    selected_file_id = str(st.session_state.get("files_selected_file_id", "") or "").strip()
    if not selected_file_id:
        return

    existing_ids = {str(item.get("file_id", "") or "").strip() for item in histories}
    if selected_file_id not in existing_ids:
        st.session_state["files_selected_file_id"] = ""


def _history_by_file_id(histories: list[dict], file_id: str) -> dict | None:
    clean_file_id = str(file_id or "").strip()

    for item in histories:
        if str(item.get("file_id", "") or "").strip() == clean_file_id:
            return item

    return None


def _get_selected_rows(event: object) -> list[int]:
    """Extract selected dataframe row indexes from Streamlit event object."""
    try:
        rows = event.selection.rows
    except Exception:
        return []

    if not rows:
        return []

    return [int(row) for row in rows]


def _stripe_table_rows(row: pd.Series) -> list[str]:
    """Apply soft alternating row colors."""
    color = TABLE_STRIPE_COLOR if int(row.name) % 2 == 1 else "white"
    return [f"background-color: {color}" for _ in row]