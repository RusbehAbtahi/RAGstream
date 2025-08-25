"""
SimpleLogger
============
Ultra-light wrapper around the built-in *logging* module so that the whole
code-base can depend on **one** unified logger without external config files.
"""
import logging

class SimpleLogger:
    """Minimal façade for standard logging (single responsibility: output)."""
    _logger = logging.getLogger("ragstream")
    if not _logger.handlers:
        _logger.setLevel(logging.INFO)
        _handler = logging.StreamHandler()
        _formatter = logging.Formatter("[%(asctime)s] %(levelname)s : %(message)s")
        _handler.setFormatter(_formatter)
        _logger.addHandler(_handler)

    @classmethod
    def log(cls, msg: str) -> None:
        """Write an *INFO* message (human-friendly)."""
        cls._logger.info(msg)

    @classmethod
    def error(cls, msg: str) -> None:
        """Write an *ERROR* message (something went wrong)."""
        cls._logger.error(msg)
