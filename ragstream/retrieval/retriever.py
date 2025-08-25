"""
Retriever
=========
Coordinates vector search and reranking. In the new design, per-file eligibility
is handled in the controller (Exact File Lock / ON-OFF pool) before retrieval.
"""
from typing import List

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
