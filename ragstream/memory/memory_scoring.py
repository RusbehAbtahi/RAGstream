# ragstream/memory/memory_scoring.py
# -*- coding: utf-8 -*-
"""
MemoryScorer
============
Scoring and aggregation logic for Memory Retrieval.

It receives raw vector hits and converts them into:
- normalized hit scores
- parent MemoryRecord scores
- selected semantic memory chunks

This class does not read SQLite.
This class does not query Chroma.
This class does not mutate SuperPrompt.
"""

from __future__ import annotations

import json
import math

from typing import Any

from ragstream.textforge.RagLog import LogALL as logger
from ragstream.textforge.RagLog import LogDeveloper as logger_dev


class MemoryScorer:
    """
    Memory retrieval scoring helper.

    Role-separated scoring:
    - question hits represent similarity to an old problem
    - answer hits represent similarity to an old solution
    - record_handle hits represent metadata/keyword/anchor discovery
    """

    def __init__(
        self,
        config: dict[str, Any],
    ) -> None:
        self.config: dict[str, Any] = config or {}
        self.parent_score_weights: dict[str, dict[str, float]] = dict(
            self.config.get("parent_score_weights", {}) or {}
        )

        self.default_weights: dict[str, float] = {
            "answer": 0.55,
            "question": 0.35,
            "meta": 0.10,
        }

    def score_vector_hits(
        self,
        raw_hits: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Normalize raw vector-store hits.

        Chroma usually returns distance, where smaller means better.
        This method converts distance into a simple similarity-like score.
        """
        scored_hits: list[dict[str, Any]] = []

        for rank, hit in enumerate(raw_hits, start=1):
            metadata = dict(hit.get("metadata", {}) or {})
            role = str(metadata.get("role", hit.get("role", "")) or "").strip()

            distance = hit.get("distance")
            score = hit.get("score")

            if score is None:
                score = self._distance_to_score(distance)

            scored_hit = {
                "rank": rank,
                "vector_id": hit.get("id", hit.get("vector_id", "")),
                "record_id": metadata.get("record_id", hit.get("record_id", "")),
                "role": role,
                "score": float(score),
                "distance": distance,
                "document": hit.get("document", ""),
                "metadata": metadata,
                "raw_hit": hit,
            }

            scored_hits.append(scored_hit)

        logger(
            f"Memory vector hits scored: {len(scored_hits)}",
            "INFO",
            "INTERNAL",
        )

        logger_dev(
            "Memory scored vector hits\n"
            + json.dumps(scored_hits, ensure_ascii=False, indent=2, default=str),
            "DEBUG",
            "CONFIDENTIAL",
        )

        return scored_hits

    def aggregate_parent_scores(
        self,
        scored_hits: list[dict[str, Any]],
        metadata_by_record: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Aggregate vector-hit scores by parent MemoryRecord.

        The parent score is the main episodic score.
        Individual chunks remain available separately for A3/A4 later.
        """
        metadata_by_record = metadata_by_record or {}
        grouped: dict[str, dict[str, Any]] = {}

        for hit in scored_hits:
            record_id = str(hit.get("record_id", "")).strip()
            if not record_id:
                continue

            role = str(hit.get("role", "")).strip()
            score = float(hit.get("score", 0.0))

            if record_id not in grouped:
                metadata = dict(metadata_by_record.get(record_id, {}) or {})
                grouped[record_id] = {
                    "record_id": record_id,
                    "tag": metadata.get("tag", ""),
                    "retrieval_source_mode": metadata.get("retrieval_source_mode", "QA"),
                    "question_score": 0.0,
                    "answer_score": 0.0,
                    "meta_score": 0.0,
                    "final_parent_score": 0.0,
                    "hit_count": 0,
                    "hits": [],
                    "metadata": metadata,
                }

            parent = grouped[record_id]
            parent["hit_count"] += 1
            parent["hits"].append(hit)

            if role == "question":
                parent["question_score"] = max(float(parent["question_score"]), score)
            elif role == "answer":
                parent["answer_score"] = max(float(parent["answer_score"]), score)
            else:
                parent["meta_score"] = max(float(parent["meta_score"]), score)

        parents = list(grouped.values())
        parents = self.apply_retrieval_source_mode(parents)
        parents = self.apply_tag_rules(parents)
        parents = self.rank_parents(parents)

        logger(
            f"Memory parent scores aggregated: {len(parents)} parents",
            "INFO",
            "INTERNAL",
        )

        logger_dev(
            "Memory parent score aggregation\n"
            + json.dumps(parents, ensure_ascii=False, indent=2, default=str),
            "DEBUG",
            "CONFIDENTIAL",
        )

        return parents

    def apply_retrieval_source_mode(
        self,
        parent_scores: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Apply QA/Q/A weighting to parent MemoryRecord scores.
        """
        for parent in parent_scores:
            mode = str(parent.get("retrieval_source_mode", "QA") or "QA").strip().upper()
            if mode not in {"QA", "Q", "A"}:
                mode = "QA"

            weights = self.parent_score_weights.get(mode, self.default_weights)

            answer_score = float(parent.get("answer_score", 0.0))
            question_score = float(parent.get("question_score", 0.0))
            meta_score = float(parent.get("meta_score", 0.0))

            parent["final_parent_score"] = (
                answer_score * float(weights.get("answer", 0.0))
                + question_score * float(weights.get("question", 0.0))
                + meta_score * float(weights.get("meta", 0.0))
            )

            parent["applied_weights"] = weights
            parent["retrieval_source_mode"] = mode

        return parent_scores

    def apply_tag_rules(
        self,
        parent_scores: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Apply current retrieval tag rules.

        Black records are excluded from automatic Memory Retrieval.
        Gold records receive a small priority lift but still remain bounded.
        """
        excluded_tags = self._collect_excluded_tags()
        result: list[dict[str, Any]] = []

        for parent in parent_scores:
            tag = str(parent.get("tag", "") or "").strip()

            if tag in excluded_tags:
                parent["excluded"] = True
                parent["exclude_reason"] = f"tag={tag}"
                continue

            if tag == "Gold":
                parent["final_parent_score"] = float(parent.get("final_parent_score", 0.0)) + 0.05
                parent["gold_priority_applied"] = True
            else:
                parent["gold_priority_applied"] = False

            result.append(parent)

        return result

    def rank_parents(
        self,
        parent_scores: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return parent MemoryRecords sorted by final score."""
        return sorted(
            parent_scores,
            key=lambda item: float(item.get("final_parent_score", 0.0)),
            reverse=True,
        )

    def select_semantic_chunks(
        self,
        scored_hits: list[dict[str, Any]],
        max_memory_chunks: int,
    ) -> list[dict[str, Any]]:
        """
        Select raw semantic memory chunks for later A3/A4.

        record_handle hits are not selected here because they are discovery
        handles, not semantic evidence chunks.
        """
        candidates: list[dict[str, Any]] = []

        for hit in scored_hits:
            role = str(hit.get("role", "")).strip()
            if role not in {"question", "answer"}:
                continue

            metadata = dict(hit.get("metadata", {}) or {})
            tag = str(metadata.get("tag", "") or "").strip()
            if tag in self._collect_excluded_tags():
                continue

            candidates.append(
                {
                    "vector_id": hit.get("vector_id", ""),
                    "record_id": hit.get("record_id", ""),
                    "role": role,
                    "score": float(hit.get("score", 0.0)),
                    "distance": hit.get("distance"),
                    "document": hit.get("document", ""),
                    "metadata": metadata,
                    "rank": hit.get("rank"),
                }
            )

        candidates.sort(
            key=lambda item: float(item.get("score", 0.0)),
            reverse=True,
        )

        selected = candidates[: max(0, int(max_memory_chunks))]

        logger(
            f"Semantic memory chunks selected: {len(selected)}",
            "INFO",
            "INTERNAL",
        )

        logger_dev(
            "Selected semantic memory chunks\n"
            + json.dumps(selected, ensure_ascii=False, indent=2, default=str),
            "DEBUG",
            "CONFIDENTIAL",
        )

        return selected

    def _collect_excluded_tags(self) -> set[str]:
        tags: set[str] = set()

        for section_name in ("working_memory", "episodic_memory", "direct_recall"):
            section = self.config.get(section_name, {})
            for tag in section.get("exclude_tags", []) or []:
                clean = str(tag).strip()
                if clean:
                    tags.add(clean)

        if not tags:
            tags.add("Black")

        return tags

    @staticmethod
    def _distance_to_score(distance: Any) -> float:
        """
        Convert Chroma distance into a bounded similarity-like score.

        Smaller distance means better match.
        """
        try:
            d = float(distance)
        except Exception:
            return 0.0

        if math.isnan(d) or math.isinf(d):
            return 0.0

        if d < 0:
            d = 0.0

        return 1.0 / (1.0 + d)