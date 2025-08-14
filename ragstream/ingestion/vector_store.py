# -*- coding: utf-8 -*-
"""
VectorStore (router)
====================
On Windows (default): use pure NumPy exact-cosine backend (no native deps).
On non-Windows or when RAG_FORCE_CHROMA=1: use Chroma (PersistentClient).
"""

from __future__ import annotations
import os, sys
from typing import List, Dict

if sys.platform.startswith("win") and os.getenv("RAG_FORCE_CHROMA") != "1":
    # Windows default: native-free store
    from .vector_store_pure import VectorStorePure as VectorStore  # re-export
else:
    # Non-Windows (or forced): Chroma embedded client
    from chromadb import PersistentClient

    class VectorStore:
        def __init__(self, persist_dir: str) -> None:
            self.client = PersistentClient(path=persist_dir)
            self.collection = self.client.get_or_create_collection(
                name="rag_vectors",
                embedding_function=None  # embeddings are precomputed
            )

        def add(self, ids: List[str], vectors: List[List[float]], meta: List[Dict]) -> None:
            if not ids or not vectors:
                return
            self.collection.add(ids=ids, embeddings=vectors, metadatas=meta)

        def query(self, vector: List[float], k: int = 10) -> List[str]:
            res = self.collection.query(query_embeddings=[vector], n_results=k)
            return res.get("ids", [[]])[0]

        def snapshot(self, timestamp: str) -> None:
            # Chroma persists continuously; no-op here.
            return
