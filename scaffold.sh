#!/usr/bin/env bash
set -euo pipefail

################################################################################
# 1) Directory scaffolding (aligned with Architecture_2 + UML)
################################################################################
mkdir -p ragstream/{app,config,ingestion,retrieval,orchestration,memory,utils}
mkdir -p data/{doc_raw,chroma_db,vector_pkls}

# ensure each package is import-ready
touch ragstream/__init__.py \
      ragstream/app/__init__.py \
      ragstream/config/__init__.py \
      ragstream/ingestion/__init__.py \
      ragstream/retrieval/__init__.py \
      ragstream/orchestration/__init__.py \
      ragstream/memory/__init__.py \
      ragstream/utils/__init__.py

################################################################################
# 2) Utils
################################################################################
cat > ragstream/utils/paths.py <<'PY'
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
PY

cat > ragstream/utils/logging.py <<'PY'
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
PY

################################################################################
# 3) Config
################################################################################
cat > ragstream/config/settings.py <<'PY'
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
PY

################################################################################
# 4) Ingestion layer
################################################################################
cat > ragstream/ingestion/loader.py <<'PY'
"""
DocumentLoader
==============
Discover and load raw files from *data/doc_raw*.
"""
from pathlib import Path
from typing import List

class DocumentLoader:
    def __init__(self, root: Path) -> None:
        self.root = root

    def load_documents(self) -> List[str]:
        """Return a list of file paths (stub)."""
        return []
PY

cat > ragstream/ingestion/chunker.py <<'PY'
"""
Chunker
=======
Token-aware overlapping splitter.
"""
from typing import List

class Chunker:
    def split(self, text: str, chunk_size: int = 1024, overlap: int = 200) -> List[str]:
        """Return list of overlapping chunks (stub)."""
        return []
PY

cat > ragstream/ingestion/embedder.py <<'PY'
"""
Embedder
========
Wrap an embedding model to convert text into dense vectors.
"""
from typing import List

class Embedder:
    def embed(self, texts: List[str]) -> List[list[float]]:
        """Return embedding vectors (stub)."""
        return []
PY

cat > ragstream/ingestion/vector_store.py <<'PY'
"""
VectorStore (interface + NP/Chroma sketches)
============================================
NumPy .pkl is the current persistence; Chroma is planned.
"""
from typing import List, Dict, Any

class IVectorStore:
    def add(self, ids: List[str], vectors: List[list[float]], meta: List[Dict[str, Any]]) -> None: ...
    def query(self, vector: list[float], k: int = 10) -> List[str]: ...
    def snapshot(self, ts: str) -> None: ...

class VectorStoreNP(IVectorStore):
    def __init__(self, persist_path: str) -> None:
        self.persist_path = persist_path
    def add(self, ids, vectors, meta) -> None: return None
    def query(self, vector, k: int = 10) -> List[str]: return []
    def snapshot(self, ts: str) -> None: return None

class VectorStoreChroma(IVectorStore):
    """Planned on-disk Chroma collection (enabled when environment allows)."""
    def add(self, ids, vectors, meta) -> None: return None
    def query(self, vector, k: int = 10) -> List[str]: return []
    def snapshot(self, ts: str) -> None: return None
PY

################################################################################
# 5) Retrieval layer
################################################################################
cat > ragstream/retrieval/attention.py <<'PY'
"""
AttentionWeights (legacy)
=========================
Kept for compatibility; not central in current eligibility model.
"""
from typing import Dict

class AttentionWeights:
    def weight(self, scores: Dict[str, float]) -> Dict[str, float]:
        return scores
PY

cat > ragstream/retrieval/reranker.py <<'PY'
"""
Reranker
========
Cross-encoder reranking placeholder.
"""
from typing import List

class Reranker:
    def rerank(self, ids: List[str], query: str) -> List[str]:
        return ids
PY

cat > ragstream/retrieval/retriever.py <<'PY'
"""
Retriever
=========
Coordinates vector search and reranking; controller handles Exact File Lock and eligibility pool.
"""
from typing import List

class DocScore:
    def __init__(self, doc_id: str, score: float) -> None:
        self.id = doc_id
        self.score = score

class Retriever:
    def retrieve(self, query: str, k: int = 10) -> List[DocScore]:
        return []
PY

################################################################################
# 6) Conversation Memory (read-only)
################################################################################
cat > ragstream/memory/conversation_memory.py <<'PY'
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
PY

################################################################################
# 7) Orchestration layer
################################################################################
cat > ragstream/orchestration/prompt_builder.py <<'PY'
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
PY

cat > ragstream/orchestration/llm_client.py <<'PY'
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
PY

################################################################################
# 8) Agents
################################################################################
cat > ragstream/app/agents.py <<'PY'
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
PY

################################################################################
# 9) Controller & UI
################################################################################
cat > ragstream/app/controller.py <<'PY'
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
PY

cat > ragstream/app/ui_streamlit.py <<'PY'
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
PY

################################################################################
echo "RAGstream scaffold written (Tooling removed, ConversationMemory added, A2 audit & bounded re-run wired)."
