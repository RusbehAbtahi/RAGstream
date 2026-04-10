# retriever_emb.py
# -*- coding: utf-8 -*-
"""
retriever_emb.py

Purpose:
    Current embedding-based retrieval backend extracted out of retriever.py.

Scope of this file:
    - Receive neutral retrieval inputs only:
        * project_name
        * query_pieces
        * top_k
    - Open the active project's Chroma document store.
    - Compare every stored chunk embedding against all query-piece embeddings.
    - Aggregate per-chunk similarities with p-norm averaging.
    - Return ranked retrieval rows to the top-level Retriever stage.

Important design rule:
    - This class does NOT know SuperPrompt.
    - This class does NOT hydrate chunk text from doc_raw.
    - This class does NOT write anything back into the pipeline state.
    - It only performs the current embedding-based ranking backend.

Stage-1 refactor goal:
    Preserve the current embedding-based retrieval behavior while moving the
    backend ranking logic out of retriever.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from ragstream.ingestion.embedder import Embedder
from ragstream.ingestion.vector_store_chroma import VectorStoreChroma

# Ranked row returned to Retriever:
# (chunk_id, retrieval_score, metadata)
RankedRow = Tuple[str, float, Dict[str, Any]]

# Fallback number of chunks to keep if the caller gives no valid top-k.
DEFAULT_TOP_K = 100

# Agreed retrieval aggregation constant:
# p-value for p-norm averaging across query pieces.
DEFAULT_P_NORM = 10


class RetrieverEmb:
    """
    Current embedding-based retrieval backend.

    Design:
    - Receive neutral retrieval inputs only.
    - Perform current dense retrieval ranking.
    - Return ranked rows to the top-level Retriever.
    """

    def __init__(self, *, chroma_root: str, embedder: Embedder) -> None:
        """
        Initialize the embedding-based retrieval backend.

        Args:
            chroma_root:
                Absolute path to the chroma_db root folder.
            embedder:
                Shared Embedder instance used to embed the query pieces.
        """
        self.chroma_root = Path(chroma_root).resolve()
        self.embedder = embedder

    def run(self, *, project_name: str, query_pieces: List[str], top_k: int) -> List[RankedRow]:
        """
        Execute the current embedding-based retrieval backend.

        Inputs:
            project_name:
                Active project selected in the GUI.
            query_pieces:
                Pre-split retrieval query pieces.
            top_k:
                Number of chunks to keep after ranking.

        Returns:
            Ranked retrieval rows in this format:
                [
                    (chunk_id, retrieval_score, metadata),
                    ...
                ]

        Error-handling rule:
        - Local validation belongs here, at the lower level.
        - The top-level Retriever.run(...) stays visually simple.
        """
        project_name = (project_name or "").strip()
        if not project_name:
            raise ValueError("RetrieverEmb.run: project_name must not be empty")

        if not self.chroma_root.exists():
            raise FileNotFoundError(
                f"RetrieverEmb.run: chroma_root does not exist: {self.chroma_root}"
            )

        project_db_dir = self.chroma_root / project_name
        if not project_db_dir.exists():
            raise FileNotFoundError(
                f"RetrieverEmb.run: active project Chroma DB does not exist: {project_db_dir}"
            )

        if not query_pieces:
            return []

        k = int(top_k) if int(top_k) > 0 else DEFAULT_TOP_K

        store = VectorStoreChroma(persist_dir=str(project_db_dir))
        raw = store.collection.get(include=["embeddings", "metadatas"])

        ids: List[str] = raw.get("ids", []) if raw else []
        metadatas: List[Dict[str, Any] | None] = raw.get("metadatas", []) if raw else []
        embeddings = raw.get("embeddings", []) if raw else []

        # embeddings may come back as a NumPy array, so never test it with
        # "if not embeddings". Use explicit length checks instead.
        if len(ids) == 0 or len(embeddings) == 0:
            return []

        if len(ids) != len(embeddings):
            raise RuntimeError(
                "RetrieverEmb.run: Chroma returned mismatched ids/embeddings lengths"
            )

        if len(metadatas) > 0 and len(metadatas) != len(ids):
            raise RuntimeError(
                "RetrieverEmb.run: Chroma returned mismatched ids/metadatas lengths"
            )

        query_vectors = self.embedder.embed(query_pieces)

        if len(query_vectors) == 0:
            return []

        A = np.asarray(embeddings, dtype=np.float32)    # stored chunks: [N, D]
        Q = np.asarray(query_vectors, dtype=np.float32) # query pieces:  [M, D]

        if A.ndim != 2 or Q.ndim != 2:
            raise RuntimeError(
                "RetrieverEmb.run: unexpected embedding dimensions returned by Chroma/OpenAI"
            )

        if A.shape[1] != Q.shape[1]:
            raise RuntimeError(
                "RetrieverEmb.run: stored vectors and query vectors have different dimensions"
            )

        # Normalize rows to compute cosine similarity as a matrix product.
        # Similarities shape: [N_chunks, M_query_pieces]
        A_norm = A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-12)
        Q_norm = Q / (np.linalg.norm(Q, axis=1, keepdims=True) + 1e-12)
        sims = A_norm @ Q_norm.T

        # p-mean aggregation over the query-piece axis.
        # Strongly favors the best match, but is still not pure max.
        p = DEFAULT_P_NORM
        sims_pos = np.clip(sims, 0.0, None)
        aggregated_scores = np.power(np.mean(np.power(sims_pos, p), axis=1), 1.0 / p)

        rows: List[RankedRow] = []
        for idx, chunk_id in enumerate(ids):
            meta = metadatas[idx] if (len(metadatas) > 0 and metadatas[idx] is not None) else {}
            rows.append(
                (
                    str(chunk_id),
                    float(aggregated_scores[idx]),
                    dict(meta),
                )
            )

        # Deterministic sort:
        # 1) higher score first
        # 2) stable fallback by chunk_id
        rows.sort(key=lambda row: (-row[1], row[0]))

        return rows[: min(k, len(rows))]