"""
AppController
=============
Glue code between Streamlit UI, retrieval pipeline, tooling dispatcher, and
LLM client.  Keeps session state and orchestrates the end-to-end flow.
"""
from typing import List
from ragstream.retrieval.retriever import Retriever, DocScore
from ragstream.tooling.dispatcher import ToolDispatcher
from ragstream.orchestration.prompt_builder import PromptBuilder
from ragstream.orchestration.llm_client import LLMClient

class AppController:
    """High-level façade used by the UI callbacks."""
    def __init__(self) -> None:
        self.retriever = Retriever()
        self.dispatcher = ToolDispatcher()
        self.prompt_builder = PromptBuilder()
        self.llm_client = LLMClient()

    def run_query(self, question: str) -> str:
        """Full workflow returning final answer (dummy)."""
        return "ANSWER"
