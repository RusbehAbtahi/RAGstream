"""
PyTool
======
Executes short Python snippets inside a restricted sandbox.
"""
from ragstream.tooling.base_tool import BaseTool

class PyTool(BaseTool):
    """RestrictedPython sandbox executor."""
    name = "py"

    def __call__(self, instruction: str) -> str:
        """Execute code and capture stdout (dummy)."""
        return "<py-result>"
