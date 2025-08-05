"""
Embedder
========
Wraps SentenceTransformers to convert text chunks into dense vectors.
"""
from typing import List

class Embedder:
    """High-level embedding interface."""
    def embed(self, texts: List[str]) -> List[list[float]]:
        """Return list of embedding vectors (dummy)."""
        return []
