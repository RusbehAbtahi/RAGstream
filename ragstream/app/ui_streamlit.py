"""
StreamlitUI
===========
Defines the visible Streamlit components (prompt box, file ON/OFF controls,
Exact File Lock toggle, Prompt Shaper panel, agent toggles, Super-Prompt preview,
transparency/cost panes) and wires them to `AppController`.
"""
import streamlit as st
from ragstream.app.controller import AppController

class StreamlitUI:
    """Thin Streamlit wrapper – all logic stays in **AppController**."""
    def __init__(self) -> None:
        self.ctrl = AppController()

    def render(self) -> None:
        """Draws UI components and handles callbacks."""
        st.title("RAG Stream")
        st.write("UI placeholder (Prompt box, ON/OFF file checkboxes, Exact File Lock, agent toggles, Super-Prompt preview)")
