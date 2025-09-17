# -*- coding: utf-8 -*-
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
