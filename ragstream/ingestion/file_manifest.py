# -*- coding: utf-8 -*-
"""
file_manifest.py

Purpose:
    A tiny, deterministic "ledger" for document ingestion. It tells the
    ingestion pipeline which files have changed since last run so we only
    re-chunk/re-embed what's necessary.

What this module provides:
    1) compute_sha256(file_path) -> str
       - Returns the SHA-256 hex digest for ONE file on disk.

    2) load_manifest(manifest_path) -> dict
       - Loads the last published manifest JSON (or returns an empty one).

    3) diff(records_now, manifest_prev) -> (to_process, unchanged, tombstones)
       - Compares current scan results ("records_now") against the previous
         manifest ("manifest_prev") and decides what to ingest or clean up.

    4) publish_atomic(manifest_dict, manifest_path) -> None
       - Writes the ENTIRE manifest JSON atomically: *.tmp then os.replace.

Data shapes:
    Record (one per file; used both during scan and inside the manifest):
        {
          "path":   str,    # RELATIVE path from doc root, e.g. "project1/file.md"
          "sha256": str,    # content hash (hex)
          "mtime":  float,  # UNIX mtime
          "size":   int     # bytes
        }

    Manifest JSON written to disk:
        {
          "version": "1",
          "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
          "files": [Record, Record, ...]
        }

Notes:
    - This module does NOT scan directories. IngestionManager (or caller) is
      responsible for building 'records_now' from the doc root using compute_sha256.
    - 'diff' expects 'records_now' as a list[Record] and the previous manifest dict.
    - 'tombstones' are files that were present in the previous manifest but are
      missing on disk now (useful for deleting stale vectors).
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple, TypedDict


# ---------------------------------------------------------------------------
# Typed structures for clarity (no runtime dependency; just type hints)
# ---------------------------------------------------------------------------

class Record(TypedDict):
    """A single file's state at scan time (also stored in the manifest)."""
    path: str     # relative path from doc root, POSIX style (e.g., "project1/file.md")
    sha256: str   # hex SHA-256 of the file contents
    mtime: float  # last modified time (float UNIX timestamp)
    size: int     # file size in bytes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_sha256(file_path: str, *, chunk_size: int = 1024 * 1024) -> str:
    """
    Compute a SHA-256 hex digest for a SINGLE file.

    Args:
        file_path: absolute or relative path to a file on disk.
        chunk_size: read size in bytes (default 1MB) to handle large files safely.

    Returns:
        The hex string of the SHA-256 content hash.

    Raises:
        FileNotFoundError: if the file does not exist.
        IsADirectoryError: if 'file_path' is a directory.
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if p.is_dir():
        raise IsADirectoryError(f"Expected a file, got directory: {file_path}")

    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load_manifest(manifest_path: str) -> Dict[str, Any]:
    """
    Load the manifest JSON if it exists; otherwise, return a valid empty structure.

    Args:
        manifest_path: full filesystem path to 'file_manifest.json'.

    Returns:
        Dict with keys:
            - "version": "1"
            - "generated_at": ISO-8601 string (UTC) or ""
            - "files": list[Record]
    """
    mp = Path(manifest_path)
    if not mp.exists():
        # Return a deterministic empty manifest structure.
        return {
            "version": "1",
            "generated_at": "",
            "files": [],
        }

    try:
        with mp.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        # If the file is corrupted, fail loudly; caller can decide what to do.
        raise ValueError(f"Manifest is not valid JSON: {manifest_path}") from e

    # Normalize to expected keys (be forgiving about missing keys).
    if "version" not in data:
        data["version"] = "1"
    if "generated_at" not in data:
        data["generated_at"] = ""
    if "files" not in data or not isinstance(data["files"], list):
        data["files"] = []

    return data


def diff(
    records_now: List[Record],
    manifest_prev: Dict[str, Any],
) -> Tuple[List[Record], List[Record], List[Record]]:
    """
    Compare the current scan against the previous manifest.

    Args:
        records_now: list of current file Records (built by the caller during scan).
        manifest_prev: manifest dict as returned by load_manifest().

    Returns:
        (to_process, unchanged, tombstones)
            to_process: Records that are NEW or CHANGED (sha256 differs).
            unchanged:  Records that are IDENTICAL to previous (same path + sha256).
            tombstones: Records from the PREVIOUS manifest that are MISSING now on disk.

    Matching logic:
        - Key by 'path'.
        - If 'path' is new (not in previous) => to_process.
        - If 'path' exists but sha256 changed => to_process.
        - Else => unchanged.
        - tombstones = previous paths not present in records_now.
    """
    prev_files = manifest_prev.get("files", []) if isinstance(manifest_prev, dict) else []

    # Build fast lookups by path.
    prev_by_path: Dict[str, Record] = {rec["path"]: rec for rec in prev_files}  # type: ignore[typeddict-item]
    now_by_path: Dict[str, Record] = {rec["path"]: rec for rec in records_now}

    to_process: List[Record] = []
    unchanged: List[Record] = []
    tombstones: List[Record] = []

    # Decide new/changed vs unchanged.
    for path, now_rec in now_by_path.items():
        prev_rec = prev_by_path.get(path)
        if prev_rec is None:
            # New file.
            to_process.append(now_rec)
        else:
            # Same path existed previously; compare hashes.
            if str(prev_rec["sha256"]) != str(now_rec["sha256"]):
                to_process.append(now_rec)   # Content changed.
            else:
                unchanged.append(now_rec)    # Identical (skip re-ingest).

    # Anything in previous but not in current is a tombstone (missing on disk).
    for path, prev_rec in prev_by_path.items():
        if path not in now_by_path:
            tombstones.append(prev_rec)

    return to_process, unchanged, tombstones


def publish_atomic(manifest_dict: Dict[str, Any], manifest_path: str) -> None:
    """
    Atomically write the ENTIRE manifest JSON to disk.

    Implementation:
        - Ensure parent directory exists.
        - Write to <manifest_path>.tmp with UTF-8 + pretty JSON.
        - os.replace(tmp, manifest_path) for atomic swap (POSIX-safe).

    Args:
        manifest_dict: the full manifest payload to persist.
        manifest_path: destination JSON path, e.g. ".../data/file_manifest.json".
    """
    mp = Path(manifest_path)
    mp.parent.mkdir(parents=True, exist_ok=True)

    # Stamp/refresh generated_at if caller forgot; harmless overwrite is fine.
    if "generated_at" not in manifest_dict:
        manifest_dict["generated_at"] = _utc_now_iso()
    else:
        # If present but empty, also refresh.
        if not manifest_dict["generated_at"]:
            manifest_dict["generated_at"] = _utc_now_iso()

    tmp_path = mp.with_suffix(mp.suffix + ".tmp")

    # Write JSON with a stable format (sorted keys, indentation).
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(manifest_dict, f, ensure_ascii=False, indent=2, sort_keys=True)

    # Atomic replace: either the old file stays, or the new one fully replaces it.
    os.replace(str(tmp_path), str(mp))


# ---------------------------------------------------------------------------
# Internal helpers (not part of the public API)
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    """Return a UTC timestamp in ISO-8601 format with 'Z' suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
