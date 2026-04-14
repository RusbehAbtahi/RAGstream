# -*- coding: utf-8 -*-
"""
reranker.py

Purpose:
    Deterministic ReRanker stage for RAGstream.

Scope of this file:
    - Read the Retrieval candidates already stored in the current SuperPrompt.
    - Build reranking query pieces from TASK / PURPOSE / CONTEXT.
    - Clean chunk text dynamically before ColBERT scoring.
    - Score each Retrieval candidate with ColBERT over the split query pieces.
    - Fuse Retrieval ranking and ColBERT ranking with deterministic weighted RRF.
    - Write the ReRanker stage result back into the same SuperPrompt.

Non-goals:
    - No Chroma query here.
    - No raw-file hydration here.
    - No A3 filtering here.
    - No GUI rendering here.
    - No final prompt composition here.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from pylate import models, rank

from ragstream.ingestion.chunker import Chunker
from ragstream.orchestration.super_prompt import A3ChunkStatus, SuperPrompt
from ragstream.orchestration.superprompt_projector import SuperPromptProjector
from ragstream.retrieval.chunk import Chunk
from ragstream.retrieval.rrf_merger import rrf_merge
from ragstream.retrieval.smart_query_splitter import split_query_into_pieces


# ---------------------------------------------------------------------
# Shared row contract
# ---------------------------------------------------------------------

RankedRow = Tuple[str, float, Dict[str, Any]]

# ---------------------------------------------------------------------
# Module-level reranker defaults
# ---------------------------------------------------------------------

# Agreed current reranker model direction.
DEFAULT_RERANK_MODEL = "lightonai/GTE-ModernColBERT-v1"

# Conceptual cap from the current requirement set for how many Retrieval
# candidates should be passed into ReRanker.
DEFAULT_RERANK_TOP_K = 50

# Agreed current runtime direction: CPU-only deterministic stage.
DEFAULT_DEVICE = "cpu"

# Keep query splitting aligned with Retrieval.
DEFAULT_QUERY_CHUNK_SIZE = 1200
DEFAULT_QUERY_OVERLAP = 120

# Equal-weight fusion between Retrieval and ColBERT.
DEFAULT_RETRIEVAL_WEIGHT = 0.75
DEFAULT_COLBERT_WEIGHT = 0.25


class Reranker:
    """
    Deterministic ReRanker stage for document chunks.

    Design:
    - Keep this class stateless with respect to pipeline history.
      The evolving pipeline state lives in SuperPrompt.
    - This class only reads the current SuperPrompt, computes reranking,
      and writes the reranked result back into the same SuperPrompt.
    - The controller decides when to call this class.
    """

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_RERANK_MODEL,
        top_k: int = DEFAULT_RERANK_TOP_K,
        device: str = DEFAULT_DEVICE,
    ) -> None:
        """
        Initialize ReRanker with the agreed ColBERT model.

        Args:
            model_name:
                Hugging Face / PyLate-compatible model id for the reranker.
            top_k:
                Maximum number of Retrieval candidates to rerank.
            device:
                Runtime device. Current agreed direction is CPU.
                Kept as part of the stable ReRanker interface.
        """
        self._model_name = model_name
        self._top_k = int(top_k) if int(top_k) > 0 else DEFAULT_RERANK_TOP_K
        self._device = device
        self._chunker = Chunker()
        self._colbert_model = models.ColBERT(model_name_or_path=self._model_name)

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def run(self, sp: SuperPrompt) -> SuperPrompt:
        """
        Execute the ReRanker stage and update the same SuperPrompt in place.

        Inputs:
            sp:
                The current evolving SuperPrompt, typically after Retrieval.

        Returns:
            The same SuperPrompt instance, mutated in place.

        Effects on SuperPrompt:
            - Writes the reranked stage snapshot into sp.views_by_stage["reranked"]
            - Writes reranked chunk IDs into sp.final_selection_ids
            - Appends "reranked" to sp.history_of_stages
            - Sets sp.stage = "reranked"
        """
        query_pieces, retrieval_rows, chunk_lookup = self._prepare_inputs(sp)
        colbert_rows = self._score_with_colbert(query_pieces, retrieval_rows, chunk_lookup)
        fused_rows = self._fuse_with_retrieval(retrieval_rows, colbert_rows, chunk_lookup)
        fused_rows = self._project_fused_metadata_to_reranker_contract(fused_rows)
        self._write_scores_back_to_chunks(fused_rows, chunk_lookup)
        reranked_view, reranked_ids = self._build_reranked_view(fused_rows)

        sp.views_by_stage["reranked"] = reranked_view
        sp.final_selection_ids = reranked_ids
        sp.stage = "reranked"
        sp.history_of_stages.append("reranked")

        return sp

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _prepare_inputs(
        self,
        sp: SuperPrompt,
    ) -> tuple[List[str], List[tuple[str, float, A3ChunkStatus]], Dict[str, Chunk]]:
        """
        Prepare the reranking job from the current SuperPrompt.

        Responsibilities grouped here on purpose:
        - validate stage and Retrieval availability,
        - build reranking query pieces from TASK / PURPOSE / CONTEXT,
        - trim Retrieval rows to the active rerank cap,
        - build chunk_id -> Chunk lookup from base_context_chunks.
        """
        if sp is None:
            raise ValueError("Reranker.run: 'sp' must not be None")

        retrieval_rows = sp.views_by_stage.get("retrieval")
        if not retrieval_rows:
            raise ValueError(
                "Reranker.run: Retrieval candidates are missing. "
                "Please run Retrieval before ReRanker."
            )

        if not sp.base_context_chunks:
            raise ValueError(
                "Reranker.run: base_context_chunks is empty. "
                "Please run Retrieval before ReRanker."
            )

        query_text = SuperPromptProjector.build_query_text(sp)

        query_pieces = split_query_into_pieces(
            query_text=query_text,
            chunker=self._chunker,
            chunk_size=DEFAULT_QUERY_CHUNK_SIZE,
            overlap=DEFAULT_QUERY_OVERLAP,
        )

        if not query_pieces:
            raise ValueError(
                "Reranker.run: no reranking query pieces could be built from SuperPrompt."
            )

        candidate_rows = list(retrieval_rows)[: self._top_k]
        chunk_lookup = {chunk_obj.id: chunk_obj for chunk_obj in sp.base_context_chunks}

        return query_pieces, candidate_rows, chunk_lookup

    def _clean_chunk_text(self, text: str) -> str:
        """
        Clean one chunk dynamically before ColBERT scoring.

        Design intention:
        - Remove obvious markdown / YAML / prompt-artifact rubbish.
        - Keep the original stored Chunk unchanged.
        - Stay conservative: preserve normal prose headings and content.
        """
        text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return ""

        metadata_key_re = re.compile(
            r"^(title|author|version|updated|tags|date|created|modified|description)\s*:\s*.*$",
            re.IGNORECASE,
        )

        lines = text.split("\n")
        cleaned_lines: List[str] = []

        front_matter_active = False
        front_matter_checked = False
        seen_content = False

        for raw_line in lines:
            line = raw_line.strip()

            if not front_matter_checked:
                if not line:
                    continue
                if line == "---":
                    front_matter_active = True
                    front_matter_checked = True
                    continue
                front_matter_checked = True

            if front_matter_active:
                if line in {"---", "..."}:
                    front_matter_active = False
                continue

            if not line:
                if seen_content and (not cleaned_lines or cleaned_lines[-1] != ""):
                    cleaned_lines.append("")
                continue

            if line.startswith("```"):
                continue
            if line.lower().startswith("@@meta"):
                continue
            if line in {"### END_OF_PROMPT", "## END_OF_PROMPT", "END_OF_PROMPT"}:
                continue
            if metadata_key_re.match(line):
                continue

            cleaned_lines.append(line)
            seen_content = True

        while cleaned_lines and cleaned_lines[-1] == "":
            cleaned_lines.pop()

        return "\n".join(cleaned_lines).strip()

    def _score_with_colbert(
        self,
        query_pieces: List[str],
        retrieval_rows: List[tuple[str, float, A3ChunkStatus]],
        chunk_lookup: Dict[str, Chunk],
    ) -> List[RankedRow]:
        """
        Score the Retrieval candidates with ColBERT over the reranking query pieces.

        Returns:
            List[(chunk_id, aggregated_colbert_score, metadata)]

        Aggregation rule:
        - Each query piece produces one ColBERT reranked list.
        - For each chunk, aggregate piece-level scores by arithmetic mean.
        - The final ColBERT ranked list is then sorted deterministically.
        """
        valid_ids: List[str] = []
        cleaned_snippets: List[str] = []

        for row in retrieval_rows:
            chunk_id = str(row[0])
            chunk_obj = chunk_lookup.get(chunk_id)
            if chunk_obj is None:
                continue

            cleaned_snippet = self._clean_chunk_text(chunk_obj.snippet or "")
            if not cleaned_snippet:
                continue

            valid_ids.append(chunk_id)
            cleaned_snippets.append(cleaned_snippet)

        if not valid_ids:
            raise ValueError(
                "Reranker.run: no valid Retrieval candidates could be prepared for ColBERT."
            )

        documents_per_query: List[List[str]] = [list(cleaned_snippets) for _ in query_pieces]
        document_ids_per_query: List[List[str]] = [list(valid_ids) for _ in query_pieces]

        queries_embeddings = self._colbert_model.encode(
            query_pieces,
            is_query=True,
            show_progress_bar=False,
        )

        documents_embeddings = self._colbert_model.encode(
            documents_per_query,
            is_query=False,
            show_progress_bar=False,
        )

        reranked_documents = rank.rerank(
            documents_ids=document_ids_per_query,
            queries_embeddings=queries_embeddings,
            documents_embeddings=documents_embeddings,
        )

        score_sums: Dict[str, float] = {}
        score_counts: Dict[str, int] = {}

        for one_query_result in reranked_documents:
            for item in one_query_result:
                chunk_id = str(item["id"])
                score = float(item["score"])
                score_sums[chunk_id] = score_sums.get(chunk_id, 0.0) + score
                score_counts[chunk_id] = score_counts.get(chunk_id, 0) + 1

        scored_rows: List[RankedRow] = []

        for chunk_id in valid_ids:
            if chunk_id not in score_counts:
                continue

            mean_score = score_sums[chunk_id] / float(score_counts[chunk_id])
            base_meta = dict((chunk_lookup.get(chunk_id).meta or {}))
            meta_out = dict(base_meta)
            meta_out["colbert_score"] = float(mean_score)

            scored_rows.append((chunk_id, float(mean_score), meta_out))

        scored_rows.sort(key=lambda row: (-row[1], row[0]))
        return scored_rows

    def _fuse_with_retrieval(
        self,
        retrieval_rows: List[tuple[str, float, A3ChunkStatus]],
        colbert_rows: List[RankedRow],
        chunk_lookup: Dict[str, Chunk],
    ) -> List[RankedRow]:
        """
        Fuse Retrieval ranking and ColBERT ranking with equal-weight RRF.
        """
        retrieval_ranked_rows: List[RankedRow] = []

        for chunk_id, retrieval_score, _status in retrieval_rows:
            chunk_obj = chunk_lookup.get(str(chunk_id))
            if chunk_obj is None:
                continue

            meta_out = dict(chunk_obj.meta or {})

            # Preserve the old Retrieval fused score explicitly before the
            # second RRF merge overwrites the generic key "rrf_score".
            if "rrf_score" in meta_out and "retrieval_rrf_score" not in meta_out:
                meta_out["retrieval_rrf_score"] = float(meta_out["rrf_score"])

            retrieval_ranked_rows.append((str(chunk_id), float(retrieval_score), meta_out))

        return rrf_merge(
            retrieval_ranked_rows,
            colbert_rows,
            top_k=self._top_k,
            weight_a=DEFAULT_RETRIEVAL_WEIGHT,
            weight_b=DEFAULT_COLBERT_WEIGHT,
        )

    def _project_fused_metadata_to_reranker_contract(
        self,
        fused_rows: List[RankedRow],
    ) -> List[RankedRow]:
        """
        Translate neutral RRF merger metadata into reranker-specific metadata.

        Design rule:
        - Preserve existing Retrieval metadata in chunk.meta.
        - Preserve the old Retrieval fused score under:
            retrieval_rrf_score
        - Add reranker-specific aliases here:
            retrieval_score
            colbert_score
            retrieval_rank
            colbert_rank
            rerank_rrf_score
        """
        projected_rows: List[RankedRow] = []

        for chunk_id, fused_score, meta in fused_rows:
            meta_in = dict(meta or {})
            meta_out = dict(meta_in)

            if "score_a" in meta_in and "retrieval_score" not in meta_out:
                meta_out["retrieval_score"] = float(meta_in["score_a"])

            if "score_b" in meta_in and "colbert_score" not in meta_out:
                meta_out["colbert_score"] = float(meta_in["score_b"])

            if "rank_a" in meta_in and "retrieval_rank" not in meta_out:
                meta_out["retrieval_rank"] = int(meta_in["rank_a"])

            if "rank_b" in meta_in and "colbert_rank" not in meta_out:
                meta_out["colbert_rank"] = int(meta_in["rank_b"])

            if "retrieval_rrf_score" not in meta_out and "score_a" in meta_in:
                meta_out["retrieval_rrf_score"] = float(meta_in["score_a"])

            meta_out["rerank_rrf_score"] = float(fused_score)

            projected_rows.append((str(chunk_id), float(fused_score), meta_out))

        return projected_rows

    def _write_scores_back_to_chunks(
        self,
        fused_rows: List[RankedRow],
        chunk_lookup: Dict[str, Chunk],
    ) -> None:
        """
        Persist the reranker metadata into the hydrated chunk objects so that
        SuperPromptProjector can render the score text directly from chunk.meta.
        """
        for chunk_id, _score, meta in fused_rows:
            chunk_obj = chunk_lookup.get(str(chunk_id))
            if chunk_obj is None:
                continue

            merged_meta = dict(chunk_obj.meta or {})
            for key, value in dict(meta or {}).items():
                merged_meta[key] = value

            chunk_obj.meta = merged_meta

    def _build_reranked_view(
        self,
        fused_rows: List[RankedRow],
    ) -> tuple[List[tuple[str, float, A3ChunkStatus]], List[str]]:
        """
        Build the ordered ReRanker stage snapshot.

        Deterministic sort:
        1) higher final fused rerank score first
        2) stable fallback by chunk_id
        """
        fused_rows.sort(key=lambda row: (-row[1], row[0]))

        reranked_view: List[tuple[str, float, A3ChunkStatus]] = []
        reranked_ids: List[str] = []

        for chunk_id, score, _meta in fused_rows:
            reranked_view.append((str(chunk_id), float(score), A3ChunkStatus.SELECTED))
            reranked_ids.append(str(chunk_id))

        return reranked_view, reranked_ids