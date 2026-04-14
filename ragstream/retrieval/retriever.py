# retriever.py
# -*- coding: utf-8 -*-
"""
retriever.py

Purpose:
    Deterministic Retrieval stage orchestrator for RAGstream.

Design:
    - Keep Retriever as the top-level stage class used by the controller.
    - Keep query-building / query-splitting support logic outside this file.
    - Keep the dense retrieval backend in RetrieverEmb.
    - Add a parallel SPLADE retrieval backend in RetrieverSplade.
    - Merge both branches with deterministic RRF.
    - Keep hydration and SuperPrompt write-back in this file.
    - Preserve the current external Retriever.run(...) contract.

Current flow inside Retriever.run(...):
    1) PreProcessing
       - build retrieval query text from SuperPrompt
       - split the query into overlapping query pieces
    2) Retriever_EMB
       - run the dense embedding-based retrieval backend
    3) Retriever_SPLADE
       - score exactly the dense-selected candidate IDs
    4) RRF_Merger
       - fuse both ranked lists deterministically
    5) PostProcessing
       - hydrate ranked rows into real Chunk objects
       - write the retrieval result into SuperPrompt
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from ragstream.ingestion.chunker import Chunker
from ragstream.ingestion.embedder import Embedder
from ragstream.ingestion.splade_embedder import SpladeEmbedder
from ragstream.orchestration.super_prompt import A3ChunkStatus, SuperPrompt
from ragstream.orchestration.superprompt_projector import SuperPromptProjector
from ragstream.retrieval.chunk import Chunk
from ragstream.retrieval.doc_score import DocScore  # compatibility re-export
from ragstream.retrieval.retriever_emb import RetrieverEmb
from ragstream.retrieval.retriever_splade import RetrieverSplade
from ragstream.retrieval.rrf_merger import rrf_merge
from ragstream.retrieval.smart_query_splitter import split_query_into_pieces


# Keep old import compatibility:
# from ragstream.retrieval.retriever import DocScore
DocScore = DocScore

# Ranked row returned by RetrieverEmb / RetrieverSplade / RRF merger:
# (chunk_id, retrieval_score, metadata)
RankedRow = Tuple[str, float, Dict[str, Any]]

# Retrieval query splitting defaults.
# These MUST stay aligned with the current behavior so that the refactor
# preserves the same practical output as before.
DEFAULT_QUERY_CHUNK_SIZE = 1200
DEFAULT_QUERY_OVERLAP = 120


class Retriever:
    """
    Deterministic Retrieval stage orchestrator for document chunks.

    Design:
    - Keep this class focused on stage orchestration.
    - Keep low-level retrieval engine logic outside this file.
    - Keep hydration + SuperPrompt write-back here.
    - The evolving pipeline state still lives in SuperPrompt.
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
            chroma_root:
                Absolute path to the chroma_db root folder.
            embedder:
                Optional shared Embedder instance.
            chunker:
                Optional shared Chunker instance.
        """
        self.doc_root = Path(doc_root).resolve()
        self.chroma_root = Path(chroma_root).resolve()

        # SPLADE DB is kept parallel to chroma_db under the same data root.
        self.splade_root = self.chroma_root.parent / "splade_db"

        self.embedder = embedder if embedder is not None else Embedder(model="text-embedding-3-large")
        self.chunker = chunker if chunker is not None else Chunker()

        # Keep the chunk class explicit so hydration remains readable and testable.
        self.chunk_cls = Chunk

        # Dense backend remains unchanged and independent.
        self.retriever_emb = RetrieverEmb(
            chroma_root=str(self.chroma_root),
            embedder=self.embedder,
        )

        # Lazy init for SPLADE so app startup does not immediately load the sparse model.
        self._splade_embedder: SpladeEmbedder | None = None
        self._retriever_splade: RetrieverSplade | None = None

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def run(self, sp: SuperPrompt, project_name: str, top_k: int) -> SuperPrompt:
        """
        Execute the Retrieval stage and update the same SuperPrompt in place.

        Visible flow:
            1) PreProcessing
            2) Retriever_EMB
            3) Retriever_SPLADE
            4) RRF_Merger
            5) PostProcessing

        Returns:
            The same SuperPrompt instance, mutated in place.
        """
        query_pieces = self._preprocess(sp)

        ranked_rows_emb = self.retriever_emb.run(
            project_name=project_name,
            query_pieces=query_pieces,
            top_k=top_k,
        )

        candidate_ids = [str(chunk_id) for chunk_id, _score, _meta in ranked_rows_emb]

        try:
            ranked_rows_splade = self._get_retriever_splade().run(
                project_name=project_name,
                query_pieces=query_pieces,
                top_k=top_k,
                candidate_ids=candidate_ids,
            )
        except FileNotFoundError:
            # Keep Retrieval usable even if an older project has no SPLADE store yet.
            ranked_rows_splade = []

        ranked_rows = rrf_merge(
            ranked_rows_emb,
            ranked_rows_splade,
            top_k=top_k,
            weight_a=0.75,
            weight_b=0.25,
        )

        ranked_rows = self._project_rrf_metadata_to_retrieval_contract(ranked_rows)

        sp = self._postprocess(sp, ranked_rows)
        return sp

    # -----------------------------------------------------------------
    # Stage-level orchestration helpers
    # -----------------------------------------------------------------

    def _preprocess(self, sp: SuperPrompt) -> List[str]:
        """
        Build the retrieval query text from SuperPrompt and split it into
        overlapping query pieces.

        Query-building and query-splitting support logic lives outside this file.
        Retriever keeps only the stage-level orchestration.
        """
        query_text = SuperPromptProjector.build_query_text(sp)

        query_pieces = split_query_into_pieces(
            query_text=query_text,
            chunker=self.chunker,
            chunk_size=DEFAULT_QUERY_CHUNK_SIZE,
            overlap=DEFAULT_QUERY_OVERLAP,
        )

        return query_pieces

    def _postprocess(self, sp: SuperPrompt, ranked_rows: List[RankedRow]) -> SuperPrompt:
        """
        Complete the Retrieval stage after the backend retrievers have finished.

        Responsibilities:
        - hydrate ranked rows into real Chunk objects
        - write the fused retrieval result into SuperPrompt
        """
        valid_ranked_rows, hydrated_chunks = self._hydrate_ranked_chunks(ranked_rows)
        self._write_stage_to_superprompt(sp, valid_ranked_rows, hydrated_chunks)
        return sp

    def _get_retriever_splade(self) -> RetrieverSplade:
        """
        Lazily initialize the SPLADE backend on first retrieval use.
        """
        if self._retriever_splade is None:
            if self._splade_embedder is None:
                self._splade_embedder = SpladeEmbedder(device="cpu")

            self._retriever_splade = RetrieverSplade(
                splade_root=str(self.splade_root),
                splade_embedder=self._splade_embedder,
            )

        return self._retriever_splade

    # -----------------------------------------------------------------
    # Internal helpers kept in retriever.py
    # -----------------------------------------------------------------

    def _project_rrf_metadata_to_retrieval_contract(
        self,
        ranked_rows: List[RankedRow],
    ) -> List[RankedRow]:
        """
        Translate neutral RRF merger metadata into retrieval-specific metadata.

        Why this exists:
        - rrf_merger.py is intentionally neutral and uses generic names:
            score_a, score_b, rank_a, rank_b
        - Retriever is the correct higher-level place that knows:
            a = dense embedding branch
            b = SPLADE branch
        - SuperPrompt projector and other retrieval-facing code can therefore
          keep reading the retrieval-specific names:
            emb_score, splade_score, emb_rank, splade_rank, rrf_score

        Design rule:
        - Preserve the neutral keys if they already exist.
        - Add the retrieval-specific aliases here.
        """
        projected_rows: List[RankedRow] = []

        for chunk_id, fused_score, meta in ranked_rows:
            meta_in = dict(meta or {})
            meta_out = dict(meta_in)

            if "score_a" in meta_in and "emb_score" not in meta_out:
                meta_out["emb_score"] = float(meta_in["score_a"])

            if "score_b" in meta_in and "splade_score" not in meta_out:
                meta_out["splade_score"] = float(meta_in["score_b"])

            if "rank_a" in meta_in and "emb_rank" not in meta_out:
                meta_out["emb_rank"] = int(meta_in["rank_a"])

            if "rank_b" in meta_in and "splade_rank" not in meta_out:
                meta_out["splade_rank"] = int(meta_in["rank_b"])

            if "rrf_score" not in meta_out:
                meta_out["rrf_score"] = float(fused_score)

            projected_rows.append((str(chunk_id), float(fused_score), meta_out))

        return projected_rows

    def _hydrate_ranked_chunks(
        self,
        ranked_rows: List[RankedRow],
    ) -> tuple[List[RankedRow], List[Chunk]]:
        """
        Reconstruct real Chunk objects for the selected ranked rows.

        Why reconstruction is needed:
        - Vector stores keep vectors + metadata only.
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
        valid_ranked_rows: List[RankedRow] = []
        hydrated: List[Chunk] = []

        # Local caches avoid re-reading and re-splitting the same source file
        # when several retrieved chunks come from that file.
        text_cache: Dict[str, str] = {}
        split_cache: Dict[str, List[tuple[str, str]]] = {}

        step = DEFAULT_QUERY_CHUNK_SIZE - DEFAULT_QUERY_OVERLAP

        for chunk_id, score, meta in ranked_rows:
            meta = meta or {}

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

            valid_ranked_rows.append((chunk_id, float(score), dict(meta)))
            hydrated.append(chunk_obj)

        return valid_ranked_rows, hydrated

    def _write_stage_to_superprompt(
        self,
        sp: SuperPrompt,
        ranked_rows: List[RankedRow],
        hydrated_chunks: List[Chunk],
    ) -> None:
        """
        Persist the Retrieval result into the evolving SuperPrompt.

        Write-back contract for this stage:
        - base_context_chunks:
            the hydrated Chunk objects in retrieval order
        - views_by_stage["retrieval"]:
            ordered triples (chunk_id, retrieval_score, SELECTED)
            where retrieval_score is now the final fused RRF score
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

        for chunk_id, score, _meta in ranked_rows:
            retrieval_view.append((str(chunk_id), float(score), A3ChunkStatus.SELECTED))
            final_ids.append(str(chunk_id))

        sp.views_by_stage["retrieval"] = retrieval_view
        sp.final_selection_ids = final_ids
        sp.stage = "retrieval"
        sp.history_of_stages.append("retrieval")