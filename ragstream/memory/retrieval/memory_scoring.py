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
from ragstream.textforge.RagLog import LogDeveloper as _logger_dev
DEV_LOG_ENABLED = False

def logger_dev(*args, **kwargs):
    if DEV_LOG_ENABLED:
        return _logger_dev(*args, **kwargs)
    return None

class MemoryScorer:
    """
    Memory retrieval scoring helper.

    Role-separated scoring:
    - question hits represent similarity to an old problem
    - answer hits represent similarity to an old solution
    - record_handle hits represent metadata/keyword/anchor discovery

    Recency scoring is episode-distance based:
    - k = 0 means latest MemoryRecord
    - k = 1 means one MemoryRecord older
    - k = 2 means two MemoryRecords older
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

        self.semantic_chunk_cfg: dict[str, Any] = dict(
            self.config.get("semantic_memory_chunks", {}) or {}
        )
        self.episodic_cfg: dict[str, Any] = dict(
            self.config.get("episodic_memory", {}) or {}
        )

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
                "semantic_score": float(score),
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
                    "tag": metadata.get("tag", "Green") or "Green",
                    "retrieval_source_mode": metadata.get("retrieval_source_mode", "QA"),
                    "episode_distance_k": metadata.get("episode_distance_k"),
                    "episode_index": metadata.get("episode_index"),
                    "episode_count_in_active_file": metadata.get("episode_count_in_active_file"),
                    "question_score": 0.0,
                    "answer_score": 0.0,
                    "meta_score": 0.0,
                    "semantic_parent_score": 0.0,
                    "recency_score": None,
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
        parents = self.apply_episodic_recency_policy(parents)
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

        This produces the semantic parent score before recency is applied.
        """
        for parent in parent_scores:
            mode = str(parent.get("retrieval_source_mode", "QA") or "QA").strip().upper()
            if mode not in {"QA", "Q", "A"}:
                mode = "QA"

            weights = self.parent_score_weights.get(mode, self.default_weights)

            answer_score = float(parent.get("answer_score", 0.0))
            question_score = float(parent.get("question_score", 0.0))
            meta_score = float(parent.get("meta_score", 0.0))

            semantic_parent_score = (
                answer_score * float(weights.get("answer", 0.0))
                + question_score * float(weights.get("question", 0.0))
                + meta_score * float(weights.get("meta", 0.0))
            )

            parent["semantic_parent_score"] = semantic_parent_score
            parent["final_parent_score"] = semantic_parent_score
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
        Gold records are not decayed here because Gold is handled as a separate
        priority/bypass path by MemoryRetriever.
        """
        excluded_tags = self._collect_excluded_tags()
        result: list[dict[str, Any]] = []

        for parent in parent_scores:
            tag = str(parent.get("tag", "") or "Green").strip()

            if tag in excluded_tags:
                parent["excluded"] = True
                parent["exclude_reason"] = f"tag={tag}"
                continue

            parent["excluded"] = False
            parent["gold_bypass_recency"] = tag == "Gold"

            result.append(parent)

        return result

    def apply_episodic_recency_policy(
        self,
        parent_scores: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Apply Green episodic recency policy.

        Formula:
            final = semantic_weight * semantic_parent_score
                    + recency_weight * recency_score

        Gold bypasses this normal recency policy.
        Black has already been excluded.
        """
        semantic_weight = float(self.episodic_cfg.get("green_semantic_weight", 0.75))
        recency_weight = float(self.episodic_cfg.get("green_recency_weight", 0.25))
        half_life_k = float(self.episodic_cfg.get("green_half_life_k", 10.0))
        recency_enabled = bool(self.episodic_cfg.get("recency_enabled", True))

        semantic_weight, recency_weight = self._normalize_two_weights(
            semantic_weight,
            recency_weight,
        )

        for parent in parent_scores:
            tag = str(parent.get("tag", "") or "Green").strip()
            semantic_score = float(parent.get("semantic_parent_score", 0.0))

            if tag == "Gold":
                parent["final_parent_score"] = semantic_score
                parent["recency_score"] = None
                parent["recency_policy"] = "bypassed_for_gold"
                continue

            if not recency_enabled:
                parent["final_parent_score"] = semantic_score
                parent["recency_score"] = None
                parent["recency_policy"] = "disabled"
                continue

            recency_score = self._recency_score_from_episode_distance(
                parent.get("episode_distance_k"),
                half_life_k,
            )

            final_score = (
                semantic_weight * semantic_score
                + recency_weight * recency_score
            )

            parent["final_parent_score"] = final_score
            parent["recency_score"] = recency_score
            parent["recency_half_life_k"] = half_life_k
            parent["semantic_recency_weights"] = {
                "semantic": semantic_weight,
                "recency": recency_weight,
            }
            parent["recency_policy"] = "green_episodic_semantic_plus_recency"

        return parent_scores

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
        metadata_by_record: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Select raw semantic memory chunks for later A3/A4.

        record_handle hits are not selected here because they are discovery
        handles, not semantic evidence chunks.

        Semantic chunks use weaker recency weighting than episodic memory.
        """
        metadata_by_record = metadata_by_record or {}
        candidates: list[dict[str, Any]] = []

        semantic_weight = float(self.semantic_chunk_cfg.get("semantic_weight", 0.90))
        recency_weight = float(self.semantic_chunk_cfg.get("recency_weight", 0.10))
        half_life_k = float(self.semantic_chunk_cfg.get("half_life_k", 10.0))
        recency_enabled = bool(self.semantic_chunk_cfg.get("recency_enabled", True))

        semantic_weight, recency_weight = self._normalize_two_weights(
            semantic_weight,
            recency_weight,
        )

        for hit in scored_hits:
            role = str(hit.get("role", "")).strip()
            if role not in {"question", "answer"}:
                continue

            record_id = str(hit.get("record_id", "") or "").strip()
            live_metadata = dict(metadata_by_record.get(record_id, {}) or {})
            metadata = dict(hit.get("metadata", {}) or {})
            merged_metadata = {**metadata, **live_metadata}

            tag = str(merged_metadata.get("tag", "") or "Green").strip()
            if tag in self._collect_excluded_tags():
                continue

            semantic_score = float(hit.get("semantic_score", hit.get("score", 0.0)))

            if tag == "Gold":
                final_score = semantic_score
                recency_score = None
                recency_policy = "bypassed_for_gold"
            elif recency_enabled:
                recency_score = self._recency_score_from_episode_distance(
                    merged_metadata.get("episode_distance_k"),
                    half_life_k,
                )
                final_score = (
                    semantic_weight * semantic_score
                    + recency_weight * recency_score
                )
                recency_policy = "semantic_chunk_semantic_plus_recency"
            else:
                final_score = semantic_score
                recency_score = None
                recency_policy = "disabled"

            candidates.append(
                {
                    "vector_id": hit.get("vector_id", ""),
                    "record_id": record_id,
                    "role": role,
                    "score": float(final_score),
                    "semantic_score": semantic_score,
                    "recency_score": recency_score,
                    "episode_distance_k": merged_metadata.get("episode_distance_k"),
                    "recency_half_life_k": half_life_k if recency_enabled and tag != "Gold" else None,
                    "semantic_recency_weights": {
                        "semantic": semantic_weight,
                        "recency": recency_weight,
                    },
                    "recency_policy": recency_policy,
                    "distance": hit.get("distance"),
                    "document": hit.get("document", ""),
                    "metadata": merged_metadata,
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

    def describe_policy(self) -> dict[str, Any]:
        """Return compact scoring policy for developer diagnostics."""
        return {
            "episodic_memory": {
                "green_semantic_weight": float(self.episodic_cfg.get("green_semantic_weight", 0.75)),
                "green_recency_weight": float(self.episodic_cfg.get("green_recency_weight", 0.25)),
                "green_half_life_k": float(self.episodic_cfg.get("green_half_life_k", 10.0)),
                "recency_enabled": bool(self.episodic_cfg.get("recency_enabled", True)),
                "gold_policy": "bypass_recency_normal_scoring",
            },
            "semantic_memory_chunks": {
                "semantic_weight": float(self.semantic_chunk_cfg.get("semantic_weight", 0.90)),
                "recency_weight": float(self.semantic_chunk_cfg.get("recency_weight", 0.10)),
                "half_life_k": float(self.semantic_chunk_cfg.get("half_life_k", 10.0)),
                "recency_enabled": bool(self.semantic_chunk_cfg.get("recency_enabled", True)),
                "gold_policy": "bypass_recency_normal_scoring",
            },
        }

    def _collect_excluded_tags(self) -> set[str]:
        tags: set[str] = set()

        for section_name in ("working_memory", "episodic_memory", "direct_recall", "semantic_memory_chunks"):
            section = self.config.get(section_name, {})
            for tag in section.get("exclude_tags", []) or []:
                clean = str(tag).strip()
                if clean:
                    tags.add(clean)

        if not tags:
            tags.add("Black")

        return tags

    @staticmethod
    def _recency_score_from_episode_distance(
        episode_distance_k: Any,
        half_life_k: float,
    ) -> float:
        """
        Episode-distance half-life decay.

        k = 0 -> 1.0
        k = H -> 0.5
        k = 2H -> 0.25

        Missing k returns 1.0 so missing metadata does not silently kill
        otherwise relevant memory.
        """
        try:
            k = float(episode_distance_k)
        except Exception:
            return 1.0

        if math.isnan(k) or math.isinf(k):
            return 1.0

        if k < 0:
            k = 0.0

        try:
            h = float(half_life_k)
        except Exception:
            h = 10.0

        if math.isnan(h) or math.isinf(h) or h <= 0:
            h = 10.0

        score = 2.0 ** (-k / h)

        return max(0.0, min(1.0, float(score)))

    @staticmethod
    def _normalize_two_weights(
        semantic_weight: float,
        recency_weight: float,
    ) -> tuple[float, float]:
        """
        Normalize two active weights so semantic=1 and recency=1 still gives 1.

        This avoids the inactive-importance problem.
        """
        s = max(0.0, float(semantic_weight))
        r = max(0.0, float(recency_weight))
        total = s + r

        if total <= 0:
            return 1.0, 0.0

        return s / total, r / total

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