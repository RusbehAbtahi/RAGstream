# ragstream/memory/compression/memory_compressor.py
# -*- coding: utf-8 -*-
"""
MemoryCompressor
================

Runtime-only memory compression helper.

Current Part-I responsibility:
- receive effective_retrieval_query_text
- reduce it to the configured query token budget
- embed the reduced query once
- use that query vector as anchor
- reduce selected episodic Q/A candidates with MemorySentenceReducer

Important:
- This does not modify MemoryRecord truth.
- This does not write .ragmem, .ragmeta.json, SQLite, or vectors.
- Compression output is query-dependent runtime data only.
"""

from __future__ import annotations

import math
import re

from typing import Any

from ragstream.ingestion.embedder import Embedder
from ragstream.memory.compression.memory_sentence_reducer import MemorySentenceReducer
from ragstream.textforge.RagLog import LogDeveloper as logger_dev

Vector = list[float]


class MemoryCompressor:
    def __init__(
        self,
        config: dict[str, Any] | None = None,
    ) -> None:
        runtime_config = dict(config or {})

        if "memory_compression" in runtime_config:
            cfg = dict(runtime_config.get("memory_compression", {}) or {})
        else:
            cfg = dict(runtime_config or {})

        self.config = cfg
        self.enabled = bool(cfg.get("enabled", True))

        query_cfg = dict(cfg.get("effective_query", {}) or {})
        episodic_cfg = dict(cfg.get("episodic_memory", {}) or {})

        self.query_max_tokens = int(query_cfg.get("max_tokens", 300))
        self.embedding_model = str(query_cfg.get("embedding_model", "text-embedding-3-small"))

        self.episodic_enabled = bool(episodic_cfg.get("enabled", True))
        self.episodic_max_tokens_total = int(episodic_cfg.get("max_tokens_total", 400))
        self.episodic_question_max_tokens = int(episodic_cfg.get("question_max_tokens", 150))

        self.window_size_sentences = int(episodic_cfg.get("window_size_sentences", 3))
        self.window_overlap_sentences = int(episodic_cfg.get("window_overlap_sentences", 1))
        self.redundancy_threshold = float(episodic_cfg.get("redundancy_threshold", 0.92))

        self._embedder = Embedder(model=self.embedding_model)

        self._episode_reducer = MemorySentenceReducer(
            max_tokens_total=self.episodic_max_tokens_total,
            question_max_tokens=self.episodic_question_max_tokens,
            window_size_sentences=self.window_size_sentences,
            window_overlap_sentences=self.window_overlap_sentences,
            redundancy_threshold=self.redundancy_threshold,
            embedding_model=self.embedding_model,
        )

    def is_enabled(self) -> bool:
        return bool(self.enabled)

    def compress_episodic_candidates(
        self,
        episodic_candidates: list[dict[str, Any]],
        effective_query_text: str,
    ) -> list[dict[str, Any]]:
        """
        Reduce episodic Q/A candidates against one query anchor vector.

        The returned candidates keep all original candidate keys and add
        compressed runtime-only fields.
        """
        candidates = list(episodic_candidates or [])

        if not self.enabled or not self.episodic_enabled:
            logger_dev(
                "MEMORY COMPRESSION SKIPPED\n"
                + str(
                    {
                        "reason": "disabled",
                        "enabled": self.enabled,
                        "episodic_enabled": self.episodic_enabled,
                        "candidate_count": len(candidates),
                    }
                ),
                "DEBUG",
                "CONFIDENTIAL",
            )
            return candidates

        query_info = self.build_query_anchor(effective_query_text)
        query_anchor_vector = list(query_info.get("query_anchor_vector", []) or [])

        if not query_anchor_vector:
            logger_dev(
                "MEMORY COMPRESSION SKIPPED\n"
                + str(
                    {
                        "reason": "empty_query_anchor_vector",
                        "candidate_count": len(candidates),
                        "query_diagnostics": query_info.get("diagnostics", {}),
                        "reduced_query_text": query_info.get("reduced_query_text", ""),
                    }
                ),
                "DEBUG",
                "CONFIDENTIAL",
            )
            return candidates

        compressed: list[dict[str, Any]] = []

        for candidate in candidates:
            compressed.append(
                self.compress_episodic_candidate(
                    candidate=candidate,
                    query_anchor_vector=query_anchor_vector,
                    query_diagnostics=query_info.get("diagnostics", {}),
                )
            )

        logger_dev(
            "MEMORY COMPRESSION RESULT\n"
            + str(
                {
                    "candidate_count_before": len(candidates),
                    "candidate_count_after": len(compressed),
                    "query_original_tokens_estimated": self._count_tokens(effective_query_text),
                    "query_reduced_tokens_estimated": self._count_tokens(
                        str(query_info.get("reduced_query_text", "") or "")
                    ),
                    "reduced_query_text": str(query_info.get("reduced_query_text", "") or ""),
                    "episodes": [
                        {
                            "record_id": str(item.get("record_id", "") or ""),
                            "memory_compression_mode": str(item.get("memory_compression_mode", "") or ""),
                            "input_tokens_before": self._count_tokens(str(item.get("input_text", "") or "")),
                            "output_tokens_before": self._count_tokens(str(item.get("output_text", "") or "")),
                            "compressed_input_tokens": self._count_tokens(str(item.get("compressed_input_text", "") or "")),
                            "compressed_output_tokens": self._count_tokens(str(item.get("compressed_output_text", "") or "")),
                            "compressed_input_text": str(item.get("compressed_input_text", "") or ""),
                            "compressed_output_text": str(item.get("compressed_output_text", "") or ""),
                        }
                        for item in compressed
                    ],
                }
            ),
            "DEBUG",
            "CONFIDENTIAL",
        )

        return compressed

    def compress_episodic_candidate(
        self,
        *,
        candidate: dict[str, Any],
        query_anchor_vector: Vector,
        query_diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Reduce one episodic MemoryRecord candidate.

        Original input_text/output_text stay unchanged in the candidate.
        Reduced Q/A is added as runtime compression fields.
        """
        item = dict(candidate or {})

        input_text = str(item.get("input_text", "") or "")
        output_text = str(item.get("output_text", "") or "")

        reduced = self._episode_reducer.reduce_with_anchor(
            input_text=input_text,
            output_text=output_text,
            anchor_vector=query_anchor_vector,
        )

        item["compressed_input_text"] = reduced.reduced_question
        item["compressed_output_text"] = reduced.reduced_answer
        item["memory_compression_mode"] = "query_anchor_episode"
        item["memory_compression_query_diagnostics"] = dict(query_diagnostics or {})
        item["memory_compression_diagnostics"] = reduced.diagnostics

        return item

    def build_query_anchor(
        self,
        effective_query_text: str,
    ) -> dict[str, Any]:
        """
        Reduce effective query to max query_max_tokens and embed it once.
        """
        original_query = str(effective_query_text or "").strip()
        reduced_query = self.reduce_query_text(original_query)

        if not reduced_query:
            return {
                "reduced_query_text": "",
                "query_anchor_vector": [],
                "diagnostics": {
                    "reason": "empty_query",
                    "query_max_tokens": self.query_max_tokens,
                },
            }

        query_anchor_vector = self._embed_query(reduced_query)

        return {
            "reduced_query_text": reduced_query,
            "query_anchor_vector": query_anchor_vector,
            "diagnostics": {
                "mode": "query_anchor",
                "embedding_model": self.embedding_model,
                "query_max_tokens": self.query_max_tokens,
                "original_query_tokens_estimated": self._count_tokens(original_query),
                "reduced_query_tokens_estimated": self._count_tokens(reduced_query),
            },
        }

    def reduce_query_text(
        self,
        query_text: str,
    ) -> str:
        """
        Reduce query text to query_max_tokens by preserving sentence order.

        This is deterministic. It removes sentences beyond the budget.
        It does not call an LLM.
        """
        clean = str(query_text or "").strip()
        if not clean:
            return ""

        if self._count_tokens(clean) <= self.query_max_tokens:
            return clean

        sentences = self._split_sentences(clean)

        if not sentences:
            return clean[: max(1, self.query_max_tokens * 4)].strip()

        selected: list[str] = []
        used_tokens = 0

        for sentence in sentences:
            sentence = str(sentence or "").strip()
            if not sentence:
                continue

            sentence_tokens = self._count_tokens(sentence)

            if used_tokens + sentence_tokens > self.query_max_tokens:
                continue

            selected.append(sentence)
            used_tokens += sentence_tokens

        if selected:
            return " ".join(selected).strip()

        return sentences[0][: max(1, self.query_max_tokens * 4)].strip()

    def _embed_query(
        self,
        query_text: str,
    ) -> Vector:
        vectors = self._embedder.embed([query_text])
        vector = vectors[0]

        if hasattr(vector, "tolist"):
            vector = vector.tolist()

        return [float(value) for value in vector]

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