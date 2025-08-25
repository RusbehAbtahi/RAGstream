"""
Settings
========
Loads environment variables **once** at start-up so that every module accesses
configuration via Settings.get("OPENAI_API_KEY") instead of scattered os.getenv.
"""
import os
from typing import Any, Dict

class Settings:
    """
    Thin, immutable wrapper around `os.environ`.

    *Purpose*: centralise **all** config keys (API keys, flags, paths) and offer
    a single interface for default values & type-checking.
    """
    _CACHE: Dict[str, Any] = {}

    @classmethod
    def get(cls, key: str, default: Any | None = None) -> Any:
        """Return env value or *default*; cache the lookup."""
        if key not in cls._CACHE:
            cls._CACHE[key] = os.getenv(key, default)
        return cls._CACHE[key]
