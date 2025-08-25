# Python Files Index (ragstream)

## C:\0000\Prompt_Engineering\Projects\GTPRusbeh\RAGstream2\ragstream\app

### ~\ragstream\app\agents.py
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

class A2_PromptShaper:
    def propose(self, question: str) -> Dict[str, str]:
        return {"intent": "explain", "domain": "software"}

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
Glue code between Streamlit UI, eligibility controls (ON/OFF + Exact File Lock),
retrieval pipeline, agents A1..A4, tooling dispatcher, and LLM client.
"""
from .agents import A1DCI, A2PromptShaper, A3NliGate, A4Condenser

class AppController:
def init(self, retriever, reranker, prompt_builder, llm_client):
self.shaper = A2PromptShaper()
self.dci = A1DCI()
self.gate = A3NliGate(theta=0.6)
self.condenser = A4Condenser()
self.retriever = retriever
self.reranker = reranker
self.prompt_builder = prompt_builder
self.llm = llm_client

def handle(self, user_prompt, named_files, exact_lock):
    shape = self.shaper.suggest(user_prompt)
    files = self.dci.build_files_block(named_files, exact_lock)
    kept = []
    if not exact_lock:
        dense = self.retriever.search(user_prompt)
        ranked = self.reranker.rerank(user_prompt, dense)
        kept = self.gate.filter(user_prompt, ranked)
    sctx = self.condenser.make_sctx(kept)
    prompt = self.prompt_builder.build(user_prompt, files, sctx, shape)
    return self.llm.send(prompt)
```

### ~\ragstream\app\ui_streamlit.py
```python
"""
StreamlitUI
===========
Defines the visible Streamlit components (prompt box, file ON/OFF controls,
Exact File Lock toggle, Prompt Shaper panel, agent toggles, Super-Prompt preview,
transparency/cost panes) and wires them to `AppController`.
"""
import streamlit as st
from ragstream.app.controller import AppController

class StreamlitUI:
    """Thin Streamlit wrapper – all logic stays in **AppController**."""
    def __init__(self) -> None:
        self.ctrl = AppController()

    def render(self) -> None:
        """Draws UI components and handles callbacks."""
        st.title("RAG Stream")
        st.write("UI placeholder (Prompt box, ON/OFF file checkboxes, Exact File Lock, agent toggles, Super-Prompt preview)")
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


## C:\0000\Prompt_Engineering\Projects\GTPRusbeh\RAGstream2\ragstream\config

### ~\ragstream\config\settings.py
```python
"""
Settings
========
Loads environment variables **once** at start-up so that every module accesses
configuration via Settings.get("OPENAI_API_KEY") instead of scattered os.getenv.
"""
import os
from typing import Any, Dict

class Settings:
    """
    Thin, immutable wrapper around `os.environ`.

    *Purpose*: centralise **all** config keys (API keys, flags, paths) and offer
    a single interface for default values & type-checking.
    """
    _CACHE: Dict[str, Any] = {}

    @classmethod
    def get(cls, key: str, default: Any | None = None) -> Any:
        """Return env value or *default*; cache the lookup."""
        if key not in cls._CACHE:
            cls._CACHE[key] = os.getenv(key, default)
        return cls._CACHE[key]
```


## C:\0000\Prompt_Engineering\Projects\GTPRusbeh\RAGstream2\ragstream\ingestion

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

### ~\ragstream\ingestion\vector_store.py
```python
# -*- coding: utf-8 -*-
"""
VectorStore (router)
====================
On Windows (default): use pure NumPy exact-cosine backend (no native deps).
On non-Windows or when RAG_FORCE_CHROMA=1: use Chroma (PersistentClient).
"""

from __future__ import annotations
import os, sys
from typing import List, Dict

if sys.platform.startswith("win") and os.getenv("RAG_FORCE_CHROMA") != "1":
    # Windows default: native-free store
    from .vector_store_pure import VectorStorePure as VectorStore  # re-export
else:
    # Non-Windows (or forced): Chroma embedded client
    from chromadb import PersistentClient

    class VectorStore:
        def __init__(self, persist_dir: str) -> None:
            self.client = PersistentClient(path=persist_dir)
            self.collection = self.client.get_or_create_collection(
                name="rag_vectors",
                embedding_function=None  # embeddings are precomputed
            )

        def add(self, ids: List[str], vectors: List[List[float]], meta: List[Dict]) -> None:
            if not ids or not vectors:
                return
            self.collection.add(ids=ids, embeddings=vectors, metadatas=meta)

        def query(self, vector: List[float], k: int = 10) -> List[str]:
            res = self.collection.query(query_embeddings=[vector], n_results=k)
            return res.get("ids", [[]])[0]

        def snapshot(self, timestamp: str) -> None:
            # Chroma persists continuously; no-op here.
            return
```

### ~\ragstream\ingestion\vector_store_np.py
```python
from __future__ import annotations
import pickle
from pathlib import Path
from typing import List, Dict, Tuple
import numpy as np

class VectorStoreNP:
    """
    Exact-cosine vector store with NumPy only.
    Persists to a single pickle under the *given persist_dir*.
    Safe on locked Windows machines (no native DLLs).
    """

    def __init__(self, persist_dir: str) -> None:
        self.persist_path = Path(persist_dir)
        self.persist_path.mkdir(parents=True, exist_ok=True)
        self.db_file = self.persist_path / "store.pkl"
        self._ids: List[str] = []
        self._meta: List[Dict] = []
        self._emb: np.ndarray | None = None  # shape (N, D)
        self._id2idx: Dict[str, int] = {}
        self._load()

    def add(self, ids: List[str], vectors: List[List[float]], meta: List[Dict]) -> None:
        if not ids or not vectors:
            return
        if len(ids) != len(vectors):
            raise ValueError("ids and vectors length mismatch")
        if meta and len(meta) != len(ids):
            raise ValueError("meta length must match ids (or be empty)")

        X = np.asarray(vectors, dtype=np.float32)
        if X.ndim != 2:
            raise ValueError("vectors must be 2D [N, D]")

        new_rows: List[Tuple[str, Dict, np.ndarray]] = []
        for i, id_ in enumerate(ids):
            m = meta[i] if meta else {}
            if id_ in self._id2idx:
                idx = self._id2idx[id_]
                self._emb[idx] = X[i]
                self._meta[idx] = m
            else:
                new_rows.append((id_, m, X[i]))

        if new_rows:
            ids_new, meta_new, emb_new = zip(*new_rows)
            emb_new = np.stack(emb_new, axis=0).astype(np.float32)
            if self._emb is None:
                self._emb = emb_new
            else:
                self._emb = np.concatenate([self._emb, emb_new], axis=0)
            start = len(self._ids)
            self._ids.extend(ids_new)
            self._meta.extend(meta_new)
            for j, id_ in enumerate(ids_new):
                self._id2idx[id_] = start + j

        self._save()

    def query(self, vector: List[float], k: int = 10) -> List[str]:
        if self._emb is None or len(self._ids) == 0:
            return []
        q = np.asarray(vector, dtype=np.float32)
        if q.ndim != 1:
            raise ValueError("query vector must be 1D")

        A = self._emb
        qn = float(np.linalg.norm(q) + 1e-12)
        An = np.linalg.norm(A, axis=1) + 1e-12
        sims = (A @ q) / (An * qn)

        k = max(1, min(int(k), sims.shape[0]))
        idx = np.argpartition(-sims, k - 1)[:k]
        idx = idx[np.argsort(-sims[idx])]
        return [self._ids[i] for i in idx.tolist()]

    def snapshot(self, timestamp: str) -> None:
        if self.db_file.exists():
            dst = self.persist_path / f"store_{timestamp}.pkl"
            dst.write_bytes(self.db_file.read_bytes())

    # ---- internal persistence ----
    def _save(self) -> None:
        data = {"ids": self._ids, "meta": self._meta, "emb": self._emb}
        with open(self.db_file, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

    def _load(self) -> None:
        if not self.db_file.exists():
            return
        with open(self.db_file, "rb") as f:
            data = pickle.load(f)
        self._ids  = list(data.get("ids", []))
        self._meta = list(data.get("meta", []))
        emb = data.get("emb", None)
        self._emb = emb if emb is None else np.asarray(emb, dtype=np.float32)
        self._id2idx = {id_: i for i, id_ in enumerate(self._ids)}
```


## C:\0000\Prompt_Engineering\Projects\GTPRusbeh\RAGstream2\ragstream\orchestration

### ~\ragstream\orchestration\llm_client.py
```python
"""
LLMClient
=========
Thin adapter around OpenAI (or local model) providing streaming & retry.
Also exposes a basic cost estimator for UI display.
"""
class LLMClient:
    """Handles completion calls and cost estimation."""
    def complete(self, prompt: str) -> str:
        """Return LLM answer (dummy)."""
        return "ANSWER"

    def estimate_cost(self, tokens: int) -> float:
        """Rough USD cost estimate based on model pricing."""
        return 0.0
```

### ~\ragstream\orchestration\prompt_builder.py
```python
"""
PromptBuilder
=============
Assembles the final Super-Prompt from:
  - ❖ FILES (deterministic block by A1)
  - S_ctx (Facts / Constraints / Open Issues by A4)
  - tool_output (if any)
