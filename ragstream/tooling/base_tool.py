"""
BaseTool
========
Abstract base class for any local executable helper (math, python, shell …).
"""
class BaseTool:
    """Every concrete tool must implement `__call__`."""
    name: str = "base"

    def __call__(self, instruction: str) -> str:
        """Execute the tool and return textual output (dummy)."""
        return "<tool-output>"
