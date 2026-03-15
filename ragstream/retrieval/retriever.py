# -*- coding: utf-8 -*-
"""
retriever.py

Purpose:
    Deterministic Retrieval stage for RAGstream.

Scope of this file:
    - Read retrieval query text from the current SuperPrompt
      (TASK / PURPOSE / CONTEXT).
    - Split that retrieval query into overlapping query pieces.
    - Open the active project's Chroma document store.
    - Compare every stored chunk embedding against all query-piece embeddings.
    - Aggregate per-chunk similarities with LogAvgExp (tau = 9).
    - Keep the top-k chunks.
    - Hydrate real Chunk objects from doc_raw using the same chunking logic
      as ingestion.
    - Write the Retrieval stage result back into the same SuperPrompt.

Non-goals:
    - No reranking here.
    - No A3 filtering here.
    - No GUI rendering here.
    - No final prompt composition here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from ragstream.ingestion.chunker import Chunker
from ragstream.ingestion.embedder import Embedder
from ragstream.ingestion.vector_store_chroma import VectorStoreChroma
from ragstream.orchestration.super_prompt import A3ChunkStatus, SuperPrompt
from ragstream.retrieval.chunk import Chunk
from ragstream.retrieval.doc_score import DocScore  # compatibility re-export

# Keep old import compatibility:
# from ragstream.retrieval.retriever import DocScore
DocScore = DocScore


# ---------------------------------------------------------------------
# Module-level retrieval defaults
# ---------------------------------------------------------------------

# Fallback number of chunks to keep if the caller gives no valid top-k.
DEFAULT_TOP_K = 100

# Retrieval query splitting reuses the same deterministic windowing idea
# as ingestion. These values MUST stay aligned with the active ingestion
# chunking contract unless you intentionally change both sides together.
DEFAULT_QUERY_CHUNK_SIZE = 500
DEFAULT_QUERY_OVERLAP = 100

# Agreed retrieval aggregation constant:
# score(chunk) = tau * log(mean(exp(sim_i / tau)))
DEFAULT_LOGAVGEXP_TAU = 9.0


class Retriever:
    """
    Deterministic Retrieval stage for document chunks.

    Design:
    - Keep this class stateless with respect to pipeline history.
      The evolving pipeline state lives in SuperPrompt.
    - This class only reads the current SuperPrompt, computes retrieval,
      and writes the retrieval result back into the same SuperPrompt.
    - The controller decides when to call this class.
    """

    def __init__(
        self,
        *,
        doc_root: str,
        chroma_root: str,
        embedder: Embedder | None = None,
        chunker: Chunker | None = None,
    ) -> None:
        """
        Initialize Retrieval with explicit project roots and shared helpers.

        Args:
            doc_root:
                Absolute path to the doc_raw root folder.
                Example: .../data/doc_raw
            chroma_root:
                Absolute path to the chroma_db root folder.
                Example: .../data/chroma_db
            embedder:
                Optional shared Embedder instance. If omitted, a default one is created.
            chunker:
                Optional shared Chunker instance. If omitted, a default one is created.
        """
        self.doc_root = Path(doc_root).resolve()
        self.chroma_root = Path(chroma_root).resolve()

        self.embedder = embedder if embedder is not None else Embedder(model="text-embedding-3-large")
        self.chunker = chunker if chunker is not None else Chunker()

        # Keep the chunk class explicit so hydration remains readable and testable.
        self.chunk_cls = Chunk

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def run(self, sp: SuperPrompt, project_name: str, top_k: int) -> SuperPrompt:
        """
        Execute the Retrieval stage and update the same SuperPrompt in place.

        Inputs:
            sp:
                The current evolving SuperPrompt, typically after PreProcessing / A2.
            project_name:
                The active project selected in the GUI.
            top_k:
                Number of chunks to keep after retrieval ranking.

        Returns:
            The same SuperPrompt instance, mutated in place.

        Effects on SuperPrompt:
            - Writes hydrated Chunk objects into sp.base_context_chunks
            - Writes the retrieval stage snapshot into sp.views_by_stage["retrieval"]
            - Writes ordered chunk IDs into sp.final_selection_ids
            - Appends "retrieval" to sp.history_of_stages
            - Sets sp.stage = "retrieval"
        """
        if sp is None:
            raise ValueError("Retriever.run: 'sp' must not be None")

        project_name = (project_name or "").strip()
        if not project_name:
            raise ValueError("Retriever.run: project_name must not be empty")

        if not self.doc_root.exists():
            raise FileNotFoundError(f"Retriever.run: doc_root does not exist: {self.doc_root}")

        project_db_dir = self.chroma_root / project_name
        if not project_db_dir.exists():
            raise FileNotFoundError(
                f"Retriever.run: active project Chroma DB does not exist: {project_db_dir}"
            )

        query_text = self._build_query_text(sp)
        if not query_text:
            raise ValueError(
                "Retriever.run: retrieval query is empty. "
                "At least one of TASK / PURPOSE / CONTEXT must be present."
            )

        query_pieces = self._split_query_into_pieces(
            query_text=query_text,
            chunk_size=DEFAULT_QUERY_CHUNK_SIZE,
            overlap=DEFAULT_QUERY_OVERLAP,
        )

        ranked_rows = self._retrieve_and_rank(
            project_name=project_name,
            query_pieces=query_pieces,
            top_k=top_k,
        )

        valid_ranked_rows, hydrated_chunks = self._hydrate_ranked_chunks(ranked_rows)
        self._write_stage_to_superprompt(sp, valid_ranked_rows, hydrated_chunks)

        return sp

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _build_query_text(self, sp: SuperPrompt) -> str:
        """
        Build the retrieval query text from the structured SuperPrompt body.

        Current design choice:
        - Use only TASK / PURPOSE / CONTEXT.
        - Keep the order explicit and stable.
        - Skip empty fields.
        """
        blocks: List[str] = []

        task = (sp.body.get("task") or "").strip()
        purpose = (sp.body.get("purpose") or "").strip()
        context = (sp.body.get("context") or "").strip()

        if task:
            blocks.append("## TASK")
            blocks.append(task)
            blocks.append("")

        if purpose:
            blocks.append("## PURPOSE")
            blocks.append(purpose)
            blocks.append("")

        if context:
            blocks.append("## CONTEXT")
            blocks.append(context)
            blocks.append("")

        return "\n".join(blocks).strip()

    def _split_query_into_pieces(
        self,
        *,
        query_text: str,
        chunk_size: int,
        overlap: int,
    ) -> List[str]:
        """
        Split the retrieval query into overlapping query pieces.

        We intentionally reuse the same deterministic chunking idea as ingestion
        so the prompt side and document side follow the same windowing culture.
        """
        query_text = (query_text or "").strip()
        if not query_text:
            return []

        pieces = self.chunker.split(
            file_path="__prompt__",
            text=query_text,
            chunk_size=chunk_size,
            overlap=overlap,
        )

        return [chunk_text for _fp, chunk_text in pieces if (chunk_text or "").strip()]

    def _retrieve_and_rank(
        self,
        *,
        project_name: str,
        query_pieces: List[str],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """
        Read all stored chunk embeddings from the active project Chroma DB,
        score them against all query pieces, aggregate with LogAvgExp, and keep top-k.

        Return format:
            List of dictionaries, one per selected chunk:
            {
                "id": <chunk_id>,
                "score": <retrieval_score>,
                "status": A3ChunkStatus.SELECTED,
                "meta": <stored metadata dict>
            }

        Notes:
        - This stage is deterministic.
        - No reranking happens here.
        - We read ALL stored chunk embeddings because the agreed Retrieval stage
          should compute its own final ranking across the complete project store.
        """
        if not query_pieces:
            return []

        k = int(top_k) if int(top_k) > 0 else DEFAULT_TOP_K

        store = VectorStoreChroma(persist_dir=str(self.chroma_root / project_name))

        raw = store.collection.get(include=["embeddings", "metadatas"])
        ids: List[str] = raw.get("ids", []) if raw else []
        metadatas: List[Dict[str, Any] | None] = raw.get("metadatas", []) if raw else []
        embeddings = raw.get("embeddings", []) if raw else []

        # embeddings may come back as a NumPy array, so never test it with
        # "if not embeddings". Use explicit length checks instead.
        if len(ids) == 0 or len(embeddings) == 0:
            return []

        if len(ids) != len(embeddings):
            raise RuntimeError(
                "Retriever._retrieve_and_rank: Chroma returned mismatched ids/embeddings lengths"
            )

        if len(metadatas) > 0 and len(metadatas) != len(ids):
            raise RuntimeError(
                "Retriever._retrieve_and_rank: Chroma returned mismatched ids/metadatas lengths"
            )

        query_vectors = self.embedder.embed(query_pieces)

        # query_vectors may also be array-like, so use explicit length checks.
        if len(query_vectors) == 0:
            return []

        A = np.asarray(embeddings, dtype=np.float32)    # stored chunks: [N, D]
        Q = np.asarray(query_vectors, dtype=np.float32) # query pieces:  [M, D]

        if A.ndim != 2 or Q.ndim != 2:
            raise RuntimeError(
                "Retriever._retrieve_and_rank: unexpected embedding dimensions returned by Chroma/OpenAI"
            )

        if A.shape[1] != Q.shape[1]:
            raise RuntimeError(
                "Retriever._retrieve_and_rank: stored vectors and query vectors have different dimensions"
            )

        # Normalize rows to compute cosine similarity as a matrix product.
        # Similarities shape: [N_chunks, M_query_pieces]
        A_norm = A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-12)
        Q_norm = Q / (np.linalg.norm(Q, axis=1, keepdims=True) + 1e-12)
        sims = A_norm @ Q_norm.T

        # LogAvgExp aggregation over the query-piece axis.
        # score(chunk) = tau * log(mean(exp(sim_i / tau)))
        tau = float(DEFAULT_LOGAVGEXP_TAU)
        aggregated_scores = tau * np.log(np.mean(np.exp(sims / tau), axis=1))

        rows: List[Dict[str, Any]] = []
        for idx, chunk_id in enumerate(ids):
            meta = metadatas[idx] if (len(metadatas) > 0 and metadatas[idx] is not None) else {}
            rows.append(
                {
                    "id": chunk_id,
                    "score": float(aggregated_scores[idx]),
                    "status": A3ChunkStatus.SELECTED,
                    "meta": meta,
                }
            )

        # Deterministic sort:
        # 1) higher score first
        # 2) stable fallback by chunk_id
        rows.sort(key=lambda row: (-row["score"], row["id"]))

        return rows[: min(k, len(rows))]

    def _hydrate_ranked_chunks(
        self,
        ranked_rows: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], List[Chunk]]:
        """
        Reconstruct real Chunk objects for the selected ranked rows.

        Why reconstruction is needed:
        - Chroma stores embeddings + metadata only.
        - The actual chunk text must therefore be rebuilt from doc_raw
          using the same chunker and the stored chunk_idx.

        Important robustness rule:
        - If one retrieved row points to a stale or broken source file,
          we skip that row instead of crashing the whole Retrieval stage.

        Returns:
            (valid_ranked_rows, hydrated_chunks)

            valid_ranked_rows:
                Only the rows that could be reconstructed successfully.
            hydrated_chunks:
                Chunk objects aligned 1:1 with valid_ranked_rows.
        """
        valid_ranked_rows: List[Dict[str, Any]] = []
        hydrated: List[Chunk] = []

        # Local caches avoid re-reading and re-splitting the same source file
        # when several retrieved chunks come from that file.
        text_cache: Dict[str, str] = {}
        split_cache: Dict[str, List[tuple[str, str]]] = {}

        step = DEFAULT_QUERY_CHUNK_SIZE - DEFAULT_QUERY_OVERLAP

        for row in ranked_rows:
            chunk_id = row["id"]
            meta = row.get("meta", {}) or {}

            rel_path = str(meta.get("path") or "").strip()
            if not rel_path:
                continue

            raw_path = self.doc_root / rel_path
            if not raw_path.exists():
                continue

            chunk_idx_raw = meta.get("chunk_idx")
            if chunk_idx_raw is None:
                continue

            chunk_idx = int(chunk_idx_raw)

            cache_key = raw_path.as_posix()
            if cache_key not in text_cache:
                text_cache[cache_key] = raw_path.read_text(encoding="utf-8", errors="ignore")

            if cache_key not in split_cache:
                split_cache[cache_key] = self.chunker.split(
                    file_path=str(raw_path),
                    text=text_cache[cache_key],
                    chunk_size=DEFAULT_QUERY_CHUNK_SIZE,
                    overlap=DEFAULT_QUERY_OVERLAP,
                )

            all_chunks_for_file = split_cache[cache_key]
            if chunk_idx < 0 or chunk_idx >= len(all_chunks_for_file):
                continue

            _fp, snippet = all_chunks_for_file[chunk_idx]

            source_text = text_cache[cache_key]
            start = chunk_idx * step
            end = min(start + DEFAULT_QUERY_CHUNK_SIZE, len(source_text))

            chunk_obj = self.chunk_cls(
                id=chunk_id,
                source=rel_path,
                snippet=snippet,
                span=(start, end),
                meta=dict(meta),
            )

            valid_ranked_rows.append(row)
            hydrated.append(chunk_obj)

        return valid_ranked_rows, hydrated

    def _write_stage_to_superprompt(
        self,
        sp: SuperPrompt,
        ranked_rows: List[Dict[str, Any]],
        hydrated_chunks: List[Chunk],
    ) -> None:
        """
        Persist the Retrieval result into the evolving SuperPrompt.

        Write-back contract for this stage:
        - base_context_chunks:
            the hydrated Chunk objects in retrieval order
        - views_by_stage["retrieval"]:
            ordered triples (chunk_id, retrieval_score, SELECTED)
        - final_selection_ids:
            ordered chunk IDs from the current retrieval result
        - stage/history:
            bookkeeping for the pipeline lifecycle
        """
        if len(ranked_rows) != len(hydrated_chunks):
            raise RuntimeError(
                "Retriever._write_stage_to_superprompt: ranked_rows and hydrated_chunks length mismatch"
            )

        sp.base_context_chunks = list(hydrated_chunks)

        retrieval_view: List[tuple[str, float, A3ChunkStatus]] = []
        final_ids: List[str] = []

        for row in ranked_rows:
            chunk_id = str(row["id"])
            score = float(row["score"])
            status = row["status"]

            retrieval_view.append((chunk_id, score, status))
            final_ids.append(chunk_id)

        sp.views_by_stage["retrieval"] = retrieval_view
        sp.final_selection_ids = final_ids
        sp.stage = "retrieval"
        sp.history_of_stages.append("retrieval")