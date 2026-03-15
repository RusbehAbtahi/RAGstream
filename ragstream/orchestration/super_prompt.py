# -*- coding: utf-8 -*-
"""
SuperPrompt (v1) — central prompt object (manual __init__, no dataclass).
Place at: ragstream/orchestration/super_prompt.py

Notes (agreed pipeline choices; for reference only):
- Retrieval aggregation: LogAvgExp (length-normalized LogSumExp) with τ = 9 over per-piece cosine sims.
- Re-ranker: cross-encoder/ms-marco-MiniLM-L-6-v2 on (Prompt_MD, chunk_text).
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Literal
from enum import Enum

# Lifecycle stages for this SuperPrompt (fixed vocabulary)
Stage = Literal["raw", "preprocessed", "a2", "retrieval", "reranked", "a3", "a4", "a5"]


class A3ChunkStatus(str, Enum):
    SELECTED = "selected"
    DISCARDED = "discarded"
    DUPLICATED = "duplicated"


class SuperPrompt:
    __slots__ = (
        # session / lifecycle
        "stage",                 # string in Stage: current lifecycle state (e.g., "retrieval", "a3")
        "model_target",          # string or None: target LLM/model name for this session
        "history_of_stages",     # list[str]: append-only history of visited stages (e.g., ["raw","preprocessed","a2",...])

        # canonical prompt data
        "body",                  # dict: canonical fields from user (system, task, audience, tone, depth, context, purpose, format, text)
        "extras",                # dict: user-defined fields

        # retrieval artifacts
        "base_context_chunks",   # list[Chunk]: authoritative set of retrieved Chunk objects (combined from history + long-term memory)
        "views_by_stage",        # dict[str, list[tuple[str, float, A3ChunkStatus]]]: per stage, ordered (chunk_id, stage_score, stage_status)
        "final_selection_ids",   # list[str]: current chosen chunk_ids (from latest view after filters + token budget)

        # recent conversation (separate block)
        "recentConversation",    # dict: e.g., {"body": full transcript string, "pairs_count": N, "range": (start_idx, end_idx)}

        # rendered strings (set externally when sending to LLM; may be kept empty until render time)
        "System_MD",             # string: high-authority system/config block rendered from body (role/tone/depth/rules)
        "Prompt_MD",             # string: normalized user ask rendered from body (task/purpose/context/format)
        "S_CTX_MD",              # string: short distilled summary from final_selection_ids (facts/constraints/open issues)
        "Attachments_MD",        # string: formatted raw excerpts with provenance fences from final_selection_ids
        "prompt_ready"           # string: fully composed prompt ready to display/send.
    )

    def __init__(
        self,
        *,
        stage: Stage = "raw",
        model_target: Optional[str] = None,
    ) -> None:
        # session / lifecycle
        self.stage: Stage = stage
        self.model_target: Optional[str] = model_target
        self.history_of_stages: List[str] = []  # filled by caller/controller as stages are completed

        # canonical prompt data (each instance gets its own dict)
        self.body: Dict[str, Optional[str]] = {
            "system": "consultant",   # must-use default
            "task": None,             # must be set by caller
            "audience": None,
            "role": None,
            "tone": "neutral",
            "depth": "high",
            "context": None,
            "purpose": None,
            "format": None,
            "text": None,
        }
        self.extras: Dict[str, Any] = {}        # free-form, user-defined metadata

        # retrieval artifacts
        self.base_context_chunks: List["Chunk"] = []  # authoritative working set of Chunk objects (no duplicates)

        # stage name -> ordered list of per-chunk stage snapshots:
        # (chunk_id, stage_score, stage_status)
        #
        # Intended stage-local meaning:
        # - Retrieval:
        #     stage_score  = cosine similarity score
        #     stage_status = A3ChunkStatus.SELECTED
        #
        # - ReRanker:
        #     stage_score  = reranker score
        #     stage_status = A3ChunkStatus.SELECTED for kept chunks,
        #                    optionally A3ChunkStatus.DISCARDED for cut-off chunks
        #
        # - A3:
        #     stage_score  = 1.0 for pass / keep, 0.0 for reject
        #     stage_status = A3ChunkStatus.SELECTED / DISCARDED / DUPLICATED
        #
        # The list is always ordered according to the active stage view.
        self.views_by_stage: Dict[str, List[tuple[str, float, A3ChunkStatus]]] = {}

        self.final_selection_ids: List[str] = []        # the ids chosen for render after all filters/budgets

        # recent conversation block (kept separate from retrieved context)
        self.recentConversation: Dict[str, Any] = {}    # e.g., {"body": "...", "pairs_count": 3, "range": (12,14)}

        # rendered strings (filled by the caller at send time; may remain empty otherwise)
        self.System_MD: str = ""       # rendered from body (system/role/tone/depth)
        self.Prompt_MD: str = ""       # rendered from body (task/purpose/context/format)
        self.S_CTX_MD: str = ""        # rendered summary from final_selection_ids
        self.Attachments_MD: str = ""  # rendered excerpts from final_selection_ids with provenance
        self.prompt_ready: str = ""    # fully composed prompt ready to display/send

    def compose_prompt_ready(self) -> str:
        """
        Central render method for the current SuperPrompt.

        Purpose:
        - Build a single display/send-ready markdown text from the current object state.
        - Work already for PreProcessing and A2, where no chunks exist yet.
        - Also work for Retrieval and later stages, where chunk-based context may exist.
        - Replace the stage-local external compose functions in the future, so prompt
          rendering lives in one central place.

        Current behaviour:
        - Rebuild self.System_MD from self.body
        - Rebuild self.Prompt_MD from self.body
        - Keep self.S_CTX_MD and self.Attachments_MD if some later stage has already set them
        - If no later-stage attachments exist, render a simple "Related Context" section
          from the currently selected chunks
        - Write the final combined markdown into self.prompt_ready

        Returns:
            The final composed markdown string.
        """
        self.System_MD = self._render_system_md()
        self.Prompt_MD = self._render_prompt_md()

        parts: List[str] = []

        if self.System_MD:
            parts.append(self.System_MD)

        if self.Prompt_MD:
            parts.append(self.Prompt_MD)

        if self.S_CTX_MD:
            parts.append(self.S_CTX_MD)

        if self.Attachments_MD:
            parts.append(self.Attachments_MD)
        else:
            related_context_md = self._render_related_context_md()
            if related_context_md:
                parts.append(related_context_md)

        self.prompt_ready = "\n\n".join(parts).strip()
        return self.prompt_ready

    def _render_system_md(self) -> str:
        """
        Render the high-authority system/config part from self.body.

        This method is intentionally deterministic and simple.
        It does not depend on retrieval artifacts.
        """
        lines: List[str] = []

        system_value = (self.body.get("system") or "").strip()
        role_value = (self.body.get("role") or "").strip()
        audience_value = (self.body.get("audience") or "").strip()
        tone_value = (self.body.get("tone") or "").strip()
        depth_value = (self.body.get("depth") or "").strip()

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
        """
        Render the user-facing prompt part from self.body.

        This method is designed to cover:
        - raw / preprocessed / a2 stages without any chunk context
        - later stages as well, because the canonical prompt body remains the same
        """
        lines: List[str] = []

        task_value = (self.body.get("task") or "").strip()
        purpose_value = (self.body.get("purpose") or "").strip()
        context_value = (self.body.get("context") or "").strip()
        format_value = (self.body.get("format") or "").strip()
        text_value = (self.body.get("text") or "").strip()

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

    def _render_related_context_md(self) -> str:
        """
        Render a simple chunk-based context preview from the current selected chunks.

        Design intention:
        - The GUI should show only the selected chunk texts.
        - Technical metadata such as ID, source, score, status, and span remain
          inside SuperPrompt as internal structured data and are not rendered here.
        - If no chunks exist yet, this method returns an empty string and the caller
          simply skips the section.
        """
        ordered_chunks = self._get_ordered_context_chunks()
        if not ordered_chunks:
            return ""

        lines: List[str] = []
        lines.append("## Related Context")
        lines.append("")

        chunk_counter = 1
        for chunk_obj in ordered_chunks:
            lines.append(f"### Chunk {chunk_counter}")
            lines.append("")
            lines.append(chunk_obj.snippet.strip())
            lines.append("")
            chunk_counter += 1

        return "\n".join(lines).strip()

    def _get_ordered_context_chunks(self) -> List["Chunk"]:
        """
        Return the currently relevant chunks in the intended display order.

        Order policy:
        1. If final_selection_ids exists, use that order.
        2. Otherwise, if the current stage has a view in views_by_stage, use that order.
        3. Otherwise, fall back to the raw order of base_context_chunks.

        This keeps the render logic general enough for Retrieval, ReRanker, A3,
        and future later stages.
        """
        if not self.base_context_chunks:
            return []

        chunk_by_id: Dict[str, "Chunk"] = {}
        for chunk_obj in self.base_context_chunks:
            chunk_by_id[chunk_obj.id] = chunk_obj

        ordered_chunks: List["Chunk"] = []

        if self.final_selection_ids:
            for chunk_id in self.final_selection_ids:
                if chunk_id in chunk_by_id:
                    ordered_chunks.append(chunk_by_id[chunk_id])
            return ordered_chunks

        if self.stage in self.views_by_stage:
            stage_rows = self.views_by_stage[self.stage]
            for row in stage_rows:
                chunk_id = row[0]
                if chunk_id in chunk_by_id:
                    ordered_chunks.append(chunk_by_id[chunk_id])
            return ordered_chunks

        for chunk_obj in self.base_context_chunks:
            ordered_chunks.append(chunk_obj)

        return ordered_chunks

    def __repr__(self) -> str:
        return f"SuperPrompt(stage={self.stage!r})"