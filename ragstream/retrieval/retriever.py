# -*- coding: utf-8 -*-
"""
Retriever
=========
Implements RET-01 (cosine top-k) and plugs optional RET-02 rerank stage.

Pipeline: query text --(Embedder)--> vector --(VectorStoreNP.query)--> ids
          [optional rerank] --> List[DocScore]

Notes
-----
* Current concrete vector store is NumPy-backed `VectorStoreNP` (exact cosine).
* The vector-store interface returns *ids*. To fulfill the requirement of
  returning cosine scores, we compute per-id cosine scores by reading the
  concrete store's in-memory arrays when available (VectorStoreNP exposes
  `_emb`, `_ids`, and `_id2idx`). This avoids changing the public interface.
  If such internals are unavailable (e.g. future Chroma backend), we still
  return `DocScore` with a neutral score of 0.0.
"""
from __future__ import annotations

from typing import List, Optional, Sequence
import math

import numpy as np

from ragstream.retrieval.doc_score import DocScore  # re-exported via this module
# Re-export so existing imports `from ragstream.retrieval.retriever import DocScore` keep working.
DocScore = DocScore  # noqa: F401  (module-level alias for compatibility)

from ragstream.ingestion.embedder import Embedder
from ragstream.ingestion.vector_store_np import VectorStoreNP

from ragstream.retrieval.reranker import Reranker
from ragstream.utils.paths import PATHS


class Retriever:
    """
    High-level retrieval orchestrator.

    Parameters
    ----------
    persist_dir : Optional[str]
        Directory for the NumPy vector store snapshots. Defaults to PATHS['vector_pkls'].
    embedder : Optional[Embedder]
        Custom embedder instance. If None, a default Embedder() is created.
    store : Optional[VectorStoreNP]
        Custom VectorStoreNP instance. If None, a default store is opened at `persist_dir`.
    reranker : Optional[Reranker]
        Optional cross-encoder reranker; if None, rerank step is skipped.
    """

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        embedder: Optional[Embedder] = None,
        store: Optional[VectorStoreNP] = None,
        reranker: Optional[Reranker] = None,
    ) -> None:
        self._persist_dir = persist_dir or str(PATHS["vector_pkls"])
        self._emb = embedder or Embedder()
        self._vs = store or VectorStoreNP(self._persist_dir)
        self._reranker = reranker or Reranker()

    # ---- public API ----
    def retrieve(self, query: str, k: int = 10, do_rerank: bool = True) -> List[DocScore]:
        """
        Retrieve top-k candidates for a query as `DocScore(id, score)`.

        Steps:
        1) Embed the query.
        2) Ask the vector store for candidate ids (k).
        3) Compute cosine scores for these ids (when store internals available).
        4) Optional rerank (order only), preserving computed scores.
        5) Return `DocScore` list (length ≤ k).

        Notes:
        - If no vectors are present, returns [].
        - If reranker is a no-op (current placeholder), order remains unchanged.
        """
        if not query or not isinstance(query, str):
            return []

        vecs = self._emb.embed([query])
        if not vecs:
            return []
        q = np.asarray(vecs[0], dtype=np.float32)
        if q.ndim != 1:
            q = q.reshape(-1)

        # Ask store for candidate ids (VectorStoreNP performs exact-cosine top-k by ids)
        ids: List[str] = self._vs.query(q.tolist(), k=k)  # type: ignore[arg-type]

        if not ids:
            return []

        # Compute cosine scores for the candidate ids when VectorStoreNP internals are available.
        scores = self._compute_cosine_scores(ids, q)

        # Optional rerank (RET-02). Current Reranker returns ids order; we preserve the computed scores.
        if do_rerank and self._reranker is not None:
            try:
                reranked_ids = self._reranker.rerank(ids, query)
                # Keep only ids we have scores for, preserve reranked order.
                ordered = [(i, scores.get(i, 0.0)) for i in reranked_ids if i in scores]
            except Exception:
                # Fail-safe: skip rerank on any error.
                ordered = [(i, scores.get(i, 0.0)) for i in ids]
        else:
            ordered = [(i, scores.get(i, 0.0)) for i in ids]

        # Truncate to k and wrap as DocScore
        ordered = ordered[: max(0, int(k))]
        return [DocScore(id=doc_id, score=float(sc)) for doc_id, sc in ordered]

    # ---- helpers ----
    def _compute_cosine_scores(self, ids: Sequence[str], q: np.ndarray) -> dict[str, float]:
        """
        Compute cosine similarity for a set of ids against query vector q using
        VectorStoreNP internal arrays when available. Falls back to 0.0 if not.
        """
        scores: dict[str, float] = {}
        # Use VectorStoreNP internals if present.
        emb = getattr(self._vs, "_emb", None)
        id2idx = getattr(self._vs, "_id2idx", None)
        if emb is None or id2idx is None:
            # No access to raw vectors (e.g., future Chroma backend).
            for _id in ids:
                scores[_id] = 0.0
            return scores

        A = np.asarray(emb, dtype=np.float32)  # (N, D)
        if A.ndim != 2 or A.size == 0:
            for _id in ids:
                scores[_id] = 0.0
            return scores

        qn = float(np.linalg.norm(q) + 1e-12)
        # Compute per-id cosine using the stored row corresponding to id.
        for _id in ids:
            idx = id2idx.get(_id, None)
            if idx is None:
                scores[_id] = 0.0
                continue
            v = A[idx]
            vn = float(np.linalg.norm(v) + 1e-12)
            sim = float(np.dot(v, q) / (vn * qn))
            # Clip to [-1, 1] to avoid tiny numerical overshoots.
            if sim > 1.0:
                sim = 1.0
            elif sim < -1.0:
                sim = -1.0
            scores[_id] = sim
        return scores
