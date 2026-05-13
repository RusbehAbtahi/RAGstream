# ragstream/memory/compression/memory_activebrief_relevance_gate.py
# -*- coding: utf-8 -*-
"""
MemoryActiveBriefRelevanceGate
==============================

Non-LLM gate before ActiveBrief update.

Purpose:
- Avoid sending unrelated Q/A pairs to the ActiveBrief LLM updater.
- Still save every MemoryRecord normally.
- If a Q/A is not worthy, copy the previous ActiveBrief into the new record.
- If a new topic becomes stable, allow it to replace/update the ActiveBrief.

Current logic:
1. Compare new Q/A vectors to the center of the current ActiveBrief.
2. If Q/A top-score mean passes activebrief_threshold:
   -> normal ActiveBrief update.
3. If it fails, compare new Q/A vectors to the center of the previous skipped Q/A.
4. If Q/A top-score mean passes pending_topic_threshold:
   -> topic shift confirmed, call LLM using the pending Q/A + current Q/A.
5. If both fail:
   -> skip LLM, copy previous ActiveBrief, update pending-topic buffer.

Important:
- No ActiveBrief weak-tail / 80% logic remains here.
- The gate uses fixed development thresholds from runtime_config.
- The gate logs only scores and summaries, not full vectors.
"""

from __future__ import annotations

import json
import math
import re

from dataclasses import dataclass
from typing import Any

from ragstream.ingestion.embedder import Embedder
from ragstream.textforge.RagLog import LogDeveloper as _logger_dev
DEV_LOG_ENABLED = False

def logger_dev(*args, **kwargs):
    if DEV_LOG_ENABLED:
        return _logger_dev(*args, **kwargs)
    return None

Vector = list[float]


@dataclass
class RelevanceGateResult:
    should_update_activebrief: bool
    route: str
    reason: str
    activebrief_top_mean: float
    pending_topic_top_mean: float
    diagnostics: dict[str, Any]


