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

Key responsibilities:
    1) Build a list of current file Records by scanning a doc root/subfolder.
    2) Load the previous manifest and compute a diff (what changed vs. last run).
    3) For changed/new files: chunk → embed → upsert to VectorStoreChroma.
       Optionally delete stale vectors from previous file versions.
    4) Publish a new manifest atomically (tmp → replace) if the run succeeds.

API:
    IngestionManager(doc_root).run(
        subfolder: str,
        store: ChromaVectorStoreBase,
        chunker: Chunker,
        embedder: Embedder,
        manifest_path: str,
        *,
        chunk_size: int = 500,
        overlap: int = 100,
        delete_old_versions: bool = True,
        delete_tombstones: bool = False,
    ) -> dict (stats)

Data structures:
    Record (from file_manifest.py):
        {
          "path":   "project1/file.md",  # relative to doc_root
          "sha256": "<hex>",
          "mtime":  <float>,
          "size":   <int>
        }

Notes:
    • We compute file hashes from bytes on disk (compute_sha256), NOT from text.
    • Chunk IDs are stable: f"{rel_path}::{sha256}::{idx}" (matches your store helpers).
    • We only publish a new manifest after all target files in this run succeed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Local imports: your existing components
from .loader import DocumentLoader          # returns [(abs_path, text), ...]
from .chunker import Chunker                # split(file_path, text, chunk_size, overlap)
from .embedder import Embedder              # embed(list[str]) -> list[list[float]]
from .vector_store_chroma import VectorStoreChroma  # Chroma-backed store

# Manifest utilities
from .file_manifest import (
    compute_sha256,
    load_manifest,
    diff as manifest_diff,
    publish_atomic,
    Record,   # TypedDict
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
    embedded_bytes: int  # total UTF-8 bytes sent to the embedder in this run

class IngestionManager:
    """
    Coordinates the full ingestion pipeline for a given doc root.

    Typical usage:
        mgr = IngestionManager(doc_root="/.../data/doc_raw")
        stats = mgr.run(
            subfolder="project1",
            store=VectorStoreChroma(persist_dir=".../data/chroma_db/project1"),
            chunker=Chunker(),
            embedder=Embedder(model="text-embedding-3-large"),
            manifest_path="/.../data/file_manifest.json",
        )
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

    # -------------------------------------------------------------------------
    # Public entrypoint
    # -------------------------------------------------------------------------

    def run(
        self,
        subfolder: str,
        store: VectorStoreChroma,
        chunker: Chunker,
        embedder: Embedder,
        manifest_path: str,
        *,
        chunk_size: int = 500,
        overlap: int = 100,
        delete_old_versions: bool = True,
        delete_tombstones: bool = False,
    ) -> IngestionStats:
        """
        Execute a full ingestion cycle for one subfolder under doc_root.

        Steps:
            1) Scan subfolder → build current Records (bytes hash, mtime, size).
            2) Load previous manifest → diff → decide what to process.
            3) For each changed/new file:
                   - chunk (deterministic windows)
                   - embed (batch)
                   - upsert to Chroma (IDs: rel_path::sha256::idx; metadatas)
                   - optionally delete old-version chunks (if path existed with other sha).
            4) Optionally delete tombstone chunks (files removed from disk).
            5) Publish new manifest atomically.

        Returns:
            IngestionStats with useful counters.
        """
        manifest_path = str(Path(manifest_path).resolve())

        # 1) Load documents (absolute path + raw text) from the subfolder.
        docs = self.loader.load_documents(subfolder)  # [(abs_path, text), ...]
        # Build a quick map from abs_path to text for later reuse.
        text_by_abs: Dict[str, str] = {abs_path: text for abs_path, text in docs}

        # 2) Build current Records by hashing files on disk (bytes).
        records_now: List[Record] = []
        for abs_path, _text in docs:
            ap = Path(abs_path)
            # relative path stored in manifest and metadata
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

        # For old-version deletion we need a map: previous[path] -> prev_sha
        prev_by_path: Dict[str, Record] = {
            rec["path"]: rec for rec in manifest_prev.get("files", [])
        }

        # 4) Process changed/new files (chunk → embed → upsert).
        total_chunks = 0
        total_upserts = 0
        total_deleted_old = 0
        total_embedded_bytes = 0  # sum of UTF-8 bytes of all chunk_texts we embed this run

        for rec in to_process:
            rel_path = rec["path"]
            sha_new = rec["sha256"]

            abs_path = (self.doc_root / rel_path).as_posix()
            text = text_by_abs.get(abs_path)
            if text is None:
                # Fallback: if loader skipped for some reason, read file now
                # (should rarely happen, but keeps us robust).
                text = Path(abs_path).read_text(encoding="utf-8", errors="ignore")

            # Build chunks deterministically (same as your ad-hoc test).
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
                # Nothing to embed/store for this file—continue gracefully.
                continue

            # Optional: delete all chunks for the OLD version of this file (same path, different sha).
            if delete_old_versions and rel_path in prev_by_path:
                sha_old = prev_by_path[rel_path]["sha256"]
                if sha_old != sha_new:
                    # Delete by metadata filter (explicit audit)
                    before = self._count_ids(store, rel_path, sha_old)
                    store.delete_where({"$and": [{"path": rel_path}, {"sha256": sha_old}]})
                    after = self._count_ids(store, rel_path, sha_old)
                    total_deleted_old += max(0, before - after)

             # Count bytes that will be embedded (exact UTF-8 length of the texts we send).
            file_embedded_bytes = sum(len(s.encode("utf-8")) for s in chunk_texts)
            total_embedded_bytes += file_embedded_bytes
            # Embed + upsert in batches (embedder handles batching internally if needed).
            vecs = embedder.embed(chunk_texts)
            store.add(ids=ids, vectors=vecs, metadatas=metas)

            total_chunks += len(chunk_texts)
            total_upserts += len(ids)

        # 5) Optionally delete tombstones (files that disappeared from disk).
        total_deleted_tombs = 0
        if delete_tombstones and tombstones:
            for prev_rec in tombstones:
                rel_path = prev_rec["path"]
                sha_prev = prev_rec["sha256"]
                before = self._count_ids(store, rel_path, sha_prev)
                store.delete_where({"$and": [{"path": rel_path}, {"sha256": sha_prev}]})
                after = self._count_ids(store, rel_path, sha_prev)
                total_deleted_tombs += max(0, before - after)

        # 6) Publish a fresh manifest that reflects the CURRENT disk state.
        manifest_new = {
            "version": "1",
            "generated_at": "",   # publish_atomic will stamp UTC if empty
            "files": records_now,
        }
        publish_atomic(manifest_new, manifest_path)

        return IngestionStats(
            files_scanned=len(records_now),
            to_process=len(to_process),
            unchanged=len(unchanged),
            tombstones=len(tombstones),
            chunks_added=total_chunks,
            vectors_upserted=total_upserts,
            deleted_old_versions=total_deleted_old,
            deleted_tombstones=total_deleted_tombs,
            published_manifest_path=manifest_path,
            embedded_bytes=total_embedded_bytes,
        )

    # -------------------------------------------------------------------------
    # Small helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _count_ids(store: VectorStoreChroma, rel_path: str, sha256: str) -> int:
        """
        Return how many IDs exist for a given (path, sha256) pair.
        Used to report how many vectors were deleted during cleanup.
        """
        res = store.collection.get(where={"$and": [{"path": rel_path}, {"sha256": sha256}]}, include=[])
        ids = res.get("ids", []) if res else []
        return len(ids)
