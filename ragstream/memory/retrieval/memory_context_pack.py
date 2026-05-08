# ragstream/memory/retrieval/memory_context_pack.py
# -*- coding: utf-8 -*-
"""
MemoryContextPack
=================
Runtime container for Memory Retrieval results.

This object is NOT durable memory truth.
It is only the run-local candidate package written into SuperPrompt after
the Retrieval button has run.

It keeps raw memory candidates available for later stages:
- Memory compression
- Memory synthesis / MemoryMerge
- final PromptBuilder rendering
"""

from __future__ import annotations

import json

from typing import Any


class MemoryContextPack:
    """
    Structured runtime result of Memory Retrieval.

    The pack separates memory candidates by retrieval role so later stages can
    decide what to do with each group independently.
    """

    def __init__(self) -> None:
        # Recent non-Black records from the active memory file.
        self.working_memory_candidates: list[dict[str, Any]] = []

        # Parent MemoryRecord candidates selected from semantic scoring and Gold lookup.
        self.episodic_candidates: list[dict[str, Any]] = []

        # Raw question/answer vector-hit chunks selected for later synthesis.
        self.semantic_memory_chunks: list[dict[str, Any]] = []

        # One Direct Recall candidate, usually selected by exact key lookup.
        self.direct_recall_candidate: dict[str, Any] | None = None

        # Final synthesized query-relevant Memory Context.
        self.synthesized_memory_context: str = ""

        # Diagnostics from MemoryMerge synthesis.
        self.memory_synthesis_diagnostics: dict[str, Any] = {}

        # Human/developer-readable explanation of selections and exclusions.
        self.selection_diagnostics: dict[str, Any] = {}

        # Token information is only estimated here; MemoryMerge later owns trimming.
        self.token_budget_report: dict[str, Any] = {}

    def add_working_memory(self, candidate: dict[str, Any]) -> None:
        """Add one recent working-memory candidate."""
        if candidate:
            self.working_memory_candidates.append(candidate)

    def add_episodic_candidate(self, candidate: dict[str, Any]) -> None:
        """Add one episodic parent MemoryRecord candidate."""
        if candidate:
            self.episodic_candidates.append(candidate)

    def add_semantic_chunk(self, candidate: dict[str, Any]) -> None:
        """Add one raw semantic memory chunk candidate."""
        if candidate:
            self.semantic_memory_chunks.append(candidate)

    def set_direct_recall(self, candidate: dict[str, Any] | None) -> None:
        """Set the Direct Recall candidate for this run."""
        self.direct_recall_candidate = candidate if candidate else None

    def set_synthesized_memory_context(
        self,
        memory_context: str,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        """Store the final synthesized Memory Context for this run."""
        self.synthesized_memory_context = str(memory_context or "").strip()
        self.memory_synthesis_diagnostics = dict(diagnostics or {})

    def set_selection_diagnostics(self, diagnostics: dict[str, Any]) -> None:
        """Store diagnostic information explaining the retrieval result."""
        self.selection_diagnostics = diagnostics or {}

    def set_token_budget_report(self, report: dict[str, Any]) -> None:
        """Store estimated token usage before later MemoryMerge compression."""
        self.token_budget_report = report or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert the pack into a plain dictionary for SuperPrompt.extras."""
        return {
            "working_memory_candidates": self.working_memory_candidates,
            "episodic_candidates": self.episodic_candidates,
            "semantic_memory_chunks": self.semantic_memory_chunks,
            "direct_recall_candidate": self.direct_recall_candidate,
            "synthesized_memory_context": self.synthesized_memory_context,
            "memory_synthesis_diagnostics": self.memory_synthesis_diagnostics,
            "selection_diagnostics": self.selection_diagnostics,
            "token_budget_report": self.token_budget_report,
            "counts": self.counts(),
        }

    def counts(self) -> dict[str, int]:
        """Return compact candidate counts for logs and GUI status."""
        return {
            "working_memory_candidates": len(self.working_memory_candidates),
            "episodic_candidates": len(self.episodic_candidates),
            "semantic_memory_chunks": len(self.semantic_memory_chunks),
            "direct_recall_candidate": 1 if self.direct_recall_candidate else 0,
            "synthesized_memory_context": 1 if self.synthesized_memory_context else 0,
        }

    def to_debug_markdown(self) -> str:
        """
        Render raw memory candidates for developer inspection.

        This is intentionally not final prompt context.
        The GUI projector no longer shows this raw memory block by default.
        """
        lines: list[str] = []

        lines.append("### Raw Memory Retrieval Candidates")
        lines.append("")
        lines.append("These are raw memory candidates produced by the Retrieval stage.")
        lines.append("They are not final prompt context.")
        lines.append("")

        self._append_synthesized_memory_context(lines)
        self._append_working_memory(lines)
        self._append_episodic_memory(lines)
        self._append_semantic_chunks(lines)
        self._append_direct_recall(lines)
        self._append_diagnostics(lines)

        return "\n".join(lines).strip()

    def _append_synthesized_memory_context(self, lines: list[str]) -> None:
        lines.append("#### Synthesized Memory Context")
        if not self.synthesized_memory_context:
            lines.append("(none)")
            lines.append("")
            return

        lines.append("```text")
        lines.append(self.synthesized_memory_context)
        lines.append("```")
        lines.append("")

    def _append_working_memory(self, lines: list[str]) -> None:
        lines.append("#### Working Memory Candidates")
        if not self.working_memory_candidates:
            lines.append("(none)")
            lines.append("")
            return

        for idx, candidate in enumerate(self.working_memory_candidates, start=1):
            lines.append(f"**W{idx}. record_id:** `{candidate.get('record_id', '')}`")
            lines.append(f"- tag: `{candidate.get('tag', '')}`")
            lines.append(f"- retrieval_source_mode: `{candidate.get('retrieval_source_mode', '')}`")
            lines.append("")
            lines.append(self._format_qa(candidate))
            lines.append("")

    def _append_episodic_memory(self, lines: list[str]) -> None:
        lines.append("#### Episodic Candidates")
        if not self.episodic_candidates:
            lines.append("(none)")
            lines.append("")
            return

        for idx, candidate in enumerate(self.episodic_candidates, start=1):
            final_score = candidate.get("final_parent_score", candidate.get("score", ""))
            semantic_score = candidate.get("semantic_parent_score", "")
            recency_score = candidate.get("recency_score", "")
            episode_distance_k = candidate.get("episode_distance_k", "")

            lines.append(f"**E{idx}. record_id:** `{candidate.get('record_id', '')}`")
            lines.append(f"- tag: `{candidate.get('tag', '')}`")
            lines.append(f"- final_score: `{final_score}`")
            lines.append(f"- semantic_score: `{semantic_score}`")
            lines.append(f"- recency_score: `{recency_score}`")
            lines.append(f"- episode_distance_k: `{episode_distance_k}`")
            lines.append(f"- retrieval_source_mode: `{candidate.get('retrieval_source_mode', '')}`")
            lines.append("")
            lines.append(self._format_qa(candidate))
            lines.append("")

    def _append_semantic_chunks(self, lines: list[str]) -> None:
        lines.append("#### Semantic Memory Chunks")
        if not self.semantic_memory_chunks:
            lines.append("(none)")
            lines.append("")
            return

        for idx, candidate in enumerate(self.semantic_memory_chunks, start=1):
            lines.append(f"**M{idx}. vector_id:** `{candidate.get('vector_id', candidate.get('id', ''))}`")
            lines.append(f"- record_id: `{candidate.get('record_id', '')}`")
            lines.append(f"- role: `{candidate.get('role', '')}`")
            lines.append(f"- final_score: `{candidate.get('score', '')}`")
            lines.append(f"- semantic_score: `{candidate.get('semantic_score', '')}`")
            lines.append(f"- recency_score: `{candidate.get('recency_score', '')}`")
            lines.append(f"- episode_distance_k: `{candidate.get('episode_distance_k', '')}`")
            lines.append("")
            text = str(candidate.get("document", candidate.get("text", ""))).strip()
            if text:
                lines.append("```text")
                lines.append(text)
                lines.append("```")
            lines.append("")

    def _append_direct_recall(self, lines: list[str]) -> None:
        lines.append("#### Direct Recall Candidate")
        if not self.direct_recall_candidate:
            lines.append("(none)")
            lines.append("")
            return

        candidate = self.direct_recall_candidate
        lines.append(f"**record_id:** `{candidate.get('record_id', '')}`")
        lines.append(f"- file_id: `{candidate.get('file_id', '')}`")
        lines.append(f"- tag: `{candidate.get('tag', '')}`")
        lines.append(f"- direct_recall_key: `{candidate.get('direct_recall_key', '')}`")
        lines.append("")
        lines.append(self._format_qa(candidate))
        lines.append("")

    def _append_diagnostics(self, lines: list[str]) -> None:
        lines.append("#### Selection Diagnostics")
        if not self.selection_diagnostics and not self.memory_synthesis_diagnostics:
            lines.append("(none)")
            lines.append("")
            return

        diagnostics = {
            "selection_diagnostics": self.selection_diagnostics,
            "memory_synthesis_diagnostics": self.memory_synthesis_diagnostics,
        }

        lines.append("```json")
        lines.append(json.dumps(diagnostics, ensure_ascii=False, indent=2, default=str))
        lines.append("```")
        lines.append("")

    @staticmethod
    def _format_qa(candidate: dict[str, Any]) -> str:
        input_text = str(candidate.get("compressed_input_text", candidate.get("input_text", "")) or "").strip()
        output_text = str(candidate.get("compressed_output_text", candidate.get("output_text", "")) or "").strip()

        lines: list[str] = []

        if input_text:
            lines.append("INPUT")
            lines.append("```text")
            lines.append(input_text)
            lines.append("```")

        if output_text:
            lines.append("OUTPUT")
            lines.append("```text")
            lines.append(output_text)
            lines.append("```")

        return "\n".join(lines).strip() if lines else "(no Q/A body available)"