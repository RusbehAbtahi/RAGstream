# -*- coding: utf-8 -*-
"""
SimpleLogger — tiny logging facade for RAGstream.

Goal:
- Avoid crashes when code calls SimpleLogger.info/debug/warning/error.
- Keep it trivial: one class with classmethods, printing to stdout.
- Later you can swap this to Python's 'logging' without touching callers.
"""

from __future__ import annotations
import sys
import datetime
from typing import ClassVar


class SimpleLogger:
    """
    Very small logging helper.

    Usage:
        SimpleLogger.info("message")
        SimpleLogger.debug("details")
    """

    _enabled: ClassVar[bool] = True
    _prefix: ClassVar[str] = "RAGstream"

    @classmethod
    def _log(cls, level: str, msg: str) -> None:
        if not cls._enabled:
            return
        now = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"{cls._prefix} | {level.upper():5s} | {now} | {msg}"
        print(line, file=sys.stdout, flush=True)

    @classmethod
    def debug(cls, msg: str) -> None:
        cls._log("DEBUG", msg)

    @classmethod
    def info(cls, msg: str) -> None:
        cls._log("INFO", msg)

    @classmethod
    def warning(cls, msg: str) -> None:
        cls._log("WARN", msg)

    @classmethod
    def error(cls, msg: str) -> None:
        cls._log("ERROR", msg)

    @classmethod
    def set_enabled(cls, enabled: bool) -> None:
        cls._enabled = enabled

    @classmethod
    def set_prefix(cls, prefix: str) -> None:
        cls._prefix = prefix
