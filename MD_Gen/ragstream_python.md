# Python Files Index (ragstream)

## /home/rusbeh_ab/project/RAGstream/ragstream/app

### ~\ragstream\app\agents.py
```python
"""
Agents (A1..A4)
===============
- A1 Deterministic Code Injector → builds ❖ FILES and enforces Exact File Lock.
- A2 Prompt Shaper → pass-1 propose headers; audit-2 may trigger one retrieval re-run on scope change.
- A3 NLI Gate → keep/drop via entailment (θ strictness).
- A4 Condenser → emits S_ctx (Facts / Constraints / Open Issues) with citations.
"""
from typing import List, Dict

class A1_DCI:
    def build_files_block(self, named_files: List[str], lock: bool) -> str:
        return "❖ FILES\n"

class A2_PromptShaper:
    def propose(self, question: str) -> Dict[str, str]:
        return {"intent": "explain", "domain": "software", "headers": "H"}
    def audit_and_rerun(self, shape: Dict[str, str], s_ctx: List[str]) -> bool:
        """
        Return True iff audit materially changes task scope (intent/domain),
        allowing exactly one retrieval→A3→A4 re-run.
        """
        return False

class A3_NLIGate:
    def __init__(self, theta: float = 0.6) -> None:
        self.theta = theta
    def filter(self, candidates: List[str], question: str) -> List[str]:
        return candidates

class A4_Condenser:
    def condense(self, kept: List[str]) -> List[str]:
        return ["Facts:", "Constraints:", "Open Issues:"]
```

### ~\ragstream\app\controller.py
```python
"""
AppController
=============
Controller orchestrates A1..A4 with ConversationMemory and the retrieval path.
- Exact File Lock short-circuits retrieval.
- A2 runs twice (propose → audit); at most one retrieval re-run on scope change.
"""
from typing import List
from ragstream.retrieval.retriever import Retriever, DocScore
from ragstream.retrieval.reranker import Reranker
from ragstream.orchestration.prompt_builder import PromptBuilder
from ragstream.orchestration.llm_client import LLMClient
from ragstream.app.agents import A1_DCI, A2_PromptShaper, A3_NLIGate, A4_Condenser
from ragstream.memory.conversation_memory import ConversationMemory

class AppController:
    def __init__(self) -> None:
        self.retriever = Retriever()
        self.reranker = Reranker()
        self.prompt_builder = PromptBuilder()
        self.llm_client = LLMClient()
        self.a1 = A1_DCI()
        self.a2 = A2_PromptShaper()
        self.a3 = A3_NLIGate()
        self.a4 = A4_Condenser()
        self.convmem = ConversationMemory()
        self.eligibility_pool = set()  # ON/OFF file gating handled by UI/controller

    def handle(self, user_prompt: str, named_files: List[str], exact_lock: bool) -> str:
        # A2 pass-1
        _shape = self.a2.propose(user_prompt)

        # A1 — ❖ FILES
        files_block = self.a1.build_files_block(named_files, exact_lock)

        # Retrieval path (skip if lock)
        kept_chunks: List[str] = []
        if not exact_lock:
            results: List[DocScore] = self.retriever.retrieve(user_prompt, k=10)
            ids = [r.id for r in results]
            kept_chunks = self.a3.filter(ids, user_prompt)

        # A4 — condense to S_ctx
        s_ctx = self.a4.condense(kept_chunks)

        # A2 audit-2 (may trigger one re-run on scope change)
        if self.a2.audit_and_rerun(_shape, s_ctx) and not exact_lock:
            results = self.retriever.retrieve(user_prompt, k=10)
            ids = [r.id for r in results]
            kept_chunks = self.a3.filter(ids, user_prompt)
            s_ctx = self.a4.condense(kept_chunks)

        # Compose & send
        prompt = self.prompt_builder.build(user_prompt, files_block, s_ctx, shape=_shape)
        return self.llm_client.complete(prompt)
```

