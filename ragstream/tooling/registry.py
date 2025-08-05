"""
ToolRegistry
============
Discovers all subclasses of BaseTool and exposes them via `.get(name)`.
"""
from typing import Dict, Type
from ragstream.tooling.base_tool import BaseTool

class ToolRegistry:
    """Keeps a mapping `name -> tool_instance`."""
    _registry: Dict[str, BaseTool] = {}

    @classmethod
    def discover(cls) -> None:
        """Populate registry (dummy)."""
        return

    @classmethod
    def get(cls, name: str) -> BaseTool:
        """Return tool instance or raise KeyError."""
        return cls._registry[name]