class MemoryActiveBriefRelevanceGate:
    def __init__(
        self,
        *,
        embedding_model: str = "text-embedding-3-small",
        window_size_sentences: int = 3,
        window_overlap_sentences: int = 1,
        activebrief_threshold: float = 0.25,
        pending_topic_threshold: float = 0.25,
    ) -> None:
        self.embedding_model = str(embedding_model)
        self.window_size_sentences = int(window_size_sentences)
        self.window_overlap_sentences = int(window_overlap_sentences)
        self.activebrief_threshold = float(activebrief_threshold)
        self.pending_topic_threshold = float(pending_topic_threshold)

        self._embedder = Embedder(model=self.embedding_model)

    def evaluate(
        self,
        *,
        record_id: str,
        previous_active_retrieval_brief: str,
        question_vectors: list[Vector],
        answer_vectors: list[Vector],
        pending_topic_buffer: dict[str, Any] | None = None,
    ) -> RelevanceGateResult:
        """
        Decide whether the current Q/A should update ActiveBrief.

        Q/A vectors are reused from MemorySentenceReducer.
        The only new embedding cost here is the previous ActiveBrief text.
        """
        previous_brief = str(previous_active_retrieval_brief or "").strip()
        pending_topic_buffer = pending_topic_buffer if isinstance(pending_topic_buffer, dict) else {}

        qa_vectors = list(question_vectors or []) + list(answer_vectors or [])

        if not previous_brief:
            return self._log_and_return(
                record_id=record_id,
                result=RelevanceGateResult(
                    should_update_activebrief=True,
                    route="init_no_previous_activebrief",
                    reason="no_previous_activebrief",
                    activebrief_top_mean=0.0,
                    pending_topic_top_mean=0.0,
                    diagnostics={
                        "record_id": record_id,
                        "decision": "pass",
                        "route": "init_no_previous_activebrief",
                        "reason": "no_previous_activebrief",
                    },
                ),
            )

        if not qa_vectors:
            return self._log_and_return(
                record_id=record_id,
                result=RelevanceGateResult(
                    should_update_activebrief=False,
                    route="skip_no_qa_vectors",
                    reason="no_qa_vectors",
                    activebrief_top_mean=0.0,
                    pending_topic_top_mean=0.0,
                    diagnostics={
                        "record_id": record_id,
                        "decision": "skip",
                        "route": "skip_no_qa_vectors",
                        "reason": "no_qa_vectors",
                    },
                ),
            )

        activebrief_center = self._build_activebrief_center(previous_brief)

        if not activebrief_center:
            # Safe pass:
            # If the ActiveBrief reference space cannot be built,
            # do not risk blocking an update.
            return self._log_and_return(
                record_id=record_id,
                result=RelevanceGateResult(
                    should_update_activebrief=True,
                    route="activebrief_safe_pass",
                    reason="no_activebrief_center_safe_pass",
                    activebrief_top_mean=0.0,
                    pending_topic_top_mean=0.0,
                    diagnostics={
                        "record_id": record_id,
                        "decision": "pass",
                        "route": "activebrief_safe_pass",
                        "reason": "no_activebrief_center_safe_pass",
                    },
                ),
            )

        activebrief_eval = self._evaluate_against_center(
            center_vector=activebrief_center,
            question_vectors=question_vectors,
            answer_vectors=answer_vectors,
        )

        if activebrief_eval["qa_top_mean"] >= self.activebrief_threshold:
            diagnostics = {
                "record_id": record_id,
                "decision": "pass",
                "route": "activebrief_update",
                "reason": "qa_top_mean_passed_activebrief_threshold",
                "embedding_model": self.embedding_model,
                "activebrief_threshold": self.activebrief_threshold,
                "pending_topic_threshold": self.pending_topic_threshold,
                "activebrief_comparison": activebrief_eval,
                "pending_topic_comparison": {},
            }

            return self._log_and_return(
                record_id=record_id,
                result=RelevanceGateResult(
                    should_update_activebrief=True,
                    route="activebrief_update",
                    reason="qa_top_mean_passed_activebrief_threshold",
                    activebrief_top_mean=float(activebrief_eval["qa_top_mean"]),
                    pending_topic_top_mean=0.0,
                    diagnostics=diagnostics,
                ),
            )

        pending_center = self._extract_pending_center(pending_topic_buffer)

        pending_eval: dict[str, Any] = {}
        if pending_center:
            pending_eval = self._evaluate_against_center(
                center_vector=pending_center,
                question_vectors=question_vectors,
                answer_vectors=answer_vectors,
            )

            if pending_eval["qa_top_mean"] >= self.pending_topic_threshold:
                diagnostics = {
                    "record_id": record_id,
                    "decision": "pass",
                    "route": "pending_topic_shift",
                    "reason": "qa_top_mean_passed_pending_topic_threshold",
                    "embedding_model": self.embedding_model,
                    "activebrief_threshold": self.activebrief_threshold,
                    "pending_topic_threshold": self.pending_topic_threshold,
                    "pending_topic_record_id": str(pending_topic_buffer.get("record_id", "") or ""),
                    "activebrief_comparison": activebrief_eval,
                    "pending_topic_comparison": pending_eval,
                }

                return self._log_and_return(
                    record_id=record_id,
                    result=RelevanceGateResult(
                        should_update_activebrief=True,
                        route="pending_topic_shift",
                        reason="qa_top_mean_passed_pending_topic_threshold",
                        activebrief_top_mean=float(activebrief_eval["qa_top_mean"]),
                        pending_topic_top_mean=float(pending_eval["qa_top_mean"]),
                        diagnostics=diagnostics,
                    ),
                )

        diagnostics = {
            "record_id": record_id,
            "decision": "skip",
            "route": "skip_and_update_pending_topic",
            "reason": "qa_failed_activebrief_and_pending_topic_thresholds",
            "embedding_model": self.embedding_model,
            "activebrief_threshold": self.activebrief_threshold,
            "pending_topic_threshold": self.pending_topic_threshold,
            "pending_topic_record_id": str(pending_topic_buffer.get("record_id", "") or ""),
            "activebrief_comparison": activebrief_eval,
            "pending_topic_comparison": pending_eval,
        }

        return self._log_and_return(
            record_id=record_id,
            result=RelevanceGateResult(
                should_update_activebrief=False,
                route="skip_and_update_pending_topic",
                reason="qa_failed_activebrief_and_pending_topic_thresholds",
                activebrief_top_mean=float(activebrief_eval["qa_top_mean"]),
                pending_topic_top_mean=float(pending_eval.get("qa_top_mean", 0.0) or 0.0),
                diagnostics=diagnostics,
            ),
        )

    def build_pending_topic_buffer(
        self,
        *,
        record_id: str,
        created_at_utc: str,
        reduced_question: str,
        reduced_answer: str,
        question_vectors: list[Vector],
        answer_vectors: list[Vector],
    ) -> dict[str, Any]:
        """
        Build the RAM-only pending-topic buffer.

        This buffer is not persisted into .ragmem or SQLite.
        It exists only to detect a possible topic shift:
        first skipped Q/A creates the buffer;
        next skipped Q/A is compared against this buffer.
        """
        qa_vectors = list(question_vectors or []) + list(answer_vectors or [])
        center_vector = self._centroid(qa_vectors)

        buffer = {
            "record_id": str(record_id or ""),
            "created_at_utc": str(created_at_utc or ""),
            "reduced_question": str(reduced_question or ""),
            "reduced_answer": str(reduced_answer or ""),
            "question_vectors": list(question_vectors or []),
            "answer_vectors": list(answer_vectors or []),
            "center_vector": center_vector,
            "vector_count": len(qa_vectors),
        }

        logger_dev(
            "ActiveBrief pending-topic buffer updated\n"
            + json.dumps(
                {
                    "record_id": buffer["record_id"],
                    "created_at_utc": buffer["created_at_utc"],
                    "question_vector_count": len(buffer["question_vectors"]),
                    "answer_vector_count": len(buffer["answer_vectors"]),
                    "vector_count": buffer["vector_count"],
                    "has_center_vector": bool(buffer["center_vector"]),
                    "reduced_question_preview": buffer["reduced_question"][:500],
                    "reduced_answer_preview": buffer["reduced_answer"][:500],
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            "DEBUG",
            "CONFIDENTIAL",
        )

        return buffer

    def _build_activebrief_center(self, previous_brief: str) -> Vector:
        activebrief_windows = self._build_sentence_windows(previous_brief)
        activebrief_texts = [item["text"] for item in activebrief_windows]
        activebrief_vectors = self._embed_texts(activebrief_texts)
        return self._centroid(activebrief_vectors)

    def _evaluate_against_center(
        self,
        *,
        center_vector: Vector,
        question_vectors: list[Vector],
        answer_vectors: list[Vector],
    ) -> dict[str, Any]:
        """
        Score Q/A vectors against a reference center.

        Used twice:
        - Q/A against current ActiveBrief center
        - Q/A against pending skipped-topic center
        """
        question_scores = [
            self._cosine(vector, center_vector)
            for vector in question_vectors or []
        ]
        answer_scores = [
            self._cosine(vector, center_vector)
            for vector in answer_vectors or []
        ]
        qa_scores = question_scores + answer_scores
        qa_scores_sorted = sorted(qa_scores, reverse=True)

        top_count = self._select_count(len(qa_scores_sorted))
        top_scores = qa_scores_sorted[:top_count]
        top_mean = self._mean(top_scores)

        return {
            "qa_vector_count": len(qa_scores),
            "question_vector_count": len(question_scores),
            "answer_vector_count": len(answer_scores),
            "qa_top_count": top_count,
            "qa_top_mean": top_mean,
            "qa_top_scores": self._round_list(top_scores),
            "qa_all_scores_best_to_worst": self._round_list(qa_scores_sorted),
            "qa_score_summary": self._score_summary(qa_scores),
            "question_score_summary": self._score_summary(question_scores),
            "answer_score_summary": self._score_summary(answer_scores),
        }

    @staticmethod
    def _select_count(n: int) -> int:
        """
        Stable 20% top-score selection rule.

        For small texts, pure percentage is unstable:
        - <= 4 vectors: use all
        - 5..20 vectors: use top 4
        - > 20 vectors: use floor(n / 5)
        """
        n = int(n)
        if n <= 0:
            return 0
        if n <= 4:
            return n
        if n <= 20:
            return 4
        return max(1, n // 5)

    @staticmethod
    def _extract_pending_center(pending_topic_buffer: dict[str, Any]) -> Vector:
        center = pending_topic_buffer.get("center_vector", [])
        if not isinstance(center, list):
            return []
        return [float(value) for value in center]

    def _build_sentence_windows(self, text: str) -> list[dict[str, Any]]:
        sentences = self._split_sentences(text)

        if not sentences:
            return []

        window_size = max(1, self.window_size_sentences)
        overlap = max(0, min(self.window_overlap_sentences, window_size - 1))
        step = max(1, window_size - overlap)

        windows: list[dict[str, Any]] = []

        start = 0
        while start < len(sentences):
            end = min(len(sentences), start + window_size)
            indexes = list(range(start, end))
            window_text = " ".join(sentences[start:end]).strip()

            if window_text:
                windows.append(
                    {
                        "text": window_text,
                        "sentence_indexes": indexes,
                    }
                )

            if end >= len(sentences):
                break

            start += step

        return windows

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        clean = str(text or "").strip()
        if not clean:
            return []

        clean = re.sub(r"\n{2,}", "\n", clean)
        rough_parts = re.split(r"(?<=[.!?])\s+|\n+", clean)

        sentences: list[str] = []
        for part in rough_parts:
            item = str(part or "").strip()
            if item:
                sentences.append(item)

        if not sentences and clean:
            sentences.append(clean)

        return sentences

    def _embed_texts(self, texts: list[str]) -> list[Vector]:
        clean_texts = [str(text or "").strip() for text in texts]
        clean_texts = [text for text in clean_texts if text]

        if not clean_texts:
            return []

        vectors = self._embedder.embed(clean_texts)
        return [list(vector) for vector in vectors]

    @staticmethod
    def _centroid(vectors: list[Vector]) -> Vector:
        if not vectors:
            return []

        dim = len(vectors[0])
        if dim <= 0:
            return []

        sums = [0.0 for _ in range(dim)]
        count = 0

        for vector in vectors:
            if len(vector) != dim:
                continue

            for i, value in enumerate(vector):
                sums[i] += float(value)

            count += 1

        if count <= 0:
            return []

        return [value / float(count) for value in sums]

    @staticmethod
    def _cosine(a: Vector, b: Vector) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0

        dot = 0.0
        norm_a = 0.0
        norm_b = 0.0

        for x, y in zip(a, b):
            fx = float(x)
            fy = float(y)
            dot += fx * fy
            norm_a += fx * fx
            norm_b += fy * fy

        if norm_a <= 0.0 or norm_b <= 0.0:
            return 0.0

        return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))

    @staticmethod
    def _mean(values: list[float]) -> float:
        if not values:
            return 0.0
        return float(sum(float(value) for value in values) / len(values))

    @staticmethod
    def _round_list(values: list[float]) -> list[float]:
        return [round(float(value), 6) for value in values]

    def _score_summary(self, values: list[float]) -> dict[str, Any]:
        if not values:
            return {
                "count": 0,
                "min": 0.0,
                "max": 0.0,
                "mean": 0.0,
            }

        return {
            "count": len(values),
            "min": round(min(values), 6),
            "max": round(max(values), 6),
            "mean": round(self._mean(values), 6),
        }

    def _log_and_return(
        self,
        *,
        record_id: str,
        result: RelevanceGateResult,
    ) -> RelevanceGateResult:
        logger_dev(
            "ActiveBrief relevance gate decision\n"
            + json.dumps(
                {
                    "record_id": record_id,
                    "should_update_activebrief": result.should_update_activebrief,
                    "route": result.route,
                    "reason": result.reason,
                    "activebrief_top_mean": result.activebrief_top_mean,
                    "pending_topic_top_mean": result.pending_topic_top_mean,
                    "diagnostics": result.diagnostics,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            "DEBUG",
            "CONFIDENTIAL",
        )
        return result