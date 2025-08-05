"""
StreamlitUI
===========
Defines the visible Streamlit components (prompt box, attention sliders,
results pane) and wires them to `AppController`.
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
        # (dummy UI skeleton – real widgets will be implemented later.)
        st.write("UI placeholder")