### ~\ragstream\app\ui_streamlit.py
```python
"""
StreamlitUI
===========
UI surface: prompt box, ON/OFF eligibility, Exact File Lock, agent toggles,
Super-Prompt preview, and transparency panel (ephemeral).
"""
import streamlit as st
from ragstream.app.controller import AppController

class StreamlitUI:
    def __init__(self) -> None:
        self.ctrl = AppController()

    def render(self) -> None:
        st.title("RAGstream")
        st.write("Prompt box, file ON/OFF, Exact File Lock, agent toggles, Super-Prompt preview")
```

### ~\ragstream\app\agents\a1_dci.py
```python
"""
Agents (A1..A4)
===============
Controller-side agents:
- A1 Deterministic Code Injector → builds ❖ FILES (FULL/PACK) and enforces Exact File Lock.
- A2 Prompt Shaper → suggests intent/domain + headers (advisory).
- A3 NLI Gate → keep/drop based on entailment with θ strictness.
- A4 Context Condenser → outputs S_ctx (Facts / Constraints / Open Issues) with citations.
"""
from typing import List, Dict, Tuple, Optional

class A1_DCI:
    def build_files_block(self, named_files: List[str], lock: bool) -> str:
        return "❖ FILES\n"

```

### ~\ragstream\app\agents\a2_prompt_shaper.py
```python
"""
Agents (A1..A4)
===============
Controller-side agents:
- A1 Deterministic Code Injector → builds ❖ FILES (FULL/PACK) and enforces Exact File Lock.
- A2 Prompt Shaper → suggests intent/domain + headers (advisory).
- A3 NLI Gate → keep/drop based on entailment with θ strictness.
- A4 Context Condenser → outputs S_ctx (Facts / Constraints / Open Issues) with citations.
"""
from typing import List, Dict, Tuple, Optional


class A2_PromptShaper:
    def propose(self, question: str) -> Dict[str, str]:
        return {"intent": "explain", "domain": "software"}


```

### ~\ragstream\app\agents\a3_nli_gate.py
```python
"""
Agents (A1..A4)
===============
Controller-side agents:
- A1 Deterministic Code Injector → builds ❖ FILES (FULL/PACK) and enforces Exact File Lock.
- A2 Prompt Shaper → suggests intent/domain + headers (advisory).
- A3 NLI Gate → keep/drop based on entailment with θ strictness.
- A4 Context Condenser → outputs S_ctx (Facts / Constraints / Open Issues) with citations.
"""
from typing import List, Dict, Tuple, Optional


class A3_NLIGate:
    def __init__(self, theta: float = 0.6) -> None:
        self.theta = theta
    def filter(self, candidates: List[str], question: str) -> List[str]:
        return candidates
```

### ~\ragstream\app\agents\a4_condenser.py
```python
"""
Agents (A1..A4)
===============
Controller-side agents:
- A1 Deterministic Code Injector → builds ❖ FILES (FULL/PACK) and enforces Exact File Lock.
- A2 Prompt Shaper → suggests intent/domain + headers (advisory).
- A3 NLI Gate → keep/drop based on entailment with θ strictness.
- A4 Context Condenser → outputs S_ctx (Facts / Constraints / Open Issues) with citations.
"""
from typing import List, Dict, Tuple, Optional

class A4_Condenser:
    def condense(self, kept: List[str]) -> List[str]:
        return ["Facts:", "Constraints:", "Open Issues:"]
```


## /home/rusbeh_ab/project/RAGstream/ragstream/config

### ~\ragstream\config\settings.py
```python
"""
Settings
========
Centralised, cached access to environment configuration.
"""
import os
from typing import Any, Dict

class Settings:
    _CACHE: Dict[str, Any] = {}

    @classmethod
    def get(cls, key: str, default: Any | None = None) -> Any:
        if key not in cls._CACHE:
            cls._CACHE[key] = os.getenv(key, default)
        return cls._CACHE[key]
```


## /home/rusbeh_ab/project/RAGstream/ragstream/ingestion

