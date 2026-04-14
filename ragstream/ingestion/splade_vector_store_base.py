# -*- coding: utf-8 -*-
"""
splade_vector_store_base.py

Shared, production-grade base class for a local SPLADE-backed sparse store.

Purpose:
    Provide the sparse-store analogue of chroma_vector_store_base.py, with the
    same public culture wherever possible:

        add(ids, vectors, metadatas) -> None
        query(vector, k=10, where=None) -> List[str]
        delete_where(where) -> None
        snapshot(timestamp=None) -> Path

Storage model:
    Local filesystem persistence under one project folder.
    The store persists:
        - sparse vectors by id
        - metadatas by id

Why local and simple:
    For your current architecture, SPLADE ingestion is the first step.
    Later retrieval can rescore a bounded set of chunk_ids efficiently from this
    store without requiring a full external search engine.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import os
import pickle
import shutil


SparseVector = Dict[str, float]


class SpladeVectorStoreBase:
    """
    Base implementation of a local persistent sparse store.

    Responsibilities:
      - Own one filesystem-backed sparse index bundle.
      - Provide deterministic add/query/delete/snapshot methods.
      - Offer policy hooks for subclasses, matching the Chroma base style.
    """

    def __init__(self, persist_dir: str, index_name: str) -> None:
        self.persist_path = Path(persist_dir)
        self.persist_path.mkdir(parents=True, exist_ok=True)

        self.index_name = index_name
        self._bundle_path = self.persist_path / f"{self.index_name}.pkl"

        self._index: Dict[str, SparseVector] = {}
        self._meta_store: Dict[str, Dict[str, Any]] = {}

        self._load()

    # ------------------------------------------------------------------
    # Public API (parallel to Chroma base)
    # ------------------------------------------------------------------

    def add(
        self,
        ids: List[str],
        vectors: List[SparseVector],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Upsert sparse vectors and metadatas into the local store.
        """
        if not ids or not vectors:
            return
        if len(ids) != len(vectors):
            raise ValueError("ids and vectors length mismatch")
        if metadatas is not None and len(metadatas) != len(ids):
            raise ValueError("metadatas length must match ids (or be None)")

        ids, vectors, metadatas = self._pre_add(ids, vectors, metadatas)

        metas = metadatas or [{} for _ in ids]

        for chunk_id, vector, meta in zip(ids, vectors, metas):
            self._index[chunk_id] = self._normalize_sparse_vector(vector)
            self._meta_store[chunk_id] = dict(meta)

        self._persist()
        self._post_add(ids, vectors, metadatas)

    def query(
        self,
        vector: SparseVector,
        k: int = 10,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Query the sparse store by sparse-vector dot product.

        Args:
            vector:
                Query sparse vector, same representation as stored doc vectors.
            k:
                Number of top results to return.
            where:
                Optional metadata filter, supporting:
                    - {"path": "...", "sha256": "..."}
                    - {"$and": [ ... ]}
                    - {"$or":  [ ... ]}
        """
        if not isinstance(vector, dict):
            raise ValueError("query vector must be a Dict[str, float]")

        k = max(1, int(k))
        vector, k, where = self._pre_query(vector, k, where)

        scored: List[tuple[str, float]] = []
        for chunk_id, doc_vec in self._index.items():
            meta = self._meta_store.get(chunk_id, {})

            if where and not self._metadata_matches(meta, where):
                continue

            score = self._dot_sparse(vector, doc_vec)
            scored.append((chunk_id, score))

        scored.sort(key=lambda row: (-row[1], row[0]))
        ids = [chunk_id for chunk_id, _score in scored[:k]]
        return self._post_query(ids, {"scored": scored})

    def delete_where(self, where: Dict[str, Any]) -> None:
        """
        Delete records by metadata filter.
        """
        if not where:
            return

        ids_to_delete = [
            chunk_id
            for chunk_id, meta in self._meta_store.items()
            if self._metadata_matches(meta, where)
        ]
        self._delete_ids(ids_to_delete)

    def snapshot(self, timestamp: Optional[str] = None) -> Path:
        """
        Create a filesystem snapshot of the persistent sparse store directory.
        """
        ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshots_dir = self.persist_path.parent / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        dst = snapshots_dir / f"{self.persist_path.name}_{ts}"

        shutil.copytree(self.persist_path, dst, dirs_exist_ok=False)
        return dst

    @property
    def index(self) -> Dict[str, SparseVector]:
        """
        Expose the underlying sparse vector mapping for advanced ops/debugging.
        """
        return self._index

    # ------------------------------------------------------------------
    # Hook methods (parallel to Chroma base)
    # ------------------------------------------------------------------

    def _pre_add(
        self,
        ids: List[str],
        vectors: List[SparseVector],
        metadatas: Optional[List[Dict[str, Any]]],
    ) -> tuple[List[str], List[SparseVector], Optional[List[Dict[str, Any]]]]:
        return ids, vectors, metadatas

    def _post_add(
        self,
        ids: List[str],
        vectors: List[SparseVector],
        metadatas: Optional[List[Dict[str, Any]]],
    ) -> None:
        return None

    def _pre_query(
        self,
        vector: SparseVector,
        k: int,
        where: Optional[Dict[str, Any]],
    ) -> tuple[SparseVector, int, Optional[Dict[str, Any]]]:
        return vector, k, where

    def _post_query(self, ids: List[str], raw_result: Dict[str, Any]) -> List[str]:
        return ids

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._bundle_path.exists():
            return

        with self._bundle_path.open("rb") as f:
            payload = pickle.load(f)

        self._index = dict(payload.get("index", {}))
        self._meta_store = dict(payload.get("metadatas", {}))

    def _persist(self) -> None:
        payload = {
            "version": "1",
            "index_name": self.index_name,
            "index": self._index,
            "metadatas": self._meta_store,
        }

        tmp_path = self._bundle_path.with_suffix(self._bundle_path.suffix + ".tmp")
        with tmp_path.open("wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)

        os.replace(str(tmp_path), str(self._bundle_path))

    def _delete_ids(self, ids: Iterable[str]) -> None:
        changed = False
        for chunk_id in ids:
            if chunk_id in self._index:
                del self._index[chunk_id]
                changed = True
            if chunk_id in self._meta_store:
                del self._meta_store[chunk_id]
                changed = True

        if changed:
            self._persist()

    @staticmethod
    def _normalize_sparse_vector(vector: SparseVector) -> SparseVector:
        """
        Remove zero entries and normalize key/value types.
        """
        normalized: SparseVector = {}
        for key, value in vector.items():
            fval = float(value)
            if fval != 0.0:
                normalized[str(key)] = fval
        return normalized

    @staticmethod
    def _dot_sparse(left: SparseVector, right: SparseVector) -> float:
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

    @classmethod
    def _metadata_matches(cls, metadata: Dict[str, Any], where: Dict[str, Any]) -> bool:
        """
        Minimal local filter engine compatible with the current ingestion needs.

        Supported:
            {"path": "..."}
            {"sha256": "..."}
            {"$and": [cond1, cond2, ...]}
            {"$or":  [cond1, cond2, ...]}
        """
        if not where:
            return True

        if "$and" in where:
            conditions = where["$and"]
            if not isinstance(conditions, list):
                raise ValueError("$and value must be a list")
            return all(cls._metadata_matches(metadata, cond) for cond in conditions)

        if "$or" in where:
            conditions = where["$or"]
            if not isinstance(conditions, list):
                raise ValueError("$or value must be a list")
            return any(cls._metadata_matches(metadata, cond) for cond in conditions)

        for key, expected in where.items():
            if key.startswith("$"):
                raise ValueError(f"Unsupported filter operator: {key}")
            if metadata.get(key) != expected:
                return False

        return True