# -*- coding: utf-8 -*-
"""
compose_texts
=============

Neutral text render helpers for AgentPrompt.

Rule:
- No agent-specific visible wording is invented here.
- Visible prompt wording must come from JSON or from agent-prepared runtime text.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List


def _stringify_for_prompt(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)

    return str(value)


def build_system_text(
    static_prompt: Dict[str, Any],
    agent_name: str,
    version: str,
) -> str:
    """
    Build the SYSTEM message content for the LLM.

    Neutral rule:
    - static_prompt is treated as dump-only content.
    - No agent-specific wording is invented here.
    - If key == 'preamble', render the text without a heading.
    - Otherwise use the JSON key itself as the heading label.
    """
    lines: List[str] = []

    for key, value in static_prompt.items():
        text = _stringify_for_prompt(value)
        if not text:
            continue

        if str(key).strip().lower() == "preamble":
            lines.append(text)
            lines.append("")
        else:
            lines.append(f"## {key}")
            lines.append(text)
            lines.append("")

    return "\n".join(lines).strip()


def _build_user_text_from_dynamic_bindings(
    input_payload: Dict[str, Any],
    dynamic_bindings: List[Dict[str, Any]],
) -> str:
    """
    Generic neutral renderer for USER content from dynamic bindings.

    Rule:
    - prompt_text is rendered exactly as provided by JSON.
    - payload values are rendered exactly as provided by the agent.
    - no extra visible wording is added here.
    """
    lines: List[str] = []

    for binding in dynamic_bindings:
        if not binding.get("visible_in_prompt", True):
            continue

        binding_id = binding.get("id")
        if not binding_id:
            continue

        prompt_text = (binding.get("prompt_text") or "").strip()
        value = input_payload.get(binding_id, "")

        if prompt_text:
            lines.append(prompt_text)

        rendered = _stringify_for_prompt(value)
        if rendered:
            lines.append(rendered)

        lines.append("")

    return "\n".join(lines).strip()


def build_user_text_for_selector(
    input_payload: Dict[str, Any],
    dynamic_bindings: List[Dict[str, Any]],
    decision_targets: List[Dict[str, Any]],
    result_keys: Dict[str, str],
    active_fields: List[str],
) -> str:
    """
    Neutral USER renderer for selector agents.

    All visible wording must already exist in JSON or in agent-prepared runtime text.
    """
    return _build_user_text_from_dynamic_bindings(
        input_payload=input_payload,
        dynamic_bindings=dynamic_bindings,
    )


def build_user_text_for_classifier(
    input_payload: Dict[str, Any],
    dynamic_bindings: List[Dict[str, Any]],
    decision_targets: List[Dict[str, Any]],
    output_schema: Dict[str, Any],
    top_level_result_keys: Dict[str, str],
    item_result_keys: Dict[str, str],
) -> str:
    """
    Neutral USER renderer for classifier agents.

    All visible wording must already exist in JSON or in agent-prepared runtime text.
    """
    return _build_user_text_from_dynamic_bindings(
        input_payload=input_payload,
        dynamic_bindings=dynamic_bindings,
    )