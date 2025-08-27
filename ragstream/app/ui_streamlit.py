"""
StreamlitUI
===========
UI surface: prompt box, ON/OFF eligibility, Exact File Lock, agent toggles,
Super-Prompt preview, and transparency panel (ephemeral).
"""
import streamlit as st
from ragstream.app.controller import AppController

class StreamlitUI:
    def __init__(self) -> None:
        self.ctrl = AppController()

    def render(self) -> None:
        st.title("RAGstream")
        st.write("Prompt box, file ON/OFF, Exact File Lock, agent toggles, Super-Prompt preview")
