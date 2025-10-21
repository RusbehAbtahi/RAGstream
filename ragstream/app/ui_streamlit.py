# -*- coding: utf-8 -*-
"""
RAGstream - ui_streamlit.py (Version 1 GUI Shell)

Purpose
-------
Single-file Streamlit UI that:
- Defines the overall 3-zone layout and routing.
- Implements top-level controls (Send/Cancel, Progress, Status, Transparency).
- Integrates with AppController if available; otherwise uses a safe stub.
- Calls out to support views (ui_sections/*) if present; provides inline fallbacks if not.

Notes
-----
- Plain text UI (no emojis/icons), compact and readable on a standard 1080p monitor.
- Advanced panels (History, Transparency, Debug, External Replies) are tucked into tabs/accordions.
- This file is intentionally self-contained to run without the support modules.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import streamlit as st

# -----------------------------------------------------------------------------
# Optional controller import (graceful fallback if backend is not wired yet)
# -----------------------------------------------------------------------------
try:
    from .controller import AppController  # type: ignore
except Exception:
    class AppController:  # type: ignore
        """Fallback controller to keep the UI runnable without backend."""
        def __init__(self) -> None:
            self.model = "gpt-4o"
        def handle(self, user_prompt: str, named_files: list[str], exact_lock: bool) -> str:
            return "[Controller stub] No backend yet. This is a placeholder response."
        def estimate_cost(self, tokens: int) -> float:
            return 0.0


# -----------------------------------------------------------------------------
# Optional support views (graceful fallbacks provided if imports fail)
# The real app can place these under ragstream/app/ui_sections/*.py
# -----------------------------------------------------------------------------
def _fallback_prompt_area(state: Dict[str, Any]) -> None:
    st.subheader("Prompt")
    state["prompt_text"] = st.text_area("Enter your prompt", value=state.get("prompt_text", ""), height=140)
    st.subheader("Super-Prompt Preview (optional)")
    state["super_prompt"] = st.text_area("Preview (editable before send)", value=state.get("super_prompt", ""), height=120)

def _fallback_model_agent_bar(state: Dict[str, Any]) -> None:
    st.subheader("Model & Agent Controls")
    state["model"] = st.selectbox("Model", options=["gpt-4o", "gpt-4o-mini", "ollama:llama3"], index=0)
    cols = st.columns(5)
    state["a1_on"] = cols[0].checkbox("A1", value=True)
    state["a2_on"] = cols[1].checkbox("A2", value=True)
    state["a3_on"] = cols[2].checkbox("A3", value=True)
    state["a4_on"] = cols[3].checkbox("A4", value=True)
    state["a5_on"] = cols[4].checkbox("A5", value=True)
    st.caption("Cost estimate is shown before send when available.")

def _fallback_file_eligibility(state: Dict[str, Any]) -> None:
    st.subheader("Files & Eligibility")
    st.caption("Per-file ON/OFF determines the Eligibility Pool for retrieval.")
    state.setdefault("files", ["docs/Req.md", "docs/Arch.md", "notes/plan.txt"])
    state.setdefault("files_on", {f: True for f in state["files"]})
    for f in state["files"]:
        state["files_on"][f] = st.checkbox(f"ON — {f}", value=state["files_on"].get(f, True), key=f"on_{f}")
    state["exact_lock"] = st.checkbox("Exact File Lock (skip retrieval, inject ❖ FILES only)", value=False)
    st.caption("Manifest is not wired yet in this fallback. Add ui_sections/file_eligibility.py to replace.")

def _fallback_prompt_shaper(state: Dict[str, Any]) -> None:
    with st.expander("Prompt Shaper (A2)"):
        state["intent"] = st.text_input("Intent", value=state.get("intent", "explain"))
        state["domain"] = st.text_input("Domain", value=state.get("domain", "software"))
        st.text_area("Headers / Roles (advisory)", value=state.get("headers", "H"), height=80)

def _fallback_history_panel(state: Dict[str, Any]) -> None:
    st.subheader("History Controls")
    state["history_k"] = st.slider("Recent turns (Layer-G, k)", 0, 10, state.get("history_k", 3))
    state["layer_e_budget"] = st.number_input("Layer-E token budget", min_value=0, max_value=5000, value=state.get("layer_e_budget", 500), step=50)
    state["mark_important"] = st.checkbox("Mark current turn important", value=state.get("mark_important", False))
    state["persist_history"] = st.checkbox("Persist History (Layer-E) ON/OFF", value=state.get("persist_history", True))
    if st.button("Clear Persisted Layer-E"):
        state["history_cleared"] = True
        st.success("Persisted Layer-E cleared (placeholder).")
    st.file_uploader("Synonym list import (optional)", type=["txt", "csv", "json"], accept_multiple_files=False)

def _fallback_external_reply_panel(state: Dict[str, Any]) -> None:
    st.subheader("External Reply Import")
    state["external_reply"] = st.text_area("Paste external LLM reply here", value=state.get("external_reply", ""), height=140)
    if st.button("Send to History"):
        st.success("External reply appended to history (placeholder).")

def _fallback_transparency_panel(state: Dict[str, Any]) -> None:
    st.subheader("Transparency")
    st.caption("Kept/Dropped with reasons; ❖ FILES and S_ctx views.")
    st.text_area("Kept/Dropped (reasons)", value=state.get("kept_dropped", ""), height=100)
    st.text_area("❖ FILES (injected)", value=state.get("files_block", ""), height=100)
    st.text_area("S_ctx (Facts / Constraints / Open Issues)", value=state.get("s_ctx", ""), height=120)

def _fallback_output_panel(state: Dict[str, Any]) -> None:
    st.subheader("Output")
    st.text_area("Assistant Response", value=state.get("answer_text", ""), height=240)
    cols = st.columns(2)
    if cols[0].button("Export with citations"):
        st.success("Exported (placeholder).")
    state["show_transparency"] = cols[1].checkbox("Show Transparency", value=state.get("show_transparency", False))

def _fallback_debug_panel(state: Dict[str, Any]) -> None:
    st.subheader("Debug / Diagnostics")
    state["debug_on"] = st.checkbox("Enable Debug Logger", value=state.get("debug_on", False))
    st.text_input("Session ID", value=state.get("session_id", "sess-0001"))
    st.text_area("Last Ingestion Stats", value=state.get("ingestion_stats", "files=0, chunks=0, bytes=0"), height=80)
    if st.button("Snapshot Vector DB"):
        st.info("Snapshot triggered (placeholder).")


# Try to import the real support modules; if missing, keep fallbacks
try:
    from .ui_sections.prompt_area import render as render_prompt_area  # type: ignore
except Exception:
    render_prompt_area = _fallback_prompt_area  # type: ignore

try:
    from .ui_sections.model_agent_bar import render as render_model_agent_bar  # type: ignore
except Exception:
    render_model_agent_bar = _fallback_model_agent_bar  # type: ignore

try:
    from .ui_sections.file_eligibility import render as render_file_eligibility  # type: ignore
except Exception:
    render_file_eligibility = _fallback_file_eligibility  # type: ignore

try:
    from .ui_sections.prompt_shaper import render as render_prompt_shaper  # type: ignore
except Exception:
    render_prompt_shaper = _fallback_prompt_shaper  # type: ignore

try:
    from .ui_sections.history_panel import render as render_history_panel  # type: ignore
except Exception:
    render_history_panel = _fallback_history_panel  # type: ignore

try:
    from .ui_sections.external_reply_panel import render as render_external_reply_panel  # type: ignore
except Exception:
    render_external_reply_panel = _fallback_external_reply_panel  # type: ignore

try:
    from .ui_sections.transparency_panel import render as render_transparency_panel  # type: ignore
except Exception:
    render_transparency_panel = _fallback_transparency_panel  # type: ignore

try:
    from .ui_sections.output_panel import render as render_output_panel  # type: ignore
except Exception:
    render_output_panel = _fallback_output_panel  # type: ignore

try:
    from .ui_sections.debug_panel import render as render_debug_panel  # type: ignore
except Exception:
    render_debug_panel = _fallback_debug_panel  # type: ignore


# -----------------------------------------------------------------------------
# UI helper: status bar and progress markers
# -----------------------------------------------------------------------------
def _status_bar(state: Dict[str, Any]) -> None:
    cols = st.columns(4)
    cols[0].markdown(f"**Model:** {state.get('model', 'gpt-4o')}")
    cols[1].markdown(f"**History:** {'Persist ON' if state.get('persist_history', True) else 'Persist OFF'}")
    cols[2].markdown(f"**Latency:** {state.get('latency_ms', '—')} ms")
    cols[3].markdown(f"**Cost Ceiling:** {state.get('cost_ceiling', '—')}")

def _progress_strip(state: Dict[str, Any]) -> None:
    st.caption("Stages: A0 FileScope • A1 DCI • A2 Shaper • Retrieval • Rerank • A3 NLI • A4 Condense • A5 Validate")


# -----------------------------------------------------------------------------
# Main UI class
# -----------------------------------------------------------------------------
class StreamlitUI:
    def __init__(self) -> None:
        if "state" not in st.session_state:
            st.session_state["state"] = {}
        self.state: Dict[str, Any] = st.session_state["state"]
        self.ctrl = AppController()

    def _send_clicked(self) -> None:
        prompt = self.state.get("prompt_text", "").strip()
        files_on = self.state.get("files_on", {})
        named_files = [p for p, on in files_on.items() if on]
        exact_lock = bool(self.state.get("exact_lock", False))

        if not prompt:
            st.warning("Please enter a prompt.")
            return

        # Pre-send cost gate (placeholder)
        self.state["cost_estimate"] = self.ctrl.estimate_cost(tokens=len(prompt) // 4) if hasattr(self.ctrl, "estimate_cost") else 0.0
        ceiling = self.state.get("cost_ceiling_value", None)
        if ceiling is not None and self.state["cost_estimate"] > ceiling:
            st.error("Cost ceiling exceeded. Adjust prompt or settings.")
            return

        # Call controller (or stub)
        answer = self.ctrl.handle(prompt, named_files, exact_lock)
        self.state["answer_text"] = answer

    def _cancel_clicked(self) -> None:
        st.info("Cancelled (placeholder).")

    def render(self) -> None:
        st.title("RAGstream")

        # Status / Safety banners
        _status_bar(self.state)
        _progress_strip(self.state)

        # Primary action bar
        bar = st.columns([1, 1, 2, 2, 2])
        if bar[0].button("Send"):
            self._send_clicked()
        if bar[1].button("Cancel/Retry"):
            self._cancel_clicked()
        self.state["cost_ceiling_value"] = bar[2].number_input("Cost ceiling (€)", min_value=0.0, value=float(self.state.get("cost_ceiling_value", 0.0)), step=0.10, help="Pre-send ceiling; set 0 to disable")
        self.state["latency_ms"] = bar[3].text_input("Latency hint (ms)", value=str(self.state.get("latency_ms", "")))
        self.state["transparency_toggle"] = bar[4].checkbox("Transparency ON/OFF", value=self.state.get("transparency_toggle", False))

        # Three-column layout
        left, center, right = st.columns([0.33, 0.47, 0.20])

        with left:
            render_prompt_area(self.state)
            render_model_agent_bar(self.state)
            render_file_eligibility(self.state)
            render_prompt_shaper(self.state)

        with center:
            render_output_panel(self.state)

        with right:
            tabs = st.tabs(["History", "Transparency", "External", "Debug"])
            with tabs[0]:
                render_history_panel(self.state)
            with tabs[1]:
                if self.state.get("show_transparency") or self.state.get("transparency_toggle"):
                    render_transparency_panel(self.state)
                else:
                    st.info("Transparency is OFF.")
            with tabs[2]:
                render_external_reply_panel(self.state)
            with tabs[3]:
                render_debug_panel(self.state)

        # Escalation (Human-in-the-Loop) panel if present
        if self.state.get("escalate", False):
            st.error(f"Escalation: {self.state.get('escalate_reason', 'unspecified')}")
            st.write("Suggested next steps: adjust eligibility, inject ❖ FILES, or retry.")

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
def run() -> None:
    ui = StreamlitUI()
    ui.render()

if __name__ == "__main__":
    run()
