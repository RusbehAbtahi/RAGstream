# ragstream/textforge/RagLog.py
# -*- coding: utf-8 -*-
"""
RagLog
======

Project-level TextForge preset/builder layer.

Responsibilities:
- Create the fixed 4-sink RAGstream logging setup.
- Keep the 5 core classes neutral.
- Decide sink order, sink flags, paths, accepted severities, and accepted sensitivities.
- Provide ready-made logger factories:
    LogALL()
    LogNoGUI()
    LogConf()

Fixed sink order:
    sinks[0] = Sink0_Archive
    sinks[1] = File_PublicRun
    sinks[2] = CliRuntimeSink
    sinks[3] = GuiPublicSink
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from ragstream.textforge.TextForge import TextForge
from ragstream.textforge.TextSink import TextSink
from ragstream.textforge.FileSink import FileSink
from ragstream.textforge.CliSink import CliSink
from ragstream.textforge.GUISink import GuiSink


# ---------------------------------------------------------------------
# Fixed catalogs / presets used by RagLog
# ---------------------------------------------------------------------

ALL_TYPES: list[str] = [
    "TRACE",
    "DEBUG",
    "INFO",
    "WARN",
    "ERROR",
    "FATAL",
]

RUNTIME_TYPES: list[str] = [
    "INFO",
    "WARN",
    "ERROR",
    "FATAL",
]

ARCHIVE_SENSITIVITIES: list[str] = [
    "PUBLIC",
    "INTERNAL",
    "CONFIDENTIAL",
]

PUBLIC_ONLY: list[str] = [
    "PUBLIC",
]

CLI_NORMAL_SENSITIVITIES: list[str] = [
    "PUBLIC",
    "INTERNAL",
]

CLI_DEVELOPER_SENSITIVITIES: list[str] = [
    "PUBLIC",
    "INTERNAL",
    "CONFIDENTIAL",
]


# ---------------------------------------------------------------------
# 1) CreateSinks
# ---------------------------------------------------------------------

def CreateSinks(
    mode: str = "normal",
    session_state: Optional[object] = None,
    gui_key: str = "textforge_gui_log",
    log_root: Optional[str | Path] = None,
    public_run_rotation_size: int = 10_000_000,
    archive_rotation_size: int = 50_000_000,
) -> list[TextSink]:
    """
    Create the fixed 4 sinks in the agreed order.

    Sink order:
        sinks[0] = Sink0_Archive
        sinks[1] = File_PublicRun
        sinks[2] = CliRuntimeSink
        sinks[3] = GuiPublicSink

    Args:
        mode:
            "normal" or "developer".

            normal:
                CLI accepts INFO/WARN/ERROR/FATAL and PUBLIC/INTERNAL.

            developer:
                CLI accepts TRACE/DEBUG/INFO/WARN/ERROR/FATAL and
                PUBLIC/INTERNAL/CONFIDENTIAL.

        session_state:
            Streamlit st.session_state or compatible mapping.
            If None, RagLog tries to use streamlit.session_state.
            If Streamlit is not available, a small internal dict is used.

        gui_key:
            Key used by GuiSink, normally "textforge_gui_log".

        log_root:
            Root folder for logs.
            Default:
                <project-root>/data/logs

        public_run_rotation_size:
            Rotation size for the public readable log.
            Option:
                increase for fewer rotated files.
                decrease for smaller files.

        archive_rotation_size:
            Rotation size for the full archive log.
            Option:
                archive can be larger because it records much more.

    Returns:
        list[TextSink]:
            The four configured sink objects.
    """

    if mode not in {"normal", "developer"}:
        raise ValueError("mode must be 'normal' or 'developer'.")

    # RagLog.py lives in:
    #   <project-root>/ragstream/textforge/RagLog.py
    # Therefore parents[2] is <project-root>.
    project_root = Path(__file__).resolve().parents[2]

    if log_root is None:
        logs_root = project_root / "data" / "logs"
    else:
        logs_root = Path(log_root)

    today = date.today().isoformat()

    public_run_dir = logs_root / "public_run"
    archive_dir = logs_root / "archive"
    sqlite_dir = logs_root / "sqlite"

    public_run_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    sqlite_dir.mkdir(parents=True, exist_ok=True)

    public_run_path = public_run_dir / f"public_run_{today}.log"
    archive_path = archive_dir / f"archive_{today}.log"
    sqlite_path = sqlite_dir / "textforge_index.sqlite3"

    # ------------------------------------------------------------
    # GUI session_state resolution.
    #
    # In Streamlit:
    #     session_state should be st.session_state.
    #
    # Outside Streamlit:
    #     we fall back to a plain dict so that the sink can still exist.
    #     This keeps the fixed 4-sink structure intact.
    # ------------------------------------------------------------
    if session_state is None:
        try:
            import streamlit as st  # type: ignore
            session_state = st.session_state
        except Exception:
            session_state = {}

    # ------------------------------------------------------------
    # sinks[0] = Sink0_Archive
    #
    # Full archive:
    # - all severities
    # - PUBLIC / INTERNAL / CONFIDENTIAL
    # - SQLite active
    # - async active
    #
    # HIGHLY_CONFIDENTIAL is intentionally not accepted.
    # ------------------------------------------------------------
    sink0_archive = FileSink(
        path=str(archive_path),
        accept_types=ALL_TYPES,
        accept_sensitivities=ARCHIVE_SENSITIVITIES,
        rotation_size=archive_rotation_size,
        split_flag=True,
        b_sqlite=True,
        sqlite_path=str(sqlite_path),
        b_async=True,
        b_timestamp=True,
        b_prefix=True,
        b_suffix=False,
    )

    # ------------------------------------------------------------
    # sinks[1] = File_PublicRun
    #
    # Clean readable public runtime file:
    # - normal operational severities only
    # - PUBLIC only
    # - no SQLite
    # - synchronous
    # ------------------------------------------------------------
    sink1_public_run = FileSink(
        path=str(public_run_path),
        accept_types=RUNTIME_TYPES,
        accept_sensitivities=PUBLIC_ONLY,
        rotation_size=public_run_rotation_size,
        split_flag=True,
        b_sqlite=False,
        sqlite_path=None,
        b_async=False,
        b_timestamp=True,
        b_prefix=True,
        b_suffix=False,
    )

    # ------------------------------------------------------------
    # sinks[2] = CliRuntimeSink
    #
    # CLI is dynamic by startup mode.
    #
    # normal:
    #   quiet runtime terminal
    #
    # developer:
    #   detailed terminal including DEBUG/TRACE and CONFIDENTIAL
    #
    # Stream option:
    #   currently stdout for all CLI logs.
    #   If later wanted, this can be changed to stderr.
    # ------------------------------------------------------------
    if mode == "developer":
        cli_types = ALL_TYPES
        cli_sensitivities = CLI_DEVELOPER_SENSITIVITIES
    else:
        cli_types = RUNTIME_TYPES
        cli_sensitivities = CLI_NORMAL_SENSITIVITIES

    sink2_cli = CliSink(
        stream="stdout",
        accept_types=cli_types,
        accept_sensitivities=cli_sensitivities,
        b_timestamp=True,
        b_prefix=True,
        b_suffix=False,
    )

    # ------------------------------------------------------------
    # sinks[3] = GuiPublicSink
    #
    # GUI should remain clean:
    # - normal runtime severities only
    # - PUBLIC only
    # - newest message first by default
    #
    # display_mode options:
    #   "prepend" = newest on top
    #   "append"  = newest at bottom
    #   "replace" = only latest message
    # ------------------------------------------------------------
    sink3_gui = GuiSink(
        session_state=session_state,
        key=gui_key,
        accept_types=RUNTIME_TYPES,
        accept_sensitivities=PUBLIC_ONLY,
        display_mode="prepend",
        b_timestamp=True,
        b_prefix=True,
        b_suffix=False,
    )

    return [
        sink0_archive,
        sink1_public_run,
        sink2_cli,
        sink3_gui,
    ]


# ---------------------------------------------------------------------
# 2) CreateTextForge
# ---------------------------------------------------------------------

def CreateTextForge(
    text: str = "",
    type: str = "INFO",
    sensitivity: str = "PUBLIC",
    mode: str = "normal",
    session_state: Optional[object] = None,
    gui_key: str = "textforge_gui_log",
    log_root: Optional[str | Path] = None,
    b_enable: Optional[list[bool]] = None,
) -> TextForge:
    """
    Create one TextForge logger with all 4 sinks attached.

    Args:
        text:
            Initial/default text.

        type:
            Initial/default severity type.

        sensitivity:
            Initial/default sensitivity flag.

        mode:
            "normal" or "developer"; affects CLI sink.

        session_state:
            Streamlit session_state for GuiSink.

        gui_key:
            GUI session_state key.

        log_root:
            Optional custom logs root.

        b_enable:
            Enable map for the 4 sinks.
            If None, all 4 sinks are enabled.

    Returns:
        TextForge:
            Ready logger object.
    """

    sinks = CreateSinks(
        mode=mode,
        session_state=session_state,
        gui_key=gui_key,
        log_root=log_root,
    )

    if b_enable is None:
        b_enable = [True, True, True, True]

    return TextForge(
        text=text,
        type=type,
        sensitivity=sensitivity,
        sinks=sinks,
        b_enable=b_enable,
    )


# ---------------------------------------------------------------------
# 3) LogALL
# ---------------------------------------------------------------------

def LogALL(
    text: str = "",
    type: str = "INFO",
    sensitivity: str = "PUBLIC",
    mode: str = "normal",
    session_state: Optional[object] = None,
    gui_key: str = "textforge_gui_log",
    log_root: Optional[str | Path] = None,
) -> TextForge:
    """
    Create a logger with all 4 sinks enabled.

    b_enable:
        [1, 1, 1, 1]

    Active sinks:
        sinks[0] Sink0_Archive
        sinks[1] File_PublicRun
        sinks[2] CliRuntimeSink
        sinks[3] GuiPublicSink
    """

    logger = CreateTextForge(
        text=text,
        type=type,
        sensitivity=sensitivity,
        mode=mode,
        session_state=session_state,
        gui_key=gui_key,
        log_root=log_root,
        b_enable=[True, True, True, True],
    )

    return logger


# ---------------------------------------------------------------------
# 4) LogNoGUI
# ---------------------------------------------------------------------

def LogNoGUI(
    text: str = "",
    type: str = "INFO",
    sensitivity: str = "PUBLIC",
    mode: str = "normal",
    session_state: Optional[object] = None,
    gui_key: str = "textforge_gui_log",
    log_root: Optional[str | Path] = None,
) -> TextForge:
    """
    Create a logger with GUI disabled.

    b_enable:
        [1, 1, 1, 0]

    Active sinks:
        sinks[0] Sink0_Archive
        sinks[1] File_PublicRun
        sinks[2] CliRuntimeSink

    Disabled:
        sinks[3] GuiPublicSink

    Use case:
        Logging without disturbing the GUI.
    """

    logger = CreateTextForge(
        text=text,
        type=type,
        sensitivity=sensitivity,
        mode=mode,
        session_state=session_state,
        gui_key=gui_key,
        log_root=log_root,
        b_enable=[True, True, True, False],
    )

    return logger


# ---------------------------------------------------------------------
# 5) LogConf
# ---------------------------------------------------------------------

def LogConf(
    text: str = "",
    type: str = "INFO",
    sensitivity: str = "CONFIDENTIAL",
    mode: str = "normal",
    session_state: Optional[object] = None,
    gui_key: str = "textforge_gui_log",
    log_root: Optional[str | Path] = None,
) -> TextForge:
    """
    Create a logger for confidential developer-analysis material.

    b_enable:
        [1, 0, 0, 0]

    Active sinks:
        sinks[0] Sink0_Archive only

    Disabled:
        sinks[1] File_PublicRun
        sinks[2] CliRuntimeSink
        sinks[3] GuiPublicSink

    Default sensitivity:
        CONFIDENTIAL

    Use case:
        Full prompt, full SuperPrompt, retrieved chunks, LLM output,
        or similar protected developer-analysis material.

    Note:
        HIGHLY_CONFIDENTIAL should normally not be logged.
    """

    logger = CreateTextForge(
        text=text,
        type=type,
        sensitivity=sensitivity,
        mode=mode,
        session_state=session_state,
        gui_key=gui_key,
        log_root=log_root,
        b_enable=[True, False, False, False],
    )

    return logger