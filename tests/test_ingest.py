#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_test.py  —  tiny Linux runner for RAGstream ingestion

What it does (single project):
  - Uses your repo at /home/rusbeh_ab/project/RAGstream  (adjust ROOT if needed)
  - Ingests docs from   ROOT/data/doc_raw/project1
  - Stores vectors into  ROOT/data/chroma_db/project1
  - Publishes manifest   ROOT/data/file_manifest.json
  - Prints ingestion stats and collection count

Prereqs:
  1) Activate your venv:  source /home/rusbeh_ab/venvs/ragstream/bin/activate
  2) Ensure OPENAI_API_KEY is set in your environment (or .env handled by Embedder)

Run:
  python3 ingest_test.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------- CONFIGURE THESE IF YOUR PATHS DIFFER ----------
ROOT = Path("/home/rusbeh_ab/project/RAGstream")   # "~" here means *project root*, not $HOME
DOC_ROOT = ROOT / "data" / "doc_raw"               # e.g., /.../RAGstream/data/doc_raw
SUBFOLDER = "project1"                              # which project to ingest
CHROMA_DIR = ROOT / "data" / "chroma_db" / SUBFOLDER
MANIFEST_PATH = ROOT / "data" / "file_manifest.json"
# ---------------------------------------------------------

def main() -> int:
    # Make the repo importable if not installed as a package
    sys.path.insert(0, str(ROOT.resolve()))

    # Fail fast if key is missing (Embedder relies on it)
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY is not set in the environment.", file=sys.stderr)
        return 2

    # Create target DB directory
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    # Imports (use your actual modules)
    from ragstream.ingestion.ingestion_manager import IngestionManager
    from ragstream.ingestion.chunker import Chunker
    from ragstream.ingestion.embedder import Embedder
    from ragstream.ingestion.vector_store_chroma import VectorStoreChroma

    # Sanity checks
    if not DOC_ROOT.exists():
        print(f"ERROR: doc_root does not exist: {DOC_ROOT}", file=sys.stderr)
        return 3
    if not (DOC_ROOT / SUBFOLDER).exists():
        print(f"ERROR: subfolder does not exist: {DOC_ROOT / SUBFOLDER}", file=sys.stderr)
        return 4

    # Wire components
    mgr = IngestionManager(doc_root=str(DOC_ROOT))
    chunker = Chunker()
    embedder = Embedder(model="text-embedding-3-large")
    store = VectorStoreChroma(persist_dir=str(CHROMA_DIR), collection_name="docs")

    print("=== RAGstream Ingestion (single project) ===")
    print("ROOT       :", ROOT)
    print("DOC_ROOT   :", DOC_ROOT)
    print("SUBFOLDER  :", SUBFOLDER)
    print("CHROMA_DIR :", CHROMA_DIR)
    print("MANIFEST   :", MANIFEST_PATH)

    # Run ingestion
    stats = mgr.run(
        subfolder=SUBFOLDER,
        store=store,
        chunker=chunker,
        embedder=embedder,
        manifest_path=str(MANIFEST_PATH),
        chunk_size=500,
        overlap=100,
        delete_old_versions=True,
        delete_tombstones=False,
    )

    # Report
    print("\n--- Ingestion Stats ---")
    print(f"files_scanned        : {stats.files_scanned}")
    print(f"to_process           : {stats.to_process}")
    print(f"unchanged            : {stats.unchanged}")
    print(f"tombstones           : {stats.tombstones}")
    print(f"chunks_added         : {stats.chunks_added}")
    print(f"vectors_upserted     : {stats.vectors_upserted}")
    print(f"deleted_old_versions : {stats.deleted_old_versions}")
    print(f"deleted_tombstones   : {stats.deleted_tombstones}")
    print(f"manifest_published   : {stats.published_manifest_path}")
    print(f"embedded_bytes       : {stats.embedded_bytes} (~{stats.embedded_bytes / 1024:.2f} KB)")

    # Quick collection count after run
    try:
        count = store.count()
    except Exception:
        count = -1
    print(f"\nCollection count (docs): {count}")
    print("✓ Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
