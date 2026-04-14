# retriever_splade.py
# -*- coding: utf-8 -*-
"""
retriever_splade.py

Purpose:
    SPLADE-based retrieval backend extracted out of retriever.py.

Scope of this file:
    - Receive neutral retrieval inputs only:
        * project_name
        * query_pieces
        * top_k
        * optional candidate_ids
    - Open the active project's SPLADE document store.
    - Compare stored sparse chunk representations against all query-piece
      sparse representations.
    - Aggregate per-chunk similarities with p-norm averaging.
    - Return ranked retrieval rows to the top-level Retriever stage.

Important design rule:
    - This class does NOT know SuperPrompt.
    - This class does NOT hydrate chunk text from doc_raw.
    - This class does NOT write anything back into the pipeline state.
    - It only performs the SPLADE-based ranking backend.

Design goal:
    Keep the same programming culture and return contract as RetrieverEmb
    wherever possible.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from ragstream.ingestion.splade_embedder import SpladeEmbedder
from ragstream.ingestion.vector_store_splade import VectorStoreSplade

# Ranked row returned to Retriever:
# (chunk_id, retrieval_score, metadata)
RankedRow = Tuple[str, float, Dict[str, Any]]

# Fallback number of chunks to keep if the caller gives no valid top-k.
DEFAULT_TOP_K = 100

# Agreed retrieval aggregation constant:
# p-value for p-norm averaging across query pieces.
DEFAULT_P_NORM = 10


class RetrieverSplade:
    """
    SPLADE-based retrieval backend.

    Design:
    - Receive neutral retrieval inputs only.
    - Perform sparse retrieval ranking.
    - Return ranked rows to the top-level Retriever.
    """

    def __init__(self, *, splade_root: str, splade_embedder: SpladeEmbedder) -> None:
        """
        Initialize the SPLADE retrieval backend.

        Args:
            splade_root:
                Absolute path to the splade_db root folder.
            splade_embedder:
                Shared SpladeEmbedder instance used to encode the query pieces.
        """
        self.splade_root = Path(splade_root).resolve()
        self.splade_embedder = splade_embedder

    def run(
        self,
        *,
        project_name: str,
        query_pieces: List[str],
        top_k: int,
        candidate_ids: List[str] | None = None,
    ) -> List[RankedRow]:
        """
        Execute the SPLADE-based retrieval backend.

        Args:
            project_name:
                Active project name selected in the GUI.
            query_pieces:
                Overlapping retrieval query pieces prepared by the top-level Retriever.
            top_k:
                Number of rows to keep after ranking when running in global-search mode.
            candidate_ids:
                Optional fixed candidate set. When provided, SPLADE scores exactly
                these IDs and does not perform its own independent top-k search.

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
            raise ValueError("RetrieverSplade.run: project_name must not be empty")

        if not self.splade_root.exists():
            raise FileNotFoundError(
                f"RetrieverSplade.run: splade_root does not exist: {self.splade_root}"
            )

        project_db_dir = self.splade_root / project_name
        if not project_db_dir.exists():
            raise FileNotFoundError(
                f"RetrieverSplade.run: active project SPLADE DB does not exist: {project_db_dir}"
            )

        if not query_pieces:
            return []

        k = int(top_k) if int(top_k) > 0 else DEFAULT_TOP_K

        store = VectorStoreSplade(persist_dir=str(project_db_dir))

        doc_vectors: Dict[str, Dict[str, float]] = store.index
        meta_store: Dict[str, Dict[str, Any]] = getattr(store, "_meta_store", {})

        if len(doc_vectors) == 0:
            return []

        query_vectors = self.splade_embedder.embed_queries(query_pieces)
        if len(query_vectors) == 0:
            return []

        target_ids: List[str]
        use_fixed_candidates = candidate_ids is not None

        if use_fixed_candidates:
            seen: set[str] = set()
            target_ids = []

            for chunk_id in candidate_ids or []:
                cid = str(chunk_id).strip()
                if not cid:
                    continue
                if cid in seen:
                    continue
                seen.add(cid)
                target_ids.append(cid)

            if len(target_ids) == 0:
                return []

            missing_ids = [cid for cid in target_ids if cid not in doc_vectors]
            if missing_ids:
                preview = ", ".join(missing_ids[:10])
                suffix = " ..." if len(missing_ids) > 10 else ""
                raise RuntimeError(
                    "RetrieverSplade.run: candidate_ids are missing in the active SPLADE store. "
                    f"Missing {len(missing_ids)} id(s): {preview}{suffix}"
                )
        else:
            target_ids = list(doc_vectors.keys())

        rows: List[RankedRow] = []

        p = DEFAULT_P_NORM

        for chunk_id in target_ids:
            doc_vec = doc_vectors[chunk_id]
            per_piece_scores: List[float] = []

            for query_vec in query_vectors:
                sim = self._dot_sparse(doc_vec, query_vec)
                per_piece_scores.append(float(sim))

            if len(per_piece_scores) == 0:
                aggregated_score = 0.0
            else:
                sims_pos = [max(0.0, float(s)) for s in per_piece_scores]
                aggregated_score = (
                    sum(pow(s, p) for s in sims_pos) / float(len(sims_pos))
                ) ** (1.0 / p)

            meta = meta_store.get(chunk_id, {})
            rows.append(
                (
                    str(chunk_id),
                    float(aggregated_score),
                    dict(meta),
                )
            )

        # Deterministic sort:
        # 1) higher score first
        # 2) stable fallback by chunk_id
        rows.sort(key=lambda row: (-row[1], row[0]))

        if use_fixed_candidates:
            return rows

        return rows[: min(k, len(rows))]

    @staticmethod
    def _dot_sparse(left: Dict[str, float], right: Dict[str, float]) -> float:
        """
        Dot product over sparse dicts.

        Iterate over the smaller dict for efficiency.
        """
        if len(left) > len(right):
            left, right = right, left

        score = 0.0
        for key, value in left.items():
            score += float(value) * float(right.get(key, 0.0))
        return score