### ~\ragstream\ingestion\chroma_vector_store_base.py
```python
# -*- coding: utf-8 -*-
"""
chroma_vector_store_base.py

Shared, production-grade base class for Chroma-backed vector stores.

Context:
- Replaces the old NumPy PKL store with a persistent, crash-safe, on-disk DB.
- Both VectorStoreChroma and HistoryStoreChroma should inherit from this class.
- We intentionally removed any separate "IVectorStore" interface; this concrete
  base provides the canonical add/query/snapshot API and small hook points so
  subclasses can enforce their own policies without duplicating core logic.

Contract (compatible with your former NumPy store):
    add(ids, vectors, metadatas) -> None
    query(vector, k=10, where=None) -> List[str]
    snapshot(timestamp=None) -> Path

Design notes:
- Uses chromadb.PersistentClient(path=...) to ensure physical persistence on disk.
- Stores ONLY embeddings + metadatas (documents are optional for this project).
- Provides hook methods (_pre_add/_post_add/_pre_query/_post_query) so that the
  history store can enforce selection-only / capacity / eligibility rules later.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import shutil
from datetime import datetime

import chromadb
from chromadb.config import Settings


class ChromaVectorStoreBase:
    """
    Base implementation of a Chroma-backed vector store.

    Responsibilities:
      - Own the PersistentClient and a single collection.
      - Provide simple, deterministic add/query/snapshot methods.
      - Offer policy hooks for subclasses (history vs. document store).

    Subclasses:
      - VectorStoreChroma(ChromaVectorStoreBase)
      - HistoryStoreChroma(ChromaVectorStoreBase)

    Typical metadata for each chunk (recommended):
      {
        "path": "<relative/original file path>",
        "sha256": "<content hash>",
        "mtime": <float or iso string>,
        "chunk_idx": <int>
      }
    """

    def __init__(
        self,
        persist_dir: str,
        collection_name: str,
        *,
        anonymized_telemetry: bool = False,
    ) -> None:
        """
        Initialize a persistent Chroma client and open/create a collection.

        Args:
            persist_dir: Directory where Chroma DB files live (e.g. PATHS.chroma_db).
            collection_name: Logical collection name (e.g. "docs" or "history").
            anonymized_telemetry: Pass False to avoid any telemetry (default False).
        """
        self.persist_path = Path(persist_dir)
        self.persist_path.mkdir(parents=True, exist_ok=True)

        # Settings keep the DB local, file-backed, and quiet (no telemetry).
        self._client = chromadb.PersistentClient(
            path=str(self.persist_path),
            settings=Settings(anonymized_telemetry=anonymized_telemetry),
        )

        self.collection_name = collection_name
        self._col = self._client.get_or_create_collection(self.collection_name)

    # -------------------------------------------------------------------------
    # Public API (stable)
    # -------------------------------------------------------------------------

    def add(
        self,
        ids: List[str],
        vectors: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Upsert vectors and metadatas into the collection.

        Contract matches the previous NumPy store:
          - ids:      unique stable IDs per chunk (e.g. "path::sha256::i")
          - vectors:  2D list [N, D] of float embeddings
          - metadatas: optional [N] list of dicts (same length as ids)

        Notes:
          - If an id already exists, Chroma upserts (replaces) it.
          - Subclasses may enforce policies via _pre_add/_post_add hooks.
        """
        if not ids or not vectors:
            return
        if len(ids) != len(vectors):
            raise ValueError("ids and vectors length mismatch")
        if metadatas is not None and len(metadatas) != len(ids):
            raise ValueError("metadatas length must match ids (or be None)")

        ids, vectors, metadatas = self._pre_add(ids, vectors, metadatas)

        # Core upsert (embeddings + optional metadatas). Documents are unused here.
        self._col.upsert(
            ids=ids,
            embeddings=vectors,
            metadatas=metadatas,
        )

        self._post_add(ids, vectors, metadatas)

    def query(
        self,
        vector: List[float],
        k: int = 10,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Nearest-neighbor search against the collection by embedding vector.

        Args:
            vector: 1D float embedding of the query.
            k: number of neighbors to return.
            where: optional Chroma metadata filter; pass None for no filter.

        Returns:
            List[str]: top-k IDs (sorted by similarity).
                       This mirrors the former NumPy store return type.

        Subclasses may adjust behavior via _pre_query/_post_query.
        """
        if not isinstance(vector, list) or not vector:
            raise ValueError("query vector must be a non-empty 1D list[float]")

        k = max(1, int(k))

        # IMPORTANT: some Chroma versions reject {} and require None when no filter is used.
        where = None if not where else where

        vector, k, where = self._pre_query(vector, k, where)

        res = self._col.query(
            query_embeddings=[vector],
            n_results=k,
            where=where,               # None means "no filter"
            include=["metadatas"],     # metadatas available for post-processing if needed
        )
        # result shape: {"ids": [[...]], "metadatas": [[...]], ...}
        ids: List[str] = res.get("ids", [[]])[0] if res else []
        ids = self._post_query(ids, res)
        return ids

    def snapshot(self, timestamp: Optional[str] = None) -> Path:
        """
        Create a filesystem snapshot of the current Chroma DB directory.

        Implementation:
          - Copies the entire persist_dir into ./snapshots/<db_name>_<timestamp>/
          - This is a coarse, but deterministic snapshot suitable for local dev.
          - For very large DBs, consider OS-level copy-on-write or backup tooling.

        Returns:
            Path to the created snapshot directory.
        """
        ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshots_dir = self.persist_path.parent / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        dst = snapshots_dir / f"{self.persist_path.name}_{ts}"

        # Copy the whole DB dir. dirs_exist_ok=False to avoid accidental overwrite.
        shutil.copytree(self.persist_path, dst, dirs_exist_ok=False)
        return dst

    # Optional utility, handy for re-ingestion flows that need to remove stale chunks
    def delete_where(self, where: Dict[str, Any]) -> None:
        """
        Delete by metadata filter (two-phase: lookup ids, then delete ids).
        This makes the operation explicit and auditable.
        """
        if not where:
            return
        res = self._col.get(where=where, include=[])  # get ids only
        ids: List[str] = res.get("ids", []) if res else []
        if ids:
            self._col.delete(ids=ids)

    # Expose underlying collection for advanced ops if needed (debug, migration)
    @property
    def collection(self):
        return self._col

    # -------------------------------------------------------------------------
    # Hook methods (subclasses override as needed)
    # -------------------------------------------------------------------------

    def _pre_add(
        self,
        ids: List[str],
        vectors: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]],
    ) -> tuple[List[str], List[List[float]], Optional[List[Dict[str, Any]]]]:
        """
        Override in subclasses to enforce policies before upsert, e.g.:
          - capacity checks, eviction, dedup, eligibility constraints (history store)
          - metadata normalization or enrichment
        Default: no-op, return inputs unchanged.
        """
        return ids, vectors, metadatas

    def _post_add(
        self,
        ids: List[str],
        vectors: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]],
    ) -> None:
        """
        Override in subclasses to log / index / audit after upsert.
        Default: no-op.
        """
        return None

    def _pre_query(
        self,
        vector: List[float],
        k: int,
        where: Optional[Dict[str, Any]],
    ) -> tuple[List[float], int, Optional[Dict[str, Any]]]:
        """
        Override in subclasses to enforce query-time policies, e.g.:
          - eligibility alignment (history store)
          - metadata filter injection
        Default: no-op, return inputs unchanged.
        """
        return vector, k, where

    def _post_query(self, ids: List[str], raw_result: Dict[str, Any]) -> List[str]:
        """
        Override in subclasses to transform the result list, e.g.:
          - strip restricted items
          - reorder by additional heuristics
        Default: no-op, return ids unchanged.
        """
        return ids
```

