"""
ToolDispatcher
==============
Detects `calc:` / `py:` prefixes in the user prompt and routes to the tool.
"""
from typing import Tuple
from ragstream.tooling.registry import ToolRegistry

class ToolDispatcher:
    """Front controller for local tool execution."""
    def maybe_dispatch(self, prompt: str) -> Tuple[str, str]:
        """
        Returns (tool_output, stripped_prompt).
        If no tool prefix detected, tool_output = "".
        """
        return ("", prompt)