and applies the fixed authority order:
[Hard Rules] → [Project Memory] → [❖ FILES] → [S_ctx] → [Task/Mode]
"""
from typing import List, Optional

class PromptBuilder:
    """Template-driven prompt composer."""
    def build(self, question: str, s_ctx: List[str], files_block: Optional[str] = None, tool: Optional[str] = None) -> str:
        """Return composed prompt (dummy)."""
        return "PROMPT"
```


## C:\0000\Prompt_Engineering\Projects\GTPRusbeh\RAGstream2\ragstream\retrieval

### ~\ragstream\retrieval\attention.py
```python
"""
AttentionWeights (legacy shim)
==============================
Kept for legacy tests. In the current design, eligibility is controlled via
ON/OFF per-file toggles and Exact File Lock in the UI, not sliders.
"""
from typing import Dict

class AttentionWeights:
    """No-op weight application kept for backward compatibility."""
    def weight(self, scores: Dict[str, float]) -> Dict[str, float]:
        return scores
```

### ~\ragstream\retrieval\reranker.py
```python
"""
Reranker
========
Cross-encoder that re-orders the initially retrieved chunks.
"""
from typing import List

class Reranker:
    """Cross-encoder interface."""
    def rerank(self, ids: List[str], query: str) -> List[str]:
        """Return list of IDs sorted by relevance (dummy)."""
        return ids
```

### ~\ragstream\retrieval\retriever.py
```python
"""
Retriever
=========
Coordinates vector search and reranking. In the new design, per-file eligibility
is handled in the controller (Exact File Lock / ON-OFF pool) before retrieval.
"""
from typing import List

class DocScore:
    """Lightweight value object pairing *doc_id* with *score*."""
    def __init__(self, doc_id: str, score: float) -> None:
        self.id = doc_id
        self.score = score

class Retriever:
    """End-to-end retrieval pipeline orchestrator."""
    def retrieve(self, query: str, k: int = 10) -> List[DocScore]:
        """Return reranked `DocScore` list (dummy)."""
        return []
```


## C:\0000\Prompt_Engineering\Projects\GTPRusbeh\RAGstream2\ragstream\tooling

### ~\ragstream\tooling\base_tool.py
```python
"""
BaseTool
========
Abstract base class for any local executable helper (math, python, shell …).
"""
class BaseTool:
    """Every concrete tool must implement `__call__`."""
    name: str = "base"

    def __call__(self, instruction: str) -> str:
        """Execute the tool and return textual output (dummy)."""
        return "<tool-output>"
```

### ~\ragstream\tooling\dispatcher.py
```python
"""
ToolDispatcher
==============
Detects `calc:` / `py:` prefixes in the user prompt and routes to the tool.
"""
from typing import Tuple

class ToolDispatcher:
    """Front controller for local tool execution."""
    def maybe_dispatch(self, prompt: str) -> Tuple[str, str]:
        """
        Returns (tool_output, stripped_prompt).
        If no tool prefix detected, tool_output = "".
        """
        return ("", prompt)
```

### ~\ragstream\tooling\math_tool.py
```python
"""
MathTool
========
Evaluates arithmetic expressions (safe subset) and returns the result.
"""
from ragstream.tooling.base_tool import BaseTool

class MathTool(BaseTool):
    """Protected SymPy evaluator."""
    name = "math"

    def __call__(self, instruction: str) -> str:
        """Parse and compute math expression (dummy)."""
        return "0"
```

### ~\ragstream\tooling\py_tool.py
```python
"""
PyTool
======
Executes short Python snippets inside a restricted sandbox.
"""
from ragstream.tooling.base_tool import BaseTool

class PyTool(BaseTool):
    """RestrictedPython sandbox executor."""
    name = "py"

    def __call__(self, instruction: str) -> str:
        """Execute code and capture stdout (dummy)."""
        return "<py-result>"
```

### ~\ragstream\tooling\registry.py
```python
"""
ToolRegistry
============
Discovers all subclasses of BaseTool and exposes them via .get(name).
"""
from typing import Dict
from ragstream.tooling.base_tool import BaseTool

class ToolRegistry:
    """Keeps a mapping `name -> tool_instance`."""
    _registry: Dict[str, BaseTool] = {}

    @classmethod
    def discover(cls) -> None:
        """Populate registry (dummy)."""
        return

    @classmethod
    def get(cls, name: str) -> BaseTool:
        """Return tool instance or raise KeyError."""
        return cls._registry[name]
```


## C:\0000\Prompt_Engineering\Projects\GTPRusbeh\RAGstream2\ragstream\utils

### ~\ragstream\utils\logging.py
```python
"""
SimpleLogger
============
Ultra-light wrapper around the built-in *logging* module so that the whole
code-base can depend on **one** unified logger without external config files.
"""
import logging

class SimpleLogger:
    """Minimal façade for standard logging (single responsibility: output)."""
    _logger = logging.getLogger("ragstream")
    if not _logger.handlers:
        _logger.setLevel(logging.INFO)
        _handler = logging.StreamHandler()
        _formatter = logging.Formatter("[%(asctime)s] %(levelname)s : %(message)s")
        _handler.setFormatter(_formatter)
        _logger.addHandler(_handler)

    @classmethod
    def log(cls, msg: str) -> None:
        """Write an *INFO* message (human-friendly)."""
        cls._logger.info(msg)

    @classmethod
    def error(cls, msg: str) -> None:
        """Write an *ERROR* message (something went wrong)."""
        cls._logger.error(msg)
```

### ~\ragstream\utils\paths.py
```python
"""
Paths
=====
Centralises all on-disk locations for the project so that a single import
(`from ragstream.utils.paths import PATHS`) provides **typed** access to
directories used across ingestion, vector store, caching, and logging.
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
    "logs":        ROOT / "logs",
}
```

