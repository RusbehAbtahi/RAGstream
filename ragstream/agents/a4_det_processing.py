# -*- coding: utf-8 -*-
"""
a4_det_processing.py

Deterministic helper functions for A4.

Imported by a4_condenser.py:
1) prepare_selected_chunks()
3) prepare_active_class_definitions()
5) build_grouped_chunk_package()
7) finalize_a4_output()
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
import re

from ragstream.orchestration.super_prompt import SuperPrompt, A3ChunkStatus
from ragstream.utils.logging import SimpleLogger


JsonDict = Dict[str, Any]


def prepare_selected_chunks(
    sp: SuperPrompt,
    *,
    max_candidates: int = 30,
) -> JsonDict:
    """
    Read A3 output, keep only useful chunks, assign fresh local ids 1..N,
    preserve A3 order, and build the shared repeated chunk/query blocks.
    """
    if sp is None:
        raise ValueError("prepare_selected_chunks: 'sp' must not be None")

    a3_rows = list(sp.views_by_stage.get("a3", []))[: int(max_candidates)]
    if not a3_rows:
        raise RuntimeError("prepare_selected_chunks: no A3 rows available")

    extras = getattr(sp, "extras", None) or {}
    item_decisions = extras.get("a3_item_decisions", {}) or {}

    chunk_by_id: Dict[str, Any] = {}
    for chunk in getattr(sp, "base_context_chunks", []) or []:
        chunk_by_id[str(chunk.id)] = chunk

    selected_items: List[Dict[str, Any]] = []
    local_to_real: Dict[str, str] = {}
    real_to_local: Dict[str, str] = {}

    next_local_index = 1
    for rank_index, row in enumerate(a3_rows, start=1):
        real_chunk_id = str(row[0])
        item_info = item_decisions.get(real_chunk_id, {}) or {}
        usefulness_label = str(item_info.get("usefulness_label", "") or "").strip().lower()

        if usefulness_label != "useful":
            continue

        chunk = chunk_by_id.get(real_chunk_id)
        if chunk is None:
            continue

        local_chunk_id = str(next_local_index)
        next_local_index += 1

        local_to_real[local_chunk_id] = real_chunk_id
        real_to_local[real_chunk_id] = local_chunk_id

        selected_items.append(
            {
                "local_chunk_id": local_chunk_id,
                "real_chunk_id": real_chunk_id,
                "a3_rank": rank_index,
                "source": str(getattr(chunk, "source", "") or ""),
                "snippet": _sanitize_chunk_text(str(getattr(chunk, "snippet", "") or "")),
                "chunk_obj": chunk,
            }
        )

    if not selected_items:
        raise RuntimeError("prepare_selected_chunks: A3 produced no useful chunks")

    user_prompt_under_evaluation = _build_user_prompt_under_evaluation(sp)
    evidence_chunks = _build_evidence_chunks_text(selected_items)

    return {
        "user_prompt_under_evaluation": user_prompt_under_evaluation,
        "evidence_chunks": evidence_chunks,
        "selected_items": selected_items,
        "local_to_real": local_to_real,
        "real_to_local": real_to_local,
        "ordered_real_ids": [item["real_chunk_id"] for item in selected_items],
    }


def prepare_active_class_definitions(
    *,
    phraser_result: JsonDict,
    classifier_agent_prompt: Any,
) -> JsonDict:
    """
    Read phraser output, keep only the active IDs actually returned,
    and mutate the classifier AgentPrompt so the visible class options are
    the real class phrases, not ID1 / ID2 / ...

    Important:
    - internal deterministic regrouping still uses the original IDs
    - classifier output is allowed to return class phrases
    - step 5 will map phrase -> original ID
    """
    raw_classes = list(phraser_result.get("class_definitions", []) or [])
    if not raw_classes:
        raise RuntimeError("prepare_active_class_definitions: no class_definitions returned")

    allowed_ids = ["ID1", "ID2", "ID3", "ID4"]
    active_classes: List[Dict[str, str]] = []

    for item in raw_classes:
        if not isinstance(item, dict):
            continue

        class_id = str(item.get("class_id", "") or "").strip()
        if class_id not in allowed_ids:
            continue

        class_phrase = str(item.get("class_phrase", "") or "").strip()
        class_context_text = str(item.get("class_context_text", "") or "").strip()

        if not class_phrase or not class_context_text:
            continue

        active_classes.append(
            {
                "class_id": class_id,
                "class_phrase": class_phrase,
                "class_context_text": class_context_text,
            }
        )

    if not active_classes:
        raise RuntimeError("prepare_active_class_definitions: no valid active classes")

    active_ids = [item["class_id"] for item in active_classes]
    active_class_phrases = [item["class_phrase"] for item in active_classes]

    phrase_to_id: Dict[str, str] = {}
    normalized_phrase_to_id: Dict[str, str] = {}
    for item in active_classes:
        phrase = item["class_phrase"]
        class_id = item["class_id"]
        phrase_to_id[phrase] = class_id
        normalized_phrase_to_id[_normalize_phrase_key(phrase)] = class_id

    # Mutate the classifier AgentPrompt locally for this A4 run only.
    # Goal: the model sees class phrases as the allowed labels, not ID1/ID2/...
    for target in getattr(classifier_agent_prompt, "decision_targets", []) or []:
        if str(target.get("id", "") or "").strip() == "class_id":
            target["options"] = list(active_class_phrases)
            target["min_selected"] = 1
            target["max_selected"] = 1

    if hasattr(classifier_agent_prompt, "enums"):
        classifier_agent_prompt.enums["class_id"] = list(active_class_phrases)

    if hasattr(classifier_agent_prompt, "defaults"):
        classifier_agent_prompt.defaults["class_id"] = active_class_phrases[0]

    # Make the classifier prompt lighter:
    # suppress the generic Decision Targets block entirely for this run.
    if hasattr(classifier_agent_prompt, "decision_targets"):
        classifier_agent_prompt.decision_targets = []

    active_class_definitions_text = _build_active_class_definitions_text(active_classes)

    return {
        "active_ids": active_ids,
        "active_classes": active_classes,
        "active_class_phrases": active_class_phrases,
        "phrase_to_id": phrase_to_id,
        "normalized_phrase_to_id": normalized_phrase_to_id,
        "active_class_definitions_text": active_class_definitions_text,
    }


def build_grouped_chunk_package(
    *,
    classifier_result: JsonDict,
    selected_payload: JsonDict,
    active_class_payload: JsonDict,
    effective_output_token_limit: int,
) -> JsonDict:
    """
    Regroup chunk ids deterministically by class, apply a simple budget profile,
    and build the final class-group text for the last A4 call.

    If classifier output is missing / unusable, continue in fallback mode:
    - keep all chunks in original order
    - provide only the global class overview to the final condenser
    - log a warning in CLI
    """
    selected_items = list(selected_payload.get("selected_items", []) or [])
    active_classes = list(active_class_payload.get("active_classes", []) or [])
    active_ids = [item["class_id"] for item in active_classes]

    phrase_to_id = dict(active_class_payload.get("phrase_to_id", {}) or {})
    normalized_phrase_to_id = dict(active_class_payload.get("normalized_phrase_to_id", {}) or {})

    raw_item_decisions = list(classifier_result.get("item_decisions", []) or [])
    class_by_local_chunk_id: Dict[str, str] = {}

    for item in raw_item_decisions:
        if not isinstance(item, dict):
            continue

        local_chunk_id = str(item.get("chunk_id", "") or "").strip()
        raw_class_value = str(item.get("class_id", "") or "").strip()

        if not local_chunk_id or not raw_class_value:
            continue

        mapped_class_id = _resolve_classifier_class_value(
            raw_class_value=raw_class_value,
            active_ids=active_ids,
            phrase_to_id=phrase_to_id,
            normalized_phrase_to_id=normalized_phrase_to_id,
        )
        if not mapped_class_id:
            continue

        class_by_local_chunk_id[local_chunk_id] = mapped_class_id

    token_limit = int(effective_output_token_limit)
    if token_limit <= 0:
        token_limit = 3000

    if len(class_by_local_chunk_id) < len(selected_items):
        SimpleLogger.warning(
            "A4 build_grouped_chunk_package: classifier output incomplete or unusable; "
            "continuing with fallback no-grouping mode."
        )
        return _build_fallback_chunk_package(
            selected_items=selected_items,
            active_classes=active_classes,
            token_limit=token_limit,
        )

    groups: List[Dict[str, Any]] = []
    group_by_class_id: Dict[str, Dict[str, Any]] = {}

    for priority_rank, class_item in enumerate(active_classes, start=1):
        group = {
            "class_id": class_item["class_id"],
            "priority_rank": priority_rank,
            "class_phrase": class_item["class_phrase"],
            "class_context_text": class_item["class_context_text"],
            "items": [],
        }
        groups.append(group)
        group_by_class_id[group["class_id"]] = group

    for item in selected_items:
        local_chunk_id = str(item["local_chunk_id"])
        class_id = class_by_local_chunk_id.get(local_chunk_id)
        if not class_id:
            SimpleLogger.warning(
                "A4 build_grouped_chunk_package: missing class after validation; "
                "continuing with fallback no-grouping mode."
            )
            return _build_fallback_chunk_package(
                selected_items=selected_items,
                active_classes=active_classes,
                token_limit=token_limit,
            )

        if class_id not in group_by_class_id:
            SimpleLogger.warning(
                "A4 build_grouped_chunk_package: classifier returned inactive class after validation; "
                "continuing with fallback no-grouping mode."
            )
            return _build_fallback_chunk_package(
                selected_items=selected_items,
                active_classes=active_classes,
                token_limit=token_limit,
            )

        group_by_class_id[class_id]["items"].append(item)

    non_empty_groups = [group for group in groups if group["items"]]
    if not non_empty_groups:
        SimpleLogger.warning(
            "A4 build_grouped_chunk_package: all groups are empty after regrouping; "
            "continuing with fallback no-grouping mode."
        )
        return _build_fallback_chunk_package(
            selected_items=selected_items,
            active_classes=active_classes,
            token_limit=token_limit,
        )

    if token_limit < 1200:
        max_group_count = 1
        budget_profile = "tight"
    elif token_limit < 1800:
        max_group_count = min(2, len(non_empty_groups))
        budget_profile = "narrow"
    elif token_limit < 2600:
        max_group_count = min(3, len(non_empty_groups))
        budget_profile = "medium"
    else:
        max_group_count = len(non_empty_groups)
        budget_profile = "broad"

    working_groups = non_empty_groups[:max_group_count]

    selected_real_ids_after_budget: List[str] = []
    for group in working_groups:
        for item in group["items"]:
            selected_real_ids_after_budget.append(str(item["real_chunk_id"]))

    class_groups_text = _build_class_groups_text(
        groups=working_groups,
        budget_profile=budget_profile,
        token_limit=token_limit,
    )

    decision_targets_text = (
        f"Effective output token allowance: {token_limit}.\n"
        f"Budget profile: {budget_profile}.\n"
        "Stay loyal to the evidence chunks.\n"
        "Favor higher-ranked classes more strongly when compression becomes necessary.\n"
        "If space becomes tight, omit lower-ranked classes before weakening the top class."
    )

    return {
        "active_classes": active_classes,
        "groups": working_groups,
        "budget_profile": budget_profile,
        "effective_output_token_limit": token_limit,
        "class_groups_text": class_groups_text,
        "decision_targets_text": decision_targets_text,
        "selected_real_ids_after_budget": selected_real_ids_after_budget,
    }


def finalize_a4_output(
    *,
    sp: SuperPrompt,
    condenser_result: JsonDict,
    grouped_chunk_package: JsonDict,
) -> SuperPrompt:
    """
    Write the final A4 output back into SuperPrompt.
    """
    if sp is None:
        raise ValueError("finalize_a4_output: 'sp' must not be None")

    s_ctx_md = str(condenser_result.get("s_ctx_md", "") or "").strip()
    if not s_ctx_md:
        raise RuntimeError("finalize_a4_output: final condenser returned empty s_ctx_md")

    if not hasattr(sp, "extras") or getattr(sp, "extras") is None:
        sp.extras = {}

    selected_real_ids_after_budget = list(
        grouped_chunk_package.get("selected_real_ids_after_budget", []) or []
    )

    stage_rows: List[Tuple[str, float, A3ChunkStatus]] = []
    selected_set = set(selected_real_ids_after_budget)

    ordered_real_ids = list(
        dict.fromkeys(
            selected_real_ids_after_budget
            + list(getattr(sp, "final_selection_ids", []) or [])
        ).keys()
    )

    score_base = float(len(ordered_real_ids))
    for idx, real_chunk_id in enumerate(ordered_real_ids, start=1):
        if real_chunk_id in selected_set:
            stage_rows.append((real_chunk_id, score_base - float(idx) + 1.0, A3ChunkStatus.SELECTED))
        else:
            stage_rows.append((real_chunk_id, 0.0, A3ChunkStatus.DISCARDED))

    sp.S_CTX_MD = s_ctx_md
    sp.final_selection_ids = selected_real_ids_after_budget
    sp.views_by_stage["a4"] = stage_rows
    sp.stage = "a4"
    sp.history_of_stages.append("a4")

    sp.extras["a4_budget_profile"] = grouped_chunk_package.get("budget_profile", "")
    sp.extras["a4_active_classes"] = grouped_chunk_package.get("active_classes", [])
    sp.extras["a4_groups"] = grouped_chunk_package.get("groups", [])
    sp.extras["a4_effective_output_token_limit"] = grouped_chunk_package.get(
        "effective_output_token_limit", 3000
    )

    try:
        sp.compose_prompt_ready()
    except Exception:
        pass

    return sp


# ----------------------------------------------------------------------
# private helpers
# ----------------------------------------------------------------------

def _build_user_prompt_under_evaluation(sp: SuperPrompt) -> str:
    body = getattr(sp, "body", {}) or {}

    blocks: List[str] = []

    purpose = str(body.get("purpose", "") or "").strip()
    task = str(body.get("task", "") or "").strip()
    context = str(body.get("context", "") or "").strip()

    if purpose:
        blocks.append(purpose)
    if task:
        blocks.append(task)
    if context:
        blocks.append(context)

    text = "\n\n".join(blocks).strip()
    if not text:
        raise RuntimeError("prepare_selected_chunks: prompt-under-evaluation text is empty")

    return text


def _build_evidence_chunks_text(selected_items: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    lines.append("<evidence_chunks>")

    for item in selected_items:
        local_chunk_id = str(item["local_chunk_id"])
        a3_rank = int(item["a3_rank"])
        source = str(item["source"] or "")
        snippet = str(item["snippet"] or "")

        lines.append(
            f'  <chunk rank="{a3_rank}" chunk_id="{local_chunk_id}" source="{source}">'
        )
        lines.append("    <chunk_text>")
        for raw_line in snippet.splitlines():
            lines.append(f"      {raw_line}")
        lines.append("    </chunk_text>")
        lines.append("  </chunk>")

    lines.append("</evidence_chunks>")
    return "\n".join(lines).strip()


def _build_active_class_definitions_text(active_classes: List[Dict[str, str]]) -> str:
    """
    Important:
    For the classifier prompt, keep the visible class view free of ID1/ID2...
    The model should mainly see the real class phrases + their meanings.
    """
    lines: List[str] = []
    lines.append("<active_class_definitions>")

    for priority_rank, item in enumerate(active_classes, start=1):
        lines.append(f'  <class priority_rank="{priority_rank}">')
        lines.append(f"    <class_phrase>{item['class_phrase']}</class_phrase>")
        lines.append(f"    <class_context_text>{item['class_context_text']}</class_context_text>")
        lines.append("  </class>")

    lines.append("</active_class_definitions>")
    return "\n".join(lines).strip()


def _build_class_groups_text(
    *,
    groups: List[Dict[str, Any]],
    budget_profile: str,
    token_limit: int,
) -> str:
    lines: List[str] = []
    lines.append("<class_groups>")
    lines.append(f"  <budget_profile>{budget_profile}</budget_profile>")
    lines.append(f"  <effective_output_token_limit>{token_limit}</effective_output_token_limit>")

    for group in groups:
        local_chunk_ids = [str(item["local_chunk_id"]) for item in group["items"]]
        local_chunk_ids_text = ", ".join(local_chunk_ids)

        lines.append(
            f'  <group priority_rank="{group["priority_rank"]}" class_phrase="{group["class_phrase"]}">'
        )
        lines.append(f"    <class_context_text>{group['class_context_text']}</class_context_text>")
        lines.append(f"    <local_chunk_ids>{local_chunk_ids_text}</local_chunk_ids>")
        lines.append("  </group>")

    lines.append("</class_groups>")
    return "\n".join(lines).strip()


def _build_fallback_chunk_package(
    *,
    selected_items: List[Dict[str, Any]],
    active_classes: List[Dict[str, str]],
    token_limit: int,
) -> JsonDict:
    """
    Fallback mode when classifier output is missing / unusable.

    Behavior agreed in chat:
    - continue instead of failing
    - no per-chunk grouping
    - send all chunks as they are to the final condenser
    - expose only the overall class phrases as collective lenses
    """
    budget_profile = "fallback_no_grouping"

    class_groups_text = _build_fallback_class_groups_text(
        active_classes=active_classes,
        selected_items=selected_items,
        token_limit=token_limit,
    )

    decision_targets_text = (
        f"Effective output token allowance: {token_limit}.\n"
        "Classifier grouping failed or was unusable.\n"
        "Do not assume per-chunk class assignment.\n"
        "Use the class phrases only as collective high-level lenses over the full evidence set.\n"
        "Condense the evidence chunks directly, in their current order, while staying loyal to the text."
    )

    selected_real_ids_after_budget = [str(item["real_chunk_id"]) for item in selected_items]

    return {
        "active_classes": active_classes,
        "groups": [],
        "budget_profile": budget_profile,
        "effective_output_token_limit": token_limit,
        "class_groups_text": class_groups_text,
        "decision_targets_text": decision_targets_text,
        "selected_real_ids_after_budget": selected_real_ids_after_budget,
    }


def _build_fallback_class_groups_text(
    *,
    active_classes: List[Dict[str, str]],
    selected_items: List[Dict[str, Any]],
    token_limit: int,
) -> str:
    lines: List[str] = []
    lines.append("<class_groups>")
    lines.append("  <mode>fallback_no_grouping</mode>")
    lines.append(f"  <effective_output_token_limit>{token_limit}</effective_output_token_limit>")
    lines.append("  <overall_class_overview>")

    for priority_rank, item in enumerate(active_classes, start=1):
        lines.append(f'    <class priority_rank="{priority_rank}">')
        lines.append(f"      <class_phrase>{item['class_phrase']}</class_phrase>")
        lines.append(f"      <class_context_text>{item['class_context_text']}</class_context_text>")
        lines.append("    </class>")

    lines.append("  </overall_class_overview>")
    local_chunk_ids_text = ", ".join(str(item["local_chunk_id"]) for item in selected_items)
    lines.append(f"  <all_selected_local_chunk_ids>{local_chunk_ids_text}</all_selected_local_chunk_ids>")
    lines.append("</class_groups>")
    return "\n".join(lines).strip()


def _resolve_classifier_class_value(
    *,
    raw_class_value: str,
    active_ids: List[str],
    phrase_to_id: Dict[str, str],
    normalized_phrase_to_id: Dict[str, str],
) -> str:
    """
    Resolve classifier output into the canonical internal class_id.
    Supports:
    - old style: ID1 / ID2 / ...
    - new style: actual class phrase
    """
    value = str(raw_class_value or "").strip()
    if not value:
        return ""

    if value in active_ids:
        return value

    if value in phrase_to_id:
        return phrase_to_id[value]

    normalized_value = _normalize_phrase_key(value)
    return normalized_phrase_to_id.get(normalized_value, "")


def _normalize_phrase_key(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _sanitize_chunk_text(text: str) -> str:
    """
    Keep chunk content readable while removing line-start structural collisions.
    """
    if not text:
        return ""

    result = str(text)

    result = re.sub(r"(?m)^###\s*", "[H3] ", result)
    result = re.sub(r"(?m)^##\s*", "[H2] ", result)
    result = re.sub(r"(?m)^#\s*", "[H1] ", result)
    result = re.sub(r"(?m)^```", "[CODE_FENCE]", result)
    result = re.sub(r"(?m)^---\s*$", "[RULE]", result)

    return result.strip()