### ~\ragstream\ingestion\chunker.py
```python
"""
Chunker
=======
Splits raw text into overlapping, character-based chunks for embedding.
"""

from typing import List, Tuple

class Chunker:
    """Window-based text splitter."""

    def split(self, file_path: str, text: str, chunk_size: int = 500, overlap: int = 100) -> List[Tuple[str, str]]:
        """
        Split the given text into overlapping chunks.

        :param file_path: Absolute path to the source file (kept with each chunk)
        :param text: The full text content of the file
        :param chunk_size: Maximum characters per chunk (default=500)
        :param overlap: Number of characters to overlap between chunks (default=100)
        :return: List of (file_path, chunk_text) tuples
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if overlap < 0:
            raise ValueError("overlap must be non-negative")
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")

        chunks: List[Tuple[str, str]] = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = min(start + chunk_size, text_length)
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append((file_path, chunk_text))
            start += chunk_size - overlap

        return chunks
```

### ~\ragstream\ingestion\embedder.py
```python
"""
Embedder
========
Wraps OpenAI embeddings API to convert text chunks into dense vectors.
"""
from typing import List
import os
from dotenv import load_dotenv
from openai import OpenAI

class Embedder:
    """High-level embedding interface using OpenAI API."""
    def __init__(self, model: str = "text-embedding-3-large"):
        load_dotenv()  # Load .env file
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment or .env file")

        self.client = OpenAI(api_key=api_key)
        self.model = model

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        Returns: list of embedding vectors (one per text)
        """
        if not texts:
            return []

        # OpenAI API allows batch embedding calls
        response = self.client.embeddings.create(
            model=self.model,
            input=texts
        )

        # Extract embeddings from response
        embeddings = [item.embedding for item in response.data]
        return embeddings
```

