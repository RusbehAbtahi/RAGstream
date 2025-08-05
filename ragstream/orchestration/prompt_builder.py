"""
PromptBuilder
=============
Assembles the final system prompt from user question, retrieved context and
optional tool output.  Handles token limits and truncation.
"""
from typing import List, Optional

class PromptBuilder:
    """Template-driven prompt composer."""
    def build(self, question: str, ctx: List[str], tool: Optional[str] = None) -> str:
        """Return composed prompt (dummy)."""
        return "PROMPT"
