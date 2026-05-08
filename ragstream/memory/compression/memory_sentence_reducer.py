# ragstream/memory/compression/memory_sentence_reducer.py
# -*- coding: utf-8 -*-
"""
MemorySentenceReducer
=====================

Shared deterministic Q/A reducer for memory compression.

Current use:
- ActiveRetrievalBrief creation uses centroid-anchor reduction.

Future use:
- Retrieval-time memory compression can use query-anchor reduction.

Core idea:
- split Q and A into sentence windows
- always embed Q/A windows
- score windows against an anchor vector
- remove highly redundant windows
- respect Q/A token budget
- restore original sentence order

Important:
- The output keeps Q_vectors and A_vectors.
- If no reduction happens, these vectors represent all Q/A windows.
- If reduction happens, these vectors represent only surviving windows.
"""

from __future__ import annotations

import math
import re

from dataclasses import dataclass
from typing import Any

from ragstream.ingestion.embedder import Embedder
from ragstream.textforge.RagLog import LogDeveloper as logger_dev


Vector = list[float]


@dataclass
class ReducedQA:
    reduced_question: str
    reduced_answer: str
    question_vectors: list[Vector]
    answer_vectors: list[Vector]
    diagnostics: dict[str, Any]


class MemorySentenceReducer:
    def __init__(
        self,
        *,
        max_tokens_total: int = 3000,
        question_max_tokens: int = 1000,
        window_size_sentences: int = 3,
        window_overlap_sentences: int = 1,
        redundancy_threshold: float = 0.92,
        embedding_model: str = "text-embedding-3-small",
    ) -> None:
        self.max_tokens_total = int(max_tokens_total)
        self.question_max_tokens = int(question_max_tokens)
        self.window_size_sentences = int(window_size_sentences)
        self.window_overlap_sentences = int(window_overlap_sentences)
        self.redundancy_threshold = float(redundancy_threshold)
        self.embedding_model = str(embedding_model)

        self._embedder = Embedder(model=self.embedding_model)

    def reduce_with_centroid(
        self,
        input_text: str,
        output_text: str,
    ) -> ReducedQA:
        """
        Query-independent reduction.

        The anchor vector is the centroid of all Q/A sentence-window vectors.
        Used for ActiveRetrievalBrief creation.
        """
        prepared = self._prepare_qa_windows_and_vectors(
            input_text=input_text,
            output_text=output_text,
        )

        all_vectors = prepared["question_vectors"] + prepared["answer_vectors"]

        if not all_vectors:
            return ReducedQA(
                reduced_question="",
                reduced_answer="",
                question_vectors=[],
                answer_vectors=[],
                diagnostics={
                    "mode": "centroid",
                    "reason": "no_vectors",
                },
            )

        anchor_vector = self._centroid(all_vectors)

        return self._reduce_prepared(
            input_text=input_text,
            output_text=output_text,
            question_windows=prepared["question_windows"],
            answer_windows=prepared["answer_windows"],
            question_vectors=prepared["question_vectors"],
            answer_vectors=prepared["answer_vectors"],
            anchor_vector=anchor_vector,
            mode="centroid",
        )

    def reduce_with_anchor(
        self,
        input_text: str,
        output_text: str,
        anchor_vector: Vector,
    ) -> ReducedQA:
        """
        Anchor-based reduction.

        The anchor vector may be:
        - centroid vector, for query-independent reduction
        - query vector, for future retrieval-time compression
        """
        prepared = self._prepare_qa_windows_and_vectors(
            input_text=input_text,
            output_text=output_text,
        )

        return self._reduce_prepared(
            input_text=input_text,
            output_text=output_text,
            question_windows=prepared["question_windows"],
            answer_windows=prepared["answer_windows"],
            question_vectors=prepared["question_vectors"],
            answer_vectors=prepared["answer_vectors"],
            anchor_vector=anchor_vector,
            mode="external_anchor",
        )

    def _prepare_qa_windows_and_vectors(
        self,
        *,
        input_text: str,
        output_text: str,
    ) -> dict[str, Any]:
        """
        Always vectorize Q and A windows.

        Reason:
        - Even if no deterministic reduction is needed, the vectors are useful
          for the later ActiveBrief relevance gate.
        - This avoids paying again to embed the same Q/A.
        """
        question_windows = self._build_sentence_windows(input_text)
        answer_windows = self._build_sentence_windows(output_text)

        question_vectors = self._embed_texts([item["text"] for item in question_windows])
        answer_vectors = self._embed_texts([item["text"] for item in answer_windows])

        return {
            "question_windows": question_windows,
            "answer_windows": answer_windows,
            "question_vectors": question_vectors,
            "answer_vectors": answer_vectors,
        }

    def _reduce_prepared(
        self,
        *,
        input_text: str,
        output_text: str,
        question_windows: list[dict[str, Any]],
        answer_windows: list[dict[str, Any]],
        question_vectors: list[Vector],
        answer_vectors: list[Vector],
        anchor_vector: Vector,
        mode: str,
    ) -> ReducedQA:
        input_tokens = self._count_tokens(input_text)
        output_tokens = self._count_tokens(output_text)

        q_budget, a_budget = self._allocate_qa_budget(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        reduced_question, surviving_q_vectors, q_diag = self._reduce_side(
            text=input_text,
            windows=question_windows,
            vectors=question_vectors,
            anchor_vector=anchor_vector,
            token_budget=q_budget,
            side="question",
        )

        reduced_answer, surviving_a_vectors, a_diag = self._reduce_side(
            text=output_text,
            windows=answer_windows,
            vectors=answer_vectors,
            anchor_vector=anchor_vector,
            token_budget=a_budget,
            side="answer",
        )

        diagnostics = {
            "mode": mode,
            "embedding_model": self.embedding_model,
            "max_tokens_total": self.max_tokens_total,
            "question_max_tokens": self.question_max_tokens,
            "input_tokens_estimated": input_tokens,
            "output_tokens_estimated": output_tokens,
            "question_budget": q_budget,
            "answer_budget": a_budget,
            "question_vector_count_before": len(question_vectors),
            "answer_vector_count_before": len(answer_vectors),
            "question_vector_count_after": len(surviving_q_vectors),
            "answer_vector_count_after": len(surviving_a_vectors),
            "question": q_diag,
            "answer": a_diag,
        }

        logger_dev(
            "MemorySentenceReducer result\n"
            + self._safe_json_dump(
                {
                    "diagnostics": diagnostics,
                    "reduced_question": reduced_question,
                    "reduced_answer": reduced_answer,
                }
            ),
            "DEBUG",
            "CONFIDENTIAL",
        )

        return ReducedQA(
            reduced_question=reduced_question,
            reduced_answer=reduced_answer,
            question_vectors=surviving_q_vectors,
            answer_vectors=surviving_a_vectors,
            diagnostics=diagnostics,
        )

    def _allocate_qa_budget(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
    ) -> tuple[int, int]:
        total_tokens = max(1, int(input_tokens) + int(output_tokens))

        proportional_q = round(self.max_tokens_total * (int(input_tokens) / total_tokens))
        q_budget = min(int(proportional_q), self.question_max_tokens)

        if input_tokens > 0 and q_budget <= 0:
            q_budget = min(self.question_max_tokens, self.max_tokens_total)

        a_budget = max(0, self.max_tokens_total - q_budget)

        return q_budget, a_budget

    def _reduce_side(
        self,
        *,
        text: str,
        windows: list[dict[str, Any]],
        vectors: list[Vector],
        anchor_vector: Vector,
        token_budget: int,
        side: str,
    ) -> tuple[str, list[Vector], dict[str, Any]]:
        clean_text = str(text or "").strip()
        if not clean_text or token_budget <= 0:
            return "", [], {
                "side": side,
                "reason": "empty_or_zero_budget",
                "token_budget": token_budget,
            }

        original_tokens = self._count_tokens(clean_text)

        if original_tokens <= token_budget:
            # No reduction needed.
            # Still return all vectors, because the relevance gate needs them.
            return clean_text, list(vectors), {
                "side": side,
                "reason": "already_below_budget",
                "original_tokens_estimated": original_tokens,
                "token_budget": token_budget,
                "window_count": len(windows),
                "surviving_vector_count": len(vectors),
            }

        sentences = self._split_sentences(clean_text)

        if not windows or not vectors:
            return clean_text[: max(1, token_budget * 4)], [], {
                "side": side,
                "reason": "no_windows_or_vectors_fallback",
                "original_tokens_estimated": original_tokens,
                "token_budget": token_budget,
            }

        scored: list[dict[str, Any]] = []
        max_count = min(len(windows), len(vectors))

        for idx in range(max_count):
            item = windows[idx]
            vector = vectors[idx]

            scored.append(
                {
                    "window_index": idx,
                    "score": self._cosine(vector, anchor_vector),
                    "text": item["text"],
                    "sentence_indexes": item["sentence_indexes"],
                    "vector": vector,
                    "tokens": self._count_tokens(item["text"]),
                }
            )

        scored.sort(key=lambda item: item["score"], reverse=True)

        selected: list[dict[str, Any]] = []
        selected_sentence_indexes: set[int] = set()
        used_window_tokens = 0

        for candidate in scored:
            if used_window_tokens + int(candidate["tokens"]) > token_budget:
                continue

            if self._is_redundant(candidate["vector"], selected):
                continue

            selected.append(candidate)
            used_window_tokens += int(candidate["tokens"])
            selected_sentence_indexes.update(candidate["sentence_indexes"])

        if not selected and scored:
            first = scored[0]
            selected.append(first)
            selected_sentence_indexes.update(first["sentence_indexes"])

        reduced_sentences: list[str] = []
        used_tokens = 0

        for sentence_index in sorted(selected_sentence_indexes):
            if sentence_index < 0 or sentence_index >= len(sentences):
                continue

            sentence = sentences[sentence_index]
            sentence_tokens = self._count_tokens(sentence)

            if used_tokens + sentence_tokens > token_budget:
                continue

            reduced_sentences.append(sentence)
            used_tokens += sentence_tokens

        reduced_text = " ".join(reduced_sentences).strip()

        if not reduced_text and selected:
            # Last-resort fallback:
            # If one sentence is longer than the budget, keep a bounded text slice.
            reduced_text = str(selected[0].get("text", "") or "")[: max(1, token_budget * 4)].strip()

        surviving_vectors = [list(item["vector"]) for item in selected]

        return reduced_text, surviving_vectors, {
            "side": side,
            "reason": "reduced",
            "original_tokens_estimated": original_tokens,
            "token_budget": token_budget,
            "window_count": len(windows),
            "selected_window_count": len(selected),
            "selected_sentence_count": len(reduced_sentences),
            "surviving_vector_count": len(surviving_vectors),
            "reduced_tokens_estimated": self._count_tokens(reduced_text),
        }

    def _is_redundant(
        self,
        candidate_vector: Vector,
        selected: list[dict[str, Any]],
    ) -> bool:
        for item in selected:
            existing_vector = item.get("vector") or []
            if self._cosine(candidate_vector, existing_vector) >= self.redundancy_threshold:
                return True
        return False

    def _build_sentence_windows(self, text: str) -> list[dict[str, Any]]:
        sentences = self._split_sentences(text)
        return self._build_windows_from_sentences(sentences)

    def _build_windows_from_sentences(
        self,
        sentences: list[str],
    ) -> list[dict[str, Any]]:
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
            text = " ".join(sentences[start:end]).strip()

            if text:
                windows.append(
                    {
                        "text": text,
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
    def _count_tokens(text: str) -> int:
        clean = str(text or "")
        if not clean:
            return 0

        try:
            import tiktoken  # type: ignore

            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(clean))
        except Exception:
            return max(1, math.ceil(len(clean) / 4))

    @staticmethod
    def _safe_json_dump(data: Any) -> str:
        import json

        try:
            return json.dumps(data, ensure_ascii=False, indent=2, default=str)
        except Exception:
            return repr(data)