### ~\ragstream\ingestion\file_manifest.py
```python
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
```

### ~\ragstream\ingestion\ingestion_manager.py
```python
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
```

### ~\ragstream\ingestion\loader.py
```python
"""
DocumentLoader
==============
Responsible for discovering and loading raw files from *data/doc_raw* and its subfolders.
"""

from pathlib import Path
from typing import List, Tuple

class DocumentLoader:
    """Scans the raw-document directory and yields (file_path, file_text) tuples."""

    def __init__(self, root: Path) -> None:
        """
        :param root: Path to the base 'data/doc_raw' folder.
        """
        self.root = root

    def load_documents(self, subfolder: str) -> List[Tuple[str, str]]:
        """
        Load all files from the given subfolder inside data/doc_raw.
        Reads any file extension as plain text.

        :param subfolder: Name of the subfolder (e.g., 'project1').
        :return: List of tuples (absolute_file_path_str, file_text).
        """
        folder_path = self.root / subfolder
        if not folder_path.exists():
            raise FileNotFoundError(f"Input folder does not exist: {folder_path}")

        docs: List[Tuple[str, str]] = []

        for file_path in folder_path.rglob("*"):
            if file_path.is_file():
                try:
                    text = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    # Fallback: try latin-1 to avoid crash on non-UTF8 files
                    text = file_path.read_text(encoding="latin-1")
                docs.append((str(file_path.resolve()), text))

        return docs
```

