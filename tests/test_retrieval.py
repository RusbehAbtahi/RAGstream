# -*- coding: utf-8 -*-
"""
Manual Retrieval Test (Hard-coded)
Run from repo root:
    python -m tests.test_retrieval
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Tuple
import pickle
from hashlib import blake2b

from ragstream.retrieval.retriever import Retriever, DocScore
from ragstream.ingestion.vector_store_np import VectorStoreNP
from ragstream.ingestion.loader import DocumentLoader
from ragstream.ingestion.chunker import Chunker

# ----- EDIT THESE WHEN NEEDED -----
WORKSPACE = "project1"
PROMPT    = " what is my Type?"
# ----------------------------------

REPO_ROOT   = Path(__file__).resolve().parents[1]
DATA_DIR    = REPO_ROOT / "data"
RAW_DIR     = DATA_DIR / "doc_raw" / WORKSPACE
PERSIST_DIR = DATA_DIR / "np_store" / WORKSPACE

CHUNK_SIZE  = 500   # must match test_embed.py
OVERLAP     = 100   # must match test_embed.py

def _stable_id(path: str, chunk_text: str) -> str:
    h = blake2b(digest_size=16)
    h.update(path.encode("utf-8")); h.update(b"||"); h.update(chunk_text.encode("utf-8"))
    return h.hexdigest()

def _rebuild_chunk_maps(workspace: str) -> Tuple[Dict[str, Tuple[str,str]], List[Tuple[str,str]]]:
    """
    Recreate the exact chunk stream used for embedding and return:
      - id_to_chunk: {id -> (source_path, chunk_text)}
      - all_chunks:  [(source_path, chunk_text)] in store order
    """
    id_to_chunk: Dict[str, Tuple[str,str]] = {}
    all_chunks:  List[Tuple[str,str]] = []

    loader = DocumentLoader(DATA_DIR / "doc_raw")
    docs = loader.load_documents(workspace)  # preserves deterministic order

    chunker = Chunker()
    for file_path, text in docs:
        chunks = chunker.split(file_path, text, chunk_size=CHUNK_SIZE, overlap=OVERLAP)
        for path, chunk_text in chunks:
            cid = _stable_id(path, chunk_text)
            id_to_chunk[cid] = (path, chunk_text)
            all_chunks.append((path, chunk_text))
    return id_to_chunk, all_chunks

def main() -> None:
    retriever = Retriever(persist_dir=str(PERSIST_DIR))
    results: List[DocScore] = retriever.retrieve(PROMPT, k=10, do_rerank=True)

    print(f"Workspace: {WORKSPACE}")
    print(f"Persist dir: {PERSIST_DIR}")
    print(f"Query: {PROMPT}")

    if not results:
        print("[INFO] No results. Make sure store.pkl exists and OPENAI_API_KEY is set.")
        return

    # Resolve id -> index via VectorStoreNP's in-memory map (store.pkl has no 'id2idx')
    vs = VectorStoreNP(str(PERSIST_DIR))

    # Load meta (for source paths)
    store_path = PERSIST_DIR / "store.pkl"
    with open(store_path, "rb") as f:
        store = pickle.load(f)
    meta = store.get("meta", [])

    print("Top-k results (id, score, idx, source):")
    for r in results:
        idx = vs._id2idx.get(r.id)
        if idx is None:
            print(f"{r.id}\t{r.score:.6f}\t-\t[MISSING IN STORE]")
            continue
        src = meta[idx]["source"] if idx < len(meta) and isinstance(meta[idx], dict) and "source" in meta[idx] else "[no source]"
        print(f"{r.id}\t{r.score:.6f}\t{idx}\t{src}")

    # ---- Extra section: print BEST 3 CHUNKS verbatim ----
    id_to_chunk, all_chunks = _rebuild_chunk_maps(WORKSPACE)

    print("\nBest 3 chunks (verbatim):")
    top3 = results[:3]
    for rank, r in enumerate(top3, start=1):
        chunk_src = None
        chunk_txt = None

        # Try ID-based lookup first (exact match)
        pair = id_to_chunk.get(r.id)
        if pair is not None:
            chunk_src, chunk_txt = pair
        else:
            # Fallback: use idx position if available and within rebuilt list
            idx = vs._id2idx.get(r.id)
            if isinstance(idx, int) and 0 <= idx < len(all_chunks):
                chunk_src, chunk_txt = all_chunks[idx]

        print(f"\n#{rank}  id={r.id}  score={r.score:.6f}")
        if chunk_src:
            print(f"source: {chunk_src}")
        if chunk_txt:
            print(chunk_txt)
        else:
            print("[chunk text unavailable]")

if __name__ == "__main__":
    main()
