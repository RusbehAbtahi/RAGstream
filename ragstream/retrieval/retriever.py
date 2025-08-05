"""
Retriever
=========
Coordinates vector search, attention weighting and reranking.
"""
from typing import List, Dict

class DocScore:
    """Lightweight value object pairing *doc_id* with *score*."""
    def __init__(self, doc_id: str, score: float) -> None:
        self.id = doc_id
        self.score = score

class Retriever:
    """End-to-end retrieval pipeline orchestrator."""
    def retrieve(self, query: str, k: int = 10) -> List[DocScore]:
        """Return reranked `DocScore` list (dummy)."""
        return []
