"""
Retriever
=========
Coordinates vector search and reranking; controller handles Exact File Lock and eligibility pool.
"""
from typing import List

class DocScore:
    def __init__(self, doc_id: str, score: float) -> None:
        self.id = doc_id
        self.score = score

class Retriever:
    def retrieve(self, query: str, k: int = 10) -> List[DocScore]:
        return []
