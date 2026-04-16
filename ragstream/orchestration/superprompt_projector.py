# superprompt_projector.py
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

        if self.sp.S_CTX_MD:
            parts.append(self.sp.S_CTX_MD)

        if self.sp.Attachments_MD:
            parts.append(self.sp.Attachments_MD)
        else:
            related_context_md = self._render_related_context_md()
            if related_context_md:
                parts.append(related_context_md)

        self.sp.prompt_ready = "\n\n".join(parts).strip()
        return self.sp.prompt_ready

    def _render_system_md(self) -> str:
        lines: List[str] = []

        system_value = (self.sp.body.get("system") or "").strip()
        role_value = (self.sp.body.get("role") or "").strip()
        audience_value = (self.sp.body.get("audience") or "").strip()
        tone_value = (self.sp.body.get("tone") or "").strip()
        depth_value = (self.sp.body.get("depth") or "").strip()

        if system_value:
            lines.append("## System")
            lines.append(system_value)

        config_lines: List[str] = []

        if role_value:
            config_lines.append(f"- Role: {role_value}")
        if audience_value:
            config_lines.append(f"- Audience: {audience_value}")
        if tone_value:
            config_lines.append(f"- Tone: {tone_value}")
        if depth_value:
            config_lines.append(f"- Depth: {depth_value}")

        if config_lines:
            if lines:
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

        if task_value:
            lines.append("## Task")
            lines.append(task_value)
            lines.append("")

        if purpose_value:
            lines.append("## Purpose")
            lines.append(purpose_value)
            lines.append("")

        if context_value:
            lines.append("## Context")
            lines.append(context_value)
            lines.append("")

        if format_value:
            lines.append("## Format")
            lines.append(format_value)
            lines.append("")

        if text_value:
            lines.append("## Text")
            lines.append(text_value)
            lines.append("")

        return "\n".join(lines).strip()

    def _format_score(self, score: float) -> str:
        return f"{float(score):.8f}".rstrip("0").rstrip(".")

    def _render_related_context_md(self) -> str:
        """
        Render a chunk-based context preview from the current selected chunks.

        During A3, show:
            selection_band at block level
            usefulness judgment per chunk
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
        lines.append("## Related Context")
        lines.append("")

        if self.sp.stage == "a3" and selection_band:
            lines.append(f"Selection band: {selection_band}")
            lines.append("")

        chunk_counter = 1
        for chunk_obj in ordered_chunks:
            header = f"### Chunk {chunk_counter}"

            emb_score = self._get_meta_float(chunk_obj.meta, "emb_score")
            splade_score = self._get_meta_float(chunk_obj.meta, "splade_score")

            if self.sp.stage == "retrieval":
                score_parts: List[str] = []

                rt_score = retrieval_score_map.get(chunk_obj.id)
                if rt_score is not None:
                    score_parts.append(f"Rt={self._format_score(rt_score)}")
                if emb_score is not None:
                    score_parts.append(f"Emb={self._format_score(emb_score)}")
                if splade_score is not None:
                    score_parts.append(f"Splade={self._format_score(splade_score)}")

                if score_parts:
                    header = f"{header} [{', '.join(score_parts)}]"

            elif self.sp.stage == "reranked":
                score_parts = []

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

                if score_parts:
                    header = f"{header} [{', '.join(score_parts)}]"

            elif self.sp.stage == "a3":
                decision = a3_decision_map.get(chunk_obj.id, {})
                usefulness = str(decision.get("usefulness_label", "") or "").strip()
                if usefulness:
                    header = f"{header} [Use={usefulness}]"

            lines.append(header)
            lines.append("")
            lines.append(chunk_obj.snippet.strip())
            lines.append("")
            chunk_counter += 1

        return "\n".join(lines).strip()

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