# super_prompt.py
# -*- coding: utf-8 -*-
"""
SuperPrompt (v1) — central prompt object (manual __init__, no dataclass).
Place at: ragstream/orchestration/super_prompt.py

Notes (agreed pipeline choices; for reference only):
- Retrieval aggregation: LogAvgExp (length-normalized LogSumExp) with τ = 9 over per-piece cosine sims.
- Re-ranker: cross-encoder/ms-marco-MiniLM-L-6-v2 on (Prompt_MD, chunk_text).

Stage refactor note:
- SuperPrompt remains the authoritative shared state object.
- Projection / render / text-extraction support logic has been moved to
  superprompt_projector.py.
- compose_prompt_ready() remains here as the stable public wrapper so that
  external call sites do not need to change.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from ragstream.orchestration.superprompt_projector import SuperPromptProjector

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
        Stable public wrapper for the central SuperPrompt render path.

        Important compatibility rule:
        - External code may continue to call sp.compose_prompt_ready() exactly
          as before.
        - The real render / projection logic lives in SuperPromptProjector.
        """
        return SuperPromptProjector(self).compose_prompt_ready()

    def __repr__(self) -> str:
        return f"SuperPrompt(stage={self.stage!r})"