### ~\ragstream\ingestion\vector_store_chroma.py
```python
# -*- coding: utf-8 -*-
"""
vector_store_chroma.py

Concrete document vector store for RAGstream, backed by Chroma.
This subclass is intentionally thin: it inherits all core mechanics
(add/query/snapshot/delete_where) from ChromaVectorStoreBase and exposes
a couple of convenience helpers that are useful for the ingestion flow.

Usage:
    store = VectorStoreChroma(persist_dir=PATHS.chroma_db)   # default collection "docs"
    store.add(ids=[...], vectors=[...], metadatas=[...])
    top_ids = store.query(vector=q_emb, k=5)
    snap_dir = store.snapshot()  # filesystem snapshot of the persistent DB

Notes:
- We removed the separate "IVectorStore" interface; this concrete class
  (via its base) is now the canonical storage API for documents.
- History policies (selection-only, capacity, eligibility alignment) belong
  to a separate HistoryStoreChroma subclass and are not implemented here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .chroma_vector_store_base import ChromaVectorStoreBase


class VectorStoreChroma(ChromaVectorStoreBase):
    """
    Chroma-backed vector store for document chunks.

    Responsibilities:
      - Provide a ready-to-use, persistent collection (default: "docs").
      - Reuse base add/query/snapshot/delete_where without policy overrides.
      - Offer tiny utilities for common ingestion tasks (e.g., ID formatting).
    """

    def __init__(
        self,
        persist_dir: str,
        collection_name: str = "docs",
        *,
        anonymized_telemetry: bool = False,
    ) -> None:
        """
        Create (or open) the persistent "docs" collection inside persist_dir.

        Args:
            persist_dir: Directory where Chroma keeps its on-disk files.
            collection_name: Logical collection name (default: "docs").
            anonymized_telemetry: Disable/enable Chroma telemetry (default: False).
        """
        super().__init__(
            persist_dir=persist_dir,
            collection_name=collection_name,
            anonymized_telemetry=anonymized_telemetry,
        )

    # ---------------------------------------------------------------------
    # Convenience helpers (optional; used by ingestion code paths)
    # ---------------------------------------------------------------------

    @staticmethod
    def make_chunk_id(rel_path: str, sha256: str, chunk_idx: int) -> str:
        """
        Deterministic ID format used across RAGstream ingestion.
        Example: "docs/Req.md::a1b2c3...::12"
        """
        return f"{rel_path}::{sha256}::{chunk_idx}"

    def delete_file_version(self, rel_path: str, sha256: str) -> int:
        """
        Remove all chunks belonging to a specific file content version.

        This is typically called when a file changes: we ingest the new sha256,
        then delete the old one to prevent duplicate versions.

        Args:
            rel_path: File path relative to the project doc root.
            sha256: Content hash of the OLD version to remove.

        Returns:
            Number of deleted IDs (best-effort; 0 if nothing matched).
        """
        # Look up matching IDs by metadata, then delete by ID for clarity/audit.
        res = self.collection.get(where={"path": rel_path, "sha256": sha256}, include=[])
        ids = res.get("ids", []) if res else []
        if ids:
            self.collection.delete(ids=ids)
        return len(ids)

    # Introspection utilities (handy for tests/diagnostics)

    @property
    def name(self) -> str:
        """Return the collection name (e.g., 'docs')."""
        return self.collection_name

    @property
    def persist_root(self) -> Path:
        """Return the directory containing the on-disk Chroma database."""
        return self.persist_path

    def count(self) -> int:
        """Return total number of stored vectors (documents/chunks)."""
        try:
            return int(self.collection.count())
        except Exception:
            # Older clients may not implement .count(); fall back to get(ids=None)
            res = self.collection.get()  # may be heavy on very large stores
            return len(res.get("ids", [])) if res else 0
```


## /home/rusbeh_ab/project/RAGstream/ragstream/orchestration

### ~\ragstream\orchestration\llm_client.py
```python
"""
LLMClient
=========
Adapter for model calls + cost estimate.
"""
class LLMClient:
    def complete(self, prompt: str) -> str:
        return "ANSWER"
    def estimate_cost(self, tokens: int) -> float:
        return 0.0
```

### ~\ragstream\orchestration\prompt_builder.py
```python
"""
PromptBuilder
=============
Composes the Super-Prompt with fixed authority order:
[Hard Rules] → [Project Memory] → [❖ FILES] → [S_ctx] → [Task/Mode]
(RECENT HISTORY may be shown for continuity; non-authoritative.)
"""
from typing import List, Optional, Dict

class PromptBuilder:
    def build(self, question: str, files_block: Optional[str], s_ctx: List[str], shape: Optional[Dict] = None) -> str:
        return "PROMPT"
```


## /home/rusbeh_ab/project/RAGstream/ragstream/retrieval

### ~\ragstream\retrieval\attention.py
```python
"""
AttentionWeights (legacy)
=========================
Kept for compatibility; not central in current eligibility model.
"""
from typing import Dict

class AttentionWeights:
    def weight(self, scores: Dict[str, float]) -> Dict[str, float]:
        return scores
```

### ~\ragstream\retrieval\doc_score.py
```python
# -*- coding: utf-8 -*-
"""
DocScore
========
Pure data container for retrieval results.

Structure mandated by UML (Retriever ..> DocScore) and requirements:
- `id`:   document/chunk identifier (string)
- `score`: cosine similarity score (float, higher is better)
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class DocScore:
    id: str
    score: float
```

### ~\ragstream\retrieval\reranker.py
```python
"""
Reranker
========
Cross-encoder reranking placeholder.
"""
from typing import List

class Reranker:
    def rerank(self, ids: List[str], query: str) -> List[str]:
        return ids
```

