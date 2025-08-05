"""
Paths
=====
Centralises all on-disk locations for the project so that a single import
(`from ragstream.utils.paths import PATHS`) provides **typed** access to
directories used across ingestion, vector store, caching, and logging.
"""
from pathlib import Path
from typing import TypedDict

class _Paths(TypedDict):
    root:        Path
    data:        Path
    raw_docs:    Path
    chroma_db:   Path
    logs:        Path

PATHS: _Paths = {
    "root":      Path(__file__).resolve().parents[2],
    "data":      Path(__file__).resolve().parents[2] / "data",
    "raw_docs":  Path(__file__).resolve().parents[2] / "data" / "doc_raw",
    "chroma_db": Path(__file__).resolve().parents[2] / "data" / "chroma_db",
    "logs":      Path(__file__).resolve().parents[2] / "logs",
}
