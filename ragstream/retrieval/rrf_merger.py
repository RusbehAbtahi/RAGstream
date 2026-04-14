# rrf_merger.py
# -*- coding: utf-8 -*-
"""
rrf_merger.py

Purpose:
    Deterministic weighted Reciprocal Rank Fusion (RRF) helper.

Role:
    - Merge two ranked result lists in a neutral way.
    - Produce one fused ranked list.
    - Preserve metadata and attach neutral rank/score fields.

Important design rule:
    - This module is purely deterministic.
    - It does not know SuperPrompt.
    - It does not know dense / SPLADE semantics.
    - It does not hydrate chunk text.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# Ranked row contract shared with retriever.py / retriever_emb.py / retriever_splade.py
RankedRow = Tuple[str, float, Dict[str, Any]]

# Common practical default for RRF.
DEFAULT_RRF_K = 60


def rrf_merge(
    rows_a: List[RankedRow],
    rows_b: List[RankedRow],
    *,
    top_k: int | None = None,
    rrf_k: int = DEFAULT_RRF_K,
    weight_a: float = 1.0,
    weight_b: float = 1.0,
) -> List[RankedRow]:
    """
    Merge two ranked lists with weighted Reciprocal Rank Fusion.

    Args:
        rows_a:
            First ranked row list.
        rows_b:
            Second ranked row list.
        top_k:
            Optional final cutoff.
        rrf_k:
            RRF constant. Larger values flatten rank differences more.
        weight_a:
            Weight for the first ranked list.
        weight_b:
            Weight for the second ranked list.

    Returns:
        One fused ranked row list:
            [
                (chunk_id, fused_rrf_score, metadata_with_neutral_scores),
                ...
            ]
    """
    by_id: Dict[str, Dict[str, Any]] = {}

    for rank, (chunk_id, score, meta) in enumerate(rows_a, start=1):
        row = by_id.setdefault(str(chunk_id), {})
        row["meta"] = _merge_meta(row.get("meta"), meta)
        row["rank_a"] = int(rank)
        row["score_a"] = float(score)

    for rank, (chunk_id, score, meta) in enumerate(rows_b, start=1):
        row = by_id.setdefault(str(chunk_id), {})
        row["meta"] = _merge_meta(row.get("meta"), meta)
        row["rank_b"] = int(rank)
        row["score_b"] = float(score)

    fused_rows: List[RankedRow] = []

    for chunk_id, row in by_id.items():
        rank_a = row.get("rank_a")
        rank_b = row.get("rank_b")

        fused_score = 0.0
        if rank_a is not None:
            fused_score += float(weight_a) / float(rrf_k + int(rank_a))
        if rank_b is not None:
            fused_score += float(weight_b) / float(rrf_k + int(rank_b))

        meta = dict(row.get("meta") or {})

        if row.get("score_a") is not None:
            meta["score_a"] = float(row["score_a"])
        if row.get("score_b") is not None:
            meta["score_b"] = float(row["score_b"])

        if rank_a is not None:
            meta["rank_a"] = int(rank_a)
        if rank_b is not None:
            meta["rank_b"] = int(rank_b)

        meta["rrf_score"] = float(fused_score)

        fused_rows.append((str(chunk_id), float(fused_score), meta))

    # Deterministic sort:
    # 1) higher fused score first
    # 2) stable fallback by chunk_id
    fused_rows.sort(key=lambda row: (-row[1], row[0]))

    if top_k is None:
        return fused_rows

    k = int(top_k)
    if k <= 0:
        return fused_rows

    return fused_rows[: min(k, len(fused_rows))]


def _merge_meta(
    base_meta: Dict[str, Any] | None,
    new_meta: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """
    Merge metadata conservatively.

    Rule:
    - keep existing keys
    - add missing keys from the new metadata
    - do not silently overwrite existing values
    """
    merged = dict(base_meta or {})
    for key, value in dict(new_meta or {}).items():
        if key not in merged:
            merged[key] = value
    return merged