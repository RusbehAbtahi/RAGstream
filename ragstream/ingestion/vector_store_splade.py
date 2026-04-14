# -*- coding: utf-8 -*-
"""
vector_store_splade.py

Concrete sparse document store for RAGstream, backed by SpladeVectorStoreBase.

This is the sparse-side counterpart of vector_store_chroma.py.

Usage:
    store = VectorStoreSplade(persist_dir=".../data/splade_db/project1")
    store.add(ids=[...], vectors=[...], metadatas=[...])
    top_ids = store.query(vector=q_sparse, k=5)
    snap_dir = store.snapshot()
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .splade_vector_store_base import SpladeVectorStoreBase


class VectorStoreSplade(SpladeVectorStoreBase):
    """
    Local persistent sparse store for document chunks.

    Responsibilities:
      - Provide a ready-to-use sparse project store (default: "docs_sparse").
      - Reuse base add/query/snapshot/delete_where without policy overrides.
      - Offer the same tiny convenience helpers as VectorStoreChroma wherever
        possible, so both branches stay structurally parallel.
    """

    def __init__(self, persist_dir: str, index_name: str = "docs_sparse") -> None:
        super().__init__(persist_dir=persist_dir, index_name=index_name)

    @staticmethod
    def make_chunk_id(rel_path: str, sha256: str, chunk_idx: int) -> str:
        """
        Deterministic chunk id format shared with the dense branch.
        Example: "docs/Req.md::a1b2c3...::12"
        """
        return f"{rel_path}::{sha256}::{chunk_idx}"

    def delete_file_version(self, rel_path: str, sha256: str) -> int:
        """
        Remove all chunks belonging to one specific file content version.

        This mirrors VectorStoreChroma.delete_file_version(...).
        """
        ids = [
            chunk_id
            for chunk_id, meta in self._meta_store.items()
            if meta.get("path") == rel_path and meta.get("sha256") == sha256
        ]
        self._delete_ids(ids)
        return len(ids)

    @property
    def name(self) -> str:
        """
        Return the logical sparse index name.
        """
        return self.index_name

    @property
    def persist_root(self) -> Path:
        """
        Return the directory containing the on-disk sparse store.
        """
        return self.persist_path

    def count(self) -> int:
        """
        Return total number of stored sparse vectors.
        """
        return len(self._index)