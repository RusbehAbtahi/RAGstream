"""
Reranker
========
Cross-encoder that re-orders the initially retrieved chunks.
"""
from typing import List

class Reranker:
    """Cross-encoder interface."""
    def rerank(self, ids: List[str], query: str) -> List[str]:
        """Return list of IDs sorted by relevance (dummy)."""
        return ids
