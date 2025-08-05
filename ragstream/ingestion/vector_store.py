"""
VectorStore
===========
Thin façade around Chroma (or any future DB) handling persistence & snapshots.
"""
from typing import List

class VectorStore:
    """Stores embeddings and metadata; persists to disk."""
    def add(self, ids: List[str], vectors: List[list[float]], meta: List[dict]) -> None:
        """Insert or update vectors; no implementation yet."""
        return

    def query(self, vector: list[float], k: int = 10) -> List[str]:
        """Return top-k IDs (dummy)."""
        return []

    def snapshot(self, timestamp: str) -> None:
        """Create a timestamped backup of the DB on disk."""
        return
