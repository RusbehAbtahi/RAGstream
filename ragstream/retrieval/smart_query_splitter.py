# smart_query_splitter.py
# -*- coding: utf-8 -*-
"""
smart_query_splitter.py

Purpose:
    External query-splitting support functions for Retrieval.

Stage-1 refactor scope:
    - Keep the current linear overlapping query-splitting logic outside retriever.py.
    - Preserve the current behavior exactly as closely as possible.

Important note:
    The current splitting logic is still the existing deterministic linear
    windowing logic. Later, this file can be upgraded internally to a smarter
    query-splitting implementation (for example wtpsplit) without changing the
    top-level Retriever stage contract.
"""

from __future__ import annotations

from typing import List

from ragstream.ingestion.chunker import Chunker


def split_query_into_pieces(
    *,
    query_text: str,
    chunker: Chunker,
    chunk_size: int,
    overlap: int,
) -> List[str]:
    """
    Split the retrieval query into overlapping query pieces.

    Current Stage-1 behavior:
    - Reuse the same deterministic chunking idea as ingestion.
    - Preserve the current retrieval splitter behavior.
    - Return only the text pieces.

    Later upgrade path:
    - This function body can be replaced by a smarter splitter implementation
      without changing the top-level Retriever stage contract.
    """
    query_text = (query_text or "").strip()
    if not query_text:
        return []

    if chunker is None:
        raise ValueError("split_query_into_pieces: 'chunker' must not be None")

    if chunk_size <= 0:
        raise ValueError("split_query_into_pieces: chunk_size must be positive")

    if overlap < 0:
        raise ValueError("split_query_into_pieces: overlap must be non-negative")

    if overlap >= chunk_size:
        raise ValueError(
            "split_query_into_pieces: overlap must be smaller than chunk_size"
        )

    pieces = chunker.split(
        file_path="__prompt__",
        text=query_text,
        chunk_size=chunk_size,
        overlap=overlap,
    )

    return [chunk_text for _fp, chunk_text in pieces if (chunk_text or "").strip()]