# ragstream/orchestration/superprompt_projector.py
# -*- coding: utf-8 -*-
"""
superprompt_projector.py

Purpose:
    Companion projection / render / text-extraction support for SuperPrompt.

Design:
    - SuperPrompt remains the authoritative shared state object.
    - This module owns derived render logic and text-oriented support logic.
    - compose_prompt_ready() remains publicly callable through the wrapper
      method on SuperPrompt for compatibility.
    - build_query_text(sp) also lives here, because it is a projection of
      SuperPrompt state into a retrieval-oriented text representation.
"""

from __future__ import annotations

from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ragstream.orchestration.super_prompt import SuperPrompt


class SuperPromptProjector:
    """
    Projection / render helper around one SuperPrompt instance.
    """

    def __init__(self, sp: "SuperPrompt") -> None:
        if sp is None:
            raise ValueError("SuperPromptProjector.__init__: 'sp' must not be None")
        self.sp = sp

    @staticmethod
    def build_query_text(sp: "SuperPrompt") -> str:
        if sp is None:
            raise ValueError("SuperPromptProjector.build_query_text: 'sp' must not be None")

        if not hasattr(sp, "body") or sp.body is None:
            raise ValueError("SuperPromptProjector.build_query_text: SuperPrompt has no usable 'body'")

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

        query_text = "\n".join(blocks).strip()

        if not query_text:
            raise ValueError(
                "SuperPromptProjector.build_query_text: retrieval query is empty. "
                "At least one of TASK / PURPOSE / CONTEXT must be present."
            )

        return query_text

    def compose_prompt_ready(self) -> str:
        self.sp.System_MD = self._render_system_md()
        self.sp.Prompt_MD = self._render_prompt_md()

        parts: List[str] = []

        if self.sp.System_MD:
            parts.append(self.sp.System_MD)

        if self.sp.Prompt_MD:
            parts.append(self.sp.Prompt_MD)

        retrieved_context_md = self._render_retrieved_context_md()
        if retrieved_context_md:
            parts.append(retrieved_context_md)

        if self.sp.Attachments_MD:
            parts.append(self.sp.Attachments_MD)

        self.sp.prompt_ready = "\n\n".join(parts).strip()
        return self.sp.prompt_ready

    def _render_system_md(self) -> str:
        lines: List[str] = []

        system_value = (self.sp.body.get("system") or "").strip()
        role_value = (self.sp.body.get("role") or "").strip()
        audience_value = (self.sp.body.get("audience") or "").strip()
        tone_value = (self.sp.body.get("tone") or "").strip()
        depth_value = (self.sp.body.get("depth") or "").strip()
        confidence_value = (self.sp.body.get("confidence") or "").strip()

        lines.append("## System")
        if system_value:
            lines.append(system_value)
        else:
            lines.append("")

        config_lines: List[str] = []

        if role_value:
            config_lines.append(f"- Role: {role_value}")
        if audience_value:
            config_lines.append(f"- Audience: {audience_value}")
        if tone_value:
            config_lines.append(f"- Tone: {tone_value}")
        if depth_value:
            config_lines.append(f"- Depth: {depth_value}")
        if confidence_value:
            config_lines.append(f"- Confidence: {confidence_value}")

        lines.append("")
        lines.append("## Configuration")
        lines.extend(config_lines)

        return "\n".join(lines).strip()

    def _render_prompt_md(self) -> str:
        lines: List[str] = []

        task_value = (self.sp.body.get("task") or "").strip()
        purpose_value = (self.sp.body.get("purpose") or "").strip()
        context_value = (self.sp.body.get("context") or "").strip()
        format_value = (self.sp.body.get("format") or "").strip()
        text_value = (self.sp.body.get("text") or "").strip()

        lines.append("## User")
        lines.append("")

        lines.append("### Task")
        lines.append(task_value)
        lines.append("")

        if purpose_value:
            lines.append("### Purpose")
            lines.append(purpose_value)
            lines.append("")

        if context_value:
            lines.append("### Context")
            lines.append(context_value)
            lines.append("")

        if format_value:
            lines.append("### Format")
            lines.append(format_value)
            lines.append("")

        if text_value:
            lines.append("### Text")
            lines.append(text_value)
            lines.append("")

        return "\n".join(lines).strip()

    def _render_retrieved_context_md(self) -> str:
        """
        Render retrieved/condensed context for GUI-visible SuperPrompt preview.

        Retrieval stage now has two raw candidate pools:
        - document chunks
        - memory candidates

        Both are rendered here as inspection/debug material.
        """
        lines: List[str] = []

        lines.append("## Retrieved Context")
        lines.append("")

        lines.append("### Retrieved Context Summary")
        lines.append(
            "The following summary is retrieved from selected project files or memory. "
            "It is supporting context for the task, not part of the task itself."
        )
        lines.append("")

        summary_text = (self.sp.S_CTX_MD or "").strip()
        if summary_text:
            lines.append(summary_text)
        lines.append("")

        lines.append("### Raw Retrieved Evidence")
        raw_evidence_md = self._render_raw_retrieved_evidence_md()
        if raw_evidence_md:
            lines.append(raw_evidence_md)

        raw_memory_md = self._render_raw_memory_retrieval_md()
        if raw_memory_md:
            lines.append("")
            lines.append(raw_memory_md)

        return "\n".join(lines).strip()

    def _render_raw_memory_retrieval_md(self) -> str:
        """
        Render raw memory retrieval candidates.

        MemoryRetriever writes the raw debug markdown into:
            sp.extras["memory_debug_markdown"]

        This is GUI inspection material only.
        It is not final compressed memory context.
        """
        extras = getattr(self.sp, "extras", {}) or {}
        memory_debug_md = str(extras.get("memory_debug_markdown", "") or "").strip()
        return memory_debug_md

    def _render_raw_retrieved_evidence_md(self) -> str:
        """
        Render raw retrieved document chunks as nested evidence.

        Source Markdown headings inside chunks are converted to [H1]/[H2]/[H3]
        so they do not compete with the visible SuperPrompt structure.
        """
        ordered_chunks = self._get_ordered_context_chunks()
        if not ordered_chunks:
            return ""

        retrieval_score_map: Dict[str, float] = {
            chunk_id: float(score)
            for chunk_id, score, _status in self.sp.views_by_stage.get("retrieval", [])
        }

        reranked_score_map: Dict[str, float] = {
            chunk_id: float(score)
            for chunk_id, score, _status in self.sp.views_by_stage.get("reranked", [])
        }

        a3_decision_map: Dict[str, Dict[str, Any]] = {}
        raw_a3_decisions = self.sp.extras.get("a3_item_decisions", {})
        if isinstance(raw_a3_decisions, dict):
            a3_decision_map = raw_a3_decisions

        selection_band = str(self.sp.extras.get("a3_selection_band", "") or "").strip()

        lines: List[str] = []
        lines.append("<retrieved_chunks>")

        if self.sp.stage == "a3" and selection_band:
            lines.append(f'  <selection_band>{selection_band}</selection_band>')

        chunk_counter = 1
        for chunk_obj in ordered_chunks:
            attributes: List[str] = [
                f'index="{chunk_counter}"',
                f'chunk_id="{self._escape_attr(str(chunk_obj.id))}"',
            ]

            source_value = ""
            meta = getattr(chunk_obj, "meta", None)
            if isinstance(meta, dict):
                source_value = str(meta.get("source") or meta.get("path") or meta.get("file") or "").strip()
            if source_value:
                attributes.append(f'source="{self._escape_attr(source_value)}"')

            score_label = self._build_chunk_score_label(
                chunk_obj=chunk_obj,
                retrieval_score_map=retrieval_score_map,
                reranked_score_map=reranked_score_map,
                a3_decision_map=a3_decision_map,
            )
            if score_label:
                attributes.append(f'info="{self._escape_attr(score_label)}"')

            lines.append(f"  <chunk {' '.join(attributes)}>")
            lines.append("    <chunk_text>")

            snippet = self._sanitize_chunk_text(chunk_obj.snippet.strip())
            if snippet:
                for snippet_line in snippet.splitlines():
                    lines.append(f"      {snippet_line}")

            lines.append("    </chunk_text>")
            lines.append("  </chunk>")
            chunk_counter += 1

        lines.append("</retrieved_chunks>")

        return "\n".join(lines).strip()

    def _build_chunk_score_label(
        self,
        *,
        chunk_obj: Any,
        retrieval_score_map: Dict[str, float],
        reranked_score_map: Dict[str, float],
        a3_decision_map: Dict[str, Dict[str, Any]],
    ) -> str:
        score_parts: List[str] = []

        emb_score = self._get_meta_float(chunk_obj.meta, "emb_score")
        splade_score = self._get_meta_float(chunk_obj.meta, "splade_score")

        if self.sp.stage == "retrieval":
            rt_score = retrieval_score_map.get(chunk_obj.id)
            if rt_score is not None:
                score_parts.append(f"Rt={self._format_score(rt_score)}")
            if emb_score is not None:
                score_parts.append(f"Emb={self._format_score(emb_score)}")
            if splade_score is not None:
                score_parts.append(f"Splade={self._format_score(splade_score)}")

        elif self.sp.stage == "reranked":
            rnk_score = reranked_score_map.get(chunk_obj.id)
            if rnk_score is None:
                rnk_score = self._get_meta_float(chunk_obj.meta, "rerank_rrf_score")

            rcolb_score = self._get_meta_float(chunk_obj.meta, "colbert_score")

            rt_score = self._get_meta_float(chunk_obj.meta, "retrieval_rrf_score")
            if rt_score is None:
                rt_score = self._get_meta_float(chunk_obj.meta, "retrieval_score")
            if rt_score is None:
                rt_score = retrieval_score_map.get(chunk_obj.id)

            if rnk_score is not None:
                score_parts.append(f"Rnk={self._format_score(rnk_score)}")
            if rcolb_score is not None:
                score_parts.append(f"RcolB={self._format_score(rcolb_score)}")
            if rt_score is not None:
                score_parts.append(f"Rt={self._format_score(rt_score)}")

        elif self.sp.stage == "a3":
            decision = a3_decision_map.get(chunk_obj.id, {})
            usefulness = str(decision.get("usefulness_label", "") or "").strip()
            if usefulness:
                score_parts.append(f"Use={usefulness}")

        return ", ".join(score_parts).strip()

    @staticmethod
    def _sanitize_chunk_text(text: str) -> str:
        """
        Prevent source Markdown headings from becoming real prompt headings.
        """
        if not text:
            return ""

        sanitized_lines: List[str] = []

        for line in text.splitlines():
            stripped = line.lstrip()
            indent = line[: len(line) - len(stripped)]

            if stripped.startswith("### "):
                sanitized_lines.append(f"{indent}[H3] {stripped[4:].strip()}")
            elif stripped.startswith("## "):
                sanitized_lines.append(f"{indent}[H2] {stripped[3:].strip()}")
            elif stripped.startswith("# "):
                sanitized_lines.append(f"{indent}[H1] {stripped[2:].strip()}")
            else:
                sanitized_lines.append(line)

        return "\n".join(sanitized_lines).strip()

    @staticmethod
    def _escape_attr(value: str) -> str:
        return (
            str(value or "")
            .replace("&", "&amp;")
            .replace('"', "&quot;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def _format_score(self, score: float) -> str:
        return f"{float(score):.8f}".rstrip("0").rstrip(".")

    def _render_related_context_md(self) -> str:
        """
        Backward-compatible wrapper.
        """
        return self._render_raw_retrieved_evidence_md()

    @staticmethod
    def _get_meta_float(meta: Dict[str, Any] | None, key: str) -> float | None:
        if not isinstance(meta, dict):
            return None

        value = meta.get(key)
        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _get_ordered_context_chunks(self) -> List["Chunk"]:
        if not self.sp.base_context_chunks:
            return []

        chunk_by_id: Dict[str, "Chunk"] = {}
        for chunk_obj in self.sp.base_context_chunks:
            chunk_by_id[chunk_obj.id] = chunk_obj

        ordered_chunks: List["Chunk"] = []

        if self.sp.stage == "a3" and "a3" in self.sp.views_by_stage:
            stage_rows = self.sp.views_by_stage["a3"]
            for row in stage_rows:
                chunk_id = row[0]
                if chunk_id in chunk_by_id:
                    ordered_chunks.append(chunk_by_id[chunk_id])
            return ordered_chunks

        if self.sp.final_selection_ids:
            for chunk_id in self.sp.final_selection_ids:
                if chunk_id in chunk_by_id:
                    ordered_chunks.append(chunk_by_id[chunk_id])
            return ordered_chunks

        if self.sp.stage in self.sp.views_by_stage:
            stage_rows = self.sp.views_by_stage[self.sp.stage]
            for row in stage_rows:
                chunk_id = row[0]
                if chunk_id in chunk_by_id:
                    ordered_chunks.append(chunk_by_id[chunk_id])
            return ordered_chunks

        for chunk_obj in self.sp.base_context_chunks:
            ordered_chunks.append(chunk_obj)

        return ordered_chunks