"""
SimpleLogger
============
Ultra-light façade for the standard logging module.
Use for ephemeral console messages only (no persistent logs by requirement).
"""
import logging

class SimpleLogger:
    _logger = logging.getLogger("ragstream")
    if not _logger.handlers:
        _logger.setLevel(logging.INFO)
        _h = logging.StreamHandler()
        _h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s : %(message)s"))
        _logger.addHandler(_h)

    @classmethod
    def log(cls, msg: str) -> None:
        cls._logger.info(msg)

    @classmethod
    def error(cls, msg: str) -> None:
        cls._logger.error(msg)