### ~\ragstream\retrieval\retriever.py
```python
# -*- coding: utf-8 -*-
"""
Retriever
=========
Implements RET-01 (cosine top-k) and plugs optional RET-02 rerank stage.

Pipeline: query text --(Embedder)--> vector --(VectorStoreNP.query)--> ids
          [optional rerank] --> List[DocScore]

Notes
-----
* Current concrete vector store is NumPy-backed `VectorStoreNP` (exact cosine).
* The vector-store interface returns *ids*. To fulfill the requirement of
  returning cosine scores, we compute per-id cosine scores by reading the
  concrete store's in-memory arrays when available (VectorStoreNP exposes
  `_emb`, `_ids`, and `_id2idx`). This avoids changing the public interface.
  If such internals are unavailable (e.g. future Chroma backend), we still
  return `DocScore` with a neutral score of 0.0.
"""
from __future__ import annotations

from typing import List, Optional, Sequence
import math

import numpy as np

from ragstream.retrieval.doc_score import DocScore  # re-exported via this module
# Re-export so existing imports `from ragstream.retrieval.retriever import DocScore` keep working.
DocScore = DocScore  # noqa: F401  (module-level alias for compatibility)

from ragstream.ingestion.embedder import Embedder
from ragstream.ingestion.vector_store_np import VectorStoreNP

from ragstream.retrieval.reranker import Reranker
from ragstream.utils.paths import PATHS


class Retriever:
    """
    High-level retrieval orchestrator.

    Parameters
    ----------
    persist_dir : Optional[str]
        Directory for the NumPy vector store snapshots. Defaults to PATHS['vector_pkls'].
    embedder : Optional[Embedder]
        Custom embedder instance. If None, a default Embedder() is created.
    store : Optional[VectorStoreNP]
        Custom VectorStoreNP instance. If None, a default store is opened at `persist_dir`.
    reranker : Optional[Reranker]
        Optional cross-encoder reranker; if None, rerank step is skipped.
    """

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        embedder: Optional[Embedder] = None,
        store: Optional[VectorStoreNP] = None,
        reranker: Optional[Reranker] = None,
    ) -> None:
        self._persist_dir = persist_dir or str(PATHS["vector_pkls"])
        self._emb = embedder or Embedder()
        self._vs = store or VectorStoreNP(self._persist_dir)
        self._reranker = reranker or Reranker()

    # ---- public API ----
    def retrieve(self, query: str, k: int = 10, do_rerank: bool = True) -> List[DocScore]:
        """
        Retrieve top-k candidates for a query as `DocScore(id, score)`.

        Steps:
        1) Embed the query.
        2) Ask the vector store for candidate ids (k).
        3) Compute cosine scores for these ids (when store internals available).
        4) Optional rerank (order only), preserving computed scores.
        5) Return `DocScore` list (length ≤ k).

        Notes:
        - If no vectors are present, returns [].
        - If reranker is a no-op (current placeholder), order remains unchanged.
        """
        if not query or not isinstance(query, str):
            return []

        vecs = self._emb.embed([query])
        if not vecs:
            return []
        q = np.asarray(vecs[0], dtype=np.float32)
        if q.ndim != 1:
            q = q.reshape(-1)

        # Ask store for candidate ids (VectorStoreNP performs exact-cosine top-k by ids)
        ids: List[str] = self._vs.query(q.tolist(), k=k)  # type: ignore[arg-type]

        if not ids:
            return []

        # Compute cosine scores for the candidate ids when VectorStoreNP internals are available.
        scores = self._compute_cosine_scores(ids, q)

        # Optional rerank (RET-02). Current Reranker returns ids order; we preserve the computed scores.
        if do_rerank and self._reranker is not None:
            try:
                reranked_ids = self._reranker.rerank(ids, query)
                # Keep only ids we have scores for, preserve reranked order.
                ordered = [(i, scores.get(i, 0.0)) for i in reranked_ids if i in scores]
            except Exception:
                # Fail-safe: skip rerank on any error.
                ordered = [(i, scores.get(i, 0.0)) for i in ids]
        else:
            ordered = [(i, scores.get(i, 0.0)) for i in ids]

        # Truncate to k and wrap as DocScore
        ordered = ordered[: max(0, int(k))]
        return [DocScore(id=doc_id, score=float(sc)) for doc_id, sc in ordered]

    # ---- helpers ----
    def _compute_cosine_scores(self, ids: Sequence[str], q: np.ndarray) -> dict[str, float]:
        """
        Compute cosine similarity for a set of ids against query vector q using
        VectorStoreNP internal arrays when available. Falls back to 0.0 if not.
        """
        scores: dict[str, float] = {}
        # Use VectorStoreNP internals if present.
        emb = getattr(self._vs, "_emb", None)
        id2idx = getattr(self._vs, "_id2idx", None)
        if emb is None or id2idx is None:
            # No access to raw vectors (e.g., future Chroma backend).
            for _id in ids:
                scores[_id] = 0.0
            return scores

        A = np.asarray(emb, dtype=np.float32)  # (N, D)
        if A.ndim != 2 or A.size == 0:
            for _id in ids:
                scores[_id] = 0.0
            return scores

        qn = float(np.linalg.norm(q) + 1e-12)
        # Compute per-id cosine using the stored row corresponding to id.
        for _id in ids:
            idx = id2idx.get(_id, None)
            if idx is None:
                scores[_id] = 0.0
                continue
            v = A[idx]
            vn = float(np.linalg.norm(v) + 1e-12)
            sim = float(np.dot(v, q) / (vn * qn))
            # Clip to [-1, 1] to avoid tiny numerical overshoots.
            if sim > 1.0:
                sim = 1.0
            elif sim < -1.0:
                sim = -1.0
            scores[_id] = sim
        return scores
```


