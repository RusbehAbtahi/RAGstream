"""
MathTool
========
Evaluates arithmetic expressions (safe subset) and returns the result.
"""
from ragstream.tooling.base_tool import BaseTool

class MathTool(BaseTool):
    """Protected SymPy evaluator."""
    name = "math"

    def __call__(self, instruction: str) -> str:
        """Parse and compute math expression (dummy)."""
        return "0"
