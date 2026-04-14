# -*- coding: utf-8 -*-
"""
ingestion_manager.py

Purpose:
    Orchestrate deterministic document ingestion for RAGstream:
      scan → diff vs. manifest → chunk → embed → store → publish manifest

Scope:
    • This module focuses on the "documents" ingestion path only
      (conversation history layers are postponed as agreed).
    • Works with your existing loader, chunker, embedder, and Chroma vector store.
    • Also supports an optional parallel SPLADE sparse-ingestion branch.

Notes:
    • We compute file hashes from bytes on disk (compute_sha256), NOT from text.
    • Chunk IDs are stable: f"{rel_path}::{sha256}::{idx}" (matches your store helpers).
    • We only publish a new manifest after all target files in this run succeed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

# Local imports: existing dense components
from .loader import DocumentLoader
from .chunker import Chunker
from .embedder import Embedder
from .vector_store_chroma import VectorStoreChroma

# Added on 13.04.2026:
# Optional sparse SPLADE ingestion components.
from .splade_embedder import SpladeEmbedder
from .vector_store_splade import VectorStoreSplade

# Manifest utilities
from .file_manifest import (
    compute_sha256,
    load_manifest,
    diff as manifest_diff,
    publish_atomic,
    Record,
)


@dataclass(frozen=True)
class IngestionStats:
    """Aggregate numbers for quick reporting / testing."""
    files_scanned: int
    to_process: int
    unchanged: int
    tombstones: int
    chunks_added: int
    vectors_upserted: int
    deleted_old_versions: int
    deleted_tombstones: int
    published_manifest_path: str
    embedded_bytes: int

    # Added on 13.04.2026:
    # Split counters for the parallel dense + sparse branches.
    dense_vectors_upserted: int
    sparse_vectors_upserted: int
    dense_embedded_bytes: int
    sparse_embedded_bytes: int


class IngestionManager:
    """
    Coordinates the full ingestion pipeline for a given doc root.
    """

    def __init__(self, doc_root: str) -> None:
        """
        Args:
            doc_root: Absolute path to the "doc_raw" root folder.
        """
        self.doc_root = Path(doc_root).resolve()
        if not self.doc_root.exists():
            raise FileNotFoundError(f"doc_root does not exist: {self.doc_root}")
        if not self.doc_root.is_dir():
            raise NotADirectoryError(f"doc_root is not a directory: {self.doc_root}")

        # A loader is tied to a root; it returns absolute file paths + text for a subfolder
        self.loader = DocumentLoader(root=self.doc_root)

    def run(
        self,
        subfolder: str,
        store: VectorStoreChroma,
        chunker: Chunker,
        embedder: Embedder,
        manifest_path: str,
        *,
        sparse_store: VectorStoreSplade | None = None,
        sparse_embedder: SpladeEmbedder | None = None,
        chunk_size: int = 1200,
        overlap: int = 120,
        delete_old_versions: bool = True,
        delete_tombstones: bool = False,
    ) -> IngestionStats:
        """
        Execute a full ingestion cycle for one subfolder under doc_root.

        Dense branch is always active.
        Sparse SPLADE branch is active only if both sparse_store and sparse_embedder are provided.

        Returns:
            IngestionStats with useful counters.
        """
        manifest_path = str(Path(manifest_path).resolve())

        use_sparse = (sparse_store is not None) or (sparse_embedder is not None)
        if use_sparse and (sparse_store is None or sparse_embedder is None):
            raise ValueError(
                "Sparse ingestion requires both sparse_store and sparse_embedder."
            )

        # 1) Load documents (absolute path + raw text) from the subfolder.
        docs = self.loader.load_documents(subfolder)
        text_by_abs: Dict[str, str] = {abs_path: text for abs_path, text in docs}

        # 2) Build current Records by hashing files on disk (bytes).
        records_now: List[Record] = []
        for abs_path, _text in docs:
            ap = Path(abs_path)
            rel_path = ap.relative_to(self.doc_root).as_posix()
            sha = compute_sha256(abs_path)
            st = ap.stat()
            records_now.append({
                "path": rel_path,
                "sha256": sha,
                "mtime": float(st.st_mtime),
                "size": int(st.st_size),
            })

        # 3) Load the previous manifest and compute the diff.
        manifest_prev = load_manifest(manifest_path)
        to_process, unchanged, tombstones = manifest_diff(records_now, manifest_prev)

        prev_by_path: Dict[str, Record] = {
            rec["path"]: rec for rec in manifest_prev.get("files", [])
        }

        # 4) Process changed/new files (shared chunking pass → dense and optional sparse upsert).
        total_chunks = 0
        total_deleted_old = 0

        dense_upserts = 0
        sparse_upserts = 0

        dense_embedded_bytes = 0
        sparse_embedded_bytes = 0

        for rec in to_process:
            rel_path = rec["path"]
            sha_new = rec["sha256"]

            abs_path = (self.doc_root / rel_path).as_posix()
            text = text_by_abs.get(abs_path)
            if text is None:
                text = Path(abs_path).read_text(encoding="utf-8", errors="ignore")

            chunks = chunker.split(abs_path, text, chunk_size=chunk_size, overlap=overlap)
            chunk_texts: List[str] = []
            ids: List[str] = []
            metas: List[Dict[str, Any]] = []

            for idx, (_fp, chunk_txt) in enumerate(chunks):
                if not chunk_txt.strip():
                    continue
                chunk_texts.append(chunk_txt)
                ids.append(store.make_chunk_id(rel_path, sha_new, idx))
                metas.append({
                    "path": rel_path,
                    "sha256": sha_new,
                    "chunk_idx": idx,
                    "mtime": rec["mtime"],
                })

            if not chunk_texts:
                continue

            if delete_old_versions and rel_path in prev_by_path:
                sha_old = prev_by_path[rel_path]["sha256"]
                if sha_old != sha_new:
                    total_deleted_old += self._delete_file_version(store, rel_path, sha_old)
                    if use_sparse and sparse_store is not None:
                        total_deleted_old += self._delete_file_version(sparse_store, rel_path, sha_old)

            file_embedded_bytes = sum(len(s.encode("utf-8")) for s in chunk_texts)

            # Dense branch
            dense_vecs = embedder.embed(chunk_texts)
            store.add(ids=ids, vectors=dense_vecs, metadatas=metas)
            dense_upserts += len(ids)
            dense_embedded_bytes += file_embedded_bytes

            # Optional sparse branch
            if use_sparse and sparse_store is not None and sparse_embedder is not None:
                sparse_vecs = sparse_embedder.embed(chunk_texts)
                sparse_store.add(ids=ids, vectors=sparse_vecs, metadatas=metas)
                sparse_upserts += len(ids)
                sparse_embedded_bytes += file_embedded_bytes

            total_chunks += len(chunk_texts)

        # 5) Optionally delete tombstones (files that disappeared from disk).
        total_deleted_tombs = 0
        if delete_tombstones and tombstones:
            for prev_rec in tombstones:
                rel_path = prev_rec["path"]
                sha_prev = prev_rec["sha256"]

                total_deleted_tombs += self._delete_file_version(store, rel_path, sha_prev)
                if use_sparse and sparse_store is not None:
                    total_deleted_tombs += self._delete_file_version(sparse_store, rel_path, sha_prev)

        # 6) Publish a fresh manifest that reflects the CURRENT disk state.
        manifest_new = {
            "version": "1",
            "generated_at": "",
            "files": records_now,
        }
        publish_atomic(manifest_new, manifest_path)

        return IngestionStats(
            files_scanned=len(records_now),
            to_process=len(to_process),
            unchanged=len(unchanged),
            tombstones=len(tombstones),
            chunks_added=total_chunks,
            vectors_upserted=dense_upserts + sparse_upserts,
            deleted_old_versions=total_deleted_old,
            deleted_tombstones=total_deleted_tombs,
            published_manifest_path=manifest_path,
            embedded_bytes=dense_embedded_bytes + sparse_embedded_bytes,
            dense_vectors_upserted=dense_upserts,
            sparse_vectors_upserted=sparse_upserts,
            dense_embedded_bytes=dense_embedded_bytes,
            sparse_embedded_bytes=sparse_embedded_bytes,
        )

    @staticmethod
    def _delete_file_version(store: Any, rel_path: str, sha256: str) -> int:
        """
        Remove all chunks belonging to one specific file version.

        Uses the store's native delete_file_version(...) when available.
        Falls back to metadata-filter delete_where(...) if needed.
        """
        if hasattr(store, "delete_file_version"):
            return int(store.delete_file_version(rel_path, sha256))

        before = IngestionManager._count_ids(store, rel_path, sha256)
        store.delete_where({"$and": [{"path": rel_path}, {"sha256": sha256}]})
        after = IngestionManager._count_ids(store, rel_path, sha256)
        return max(0, before - after)

    @staticmethod
    def _count_ids(store: Any, rel_path: str, sha256: str) -> int:
        """
        Return how many IDs exist for a given (path, sha256) pair.
        """
        # Dense Chroma store
        if hasattr(store, "collection"):
            res = store.collection.get(
                where={"$and": [{"path": rel_path}, {"sha256": sha256}]},
                include=[],
            )
            ids = res.get("ids", []) if res else []
            return len(ids)

        # Local sparse SPLADE store
        meta_store = getattr(store, "_meta_store", None)
        if isinstance(meta_store, dict):
            return sum(
                1
                for meta in meta_store.values()
                if meta.get("path") == rel_path and meta.get("sha256") == sha256
            )

        return 0