## /home/rusbeh_ab/project/RAGstream/ragstream/memory

### ~\ragstream\memory\conversation_memory.py
```python
"""
ConversationMemory (read-only)
==============================
Two-layer history:
- Layer-G: recency window (last k turns), always available.
- Layer-E: episodic store with metadata (on-topic, soft fading).
Not part of the document store; no embeddings/retrieval.
"""
from typing import List, Tuple

class ConversationMemory:
    def __init__(self, k_default: int = 5) -> None:
        self.k_default = k_default
        self.soft_fading = True
        self.conflict_policy = "FILES>newer>older"

    def get_recent(self, k: int | None = None) -> List[Tuple[str, str]]:
        return []

    def get_episodic(self) -> List[Tuple[str, str]]:
        return []
```


## /home/rusbeh_ab/project/RAGstream/ragstream/utils

### ~\ragstream\utils\logging.py
```python
"""
SimpleLogger
============
Ultra-light façade for the standard logging module.
Use for ephemeral console messages only (no persistent logs by requirement).
"""
import logging

class SimpleLogger:
    _logger = logging.getLogger("ragstream")
    if not _logger.handlers:
        _logger.setLevel(logging.INFO)
        _h = logging.StreamHandler()
        _h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s : %(message)s"))
        _logger.addHandler(_h)

    @classmethod
    def log(cls, msg: str) -> None:
        cls._logger.info(msg)

    @classmethod
    def error(cls, msg: str) -> None:
        cls._logger.error(msg)
```

### ~\ragstream\utils\paths.py
```python
"""
Paths
=====
Centralises on-disk locations so a single import
(`from ragstream.utils.paths import PATHS`) gives typed access.
"""
from pathlib import Path
from typing import TypedDict

class _Paths(TypedDict):
    root:        Path
    data:        Path
    raw_docs:    Path
    chroma_db:   Path
    vector_pkls: Path
    logs:        Path

ROOT = Path(__file__).resolve().parents[2]

PATHS: _Paths = {
    "root":        ROOT,
    "data":        ROOT / "data",
    "raw_docs":    ROOT / "data" / "doc_raw",
    "chroma_db":   ROOT / "data" / "chroma_db",   # planned
    "vector_pkls": ROOT / "data" / "vector_pkls", # current persistence
    "logs":        ROOT / "logs",                 # present as a path; no persistent logging required
}
```

