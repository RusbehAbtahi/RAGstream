# -*- coding: utf-8 -*-
"""
compose_texts
=============

Why this helper exists:
- Composing SYSTEM and USER messages is text-heavy and easy to clutter the
  main AgentPrompt class.
- We want the core class to read like a high-level story, and all text
  formatting to live here.

What it does:
- Provides `build_system_text(...)` for the SYSTEM message.
- Provides `build_user_text_for_chooser(...)` for the USER message when
  agent_type == "chooser".
"""

from __future__ import annotations

from typing import Any, Dict, List


def build_system_text(
    system_text: str,
    purpose_text: str,
    agent_name: str,
    version: str,
) -> str:
    """
    Build the SYSTEM message content for the LLM.
    """
    lines: List[str] = []

    if system_text:
        lines.append(system_text.strip())

    if purpose_text:
        lines.append("")
        lines.append(f"Agent purpose: {purpose_text.strip()}")

    lines.append("")
    lines.append(f"Agent id: {agent_name} v{version}")
    lines.append(
        "You never answer the user's question directly. "
        "You ONLY choose configuration values as instructed."
    )
    lines.append(
        "You MUST respond with a single JSON object and nothing else "
        "(no prose, no comments)."
    )

    return "\n".join(lines)


def build_user_text_for_chooser(
    input_payload: Dict[str, Any],
    enums: Dict[str, List[str]],
    cardinality: Dict[str, str],
    option_descriptions: Dict[str, Dict[str, str]],
    option_labels: Dict[str, Dict[str, str]],
    result_keys: Dict[str, str],
    active_fields: List[str],
) -> str:
    """
    Build the USER message content for a chooser-type agent.

    Shows:
    - Current SuperPrompt state (task, purpose, context, ...).
    - For each active field: allowed option ids plus label/description for clarity, and expected JSON shape.
    """
    lines: List[str] = []

    # Show SuperPrompt state
    lines.append("Current SuperPrompt state:")
    for key, value in input_payload.items():
        lines.append(f"- {key}: {value!r}")
    lines.append("")

    # Explain the decision task
    lines.append(
        "Based on this, choose values for the following configuration fields. "
        "For each field, you MUST choose only from the allowed option ids."
    )
    lines.append("")

    # List fields and options
    for field_id in active_fields:
        allowed = enums.get(field_id, [])
        if not allowed:
            continue

        card = cardinality.get(field_id, "one")
        result_key = result_keys.get(field_id, field_id)

        lines.append(f"Field '{field_id}' (JSON key: '{result_key}'):")

        if card == "many":
            lines.append(
                "  - Type: array of one or more option ids (strings) from the list below."
            )
        else:
            lines.append("  - Type: single option id (string) from the list below.")

        labels = option_labels.get(field_id, {})
        descs = option_descriptions.get(field_id, {})
        for opt_id in allowed:
            label = labels.get(opt_id)
            desc = descs.get(opt_id)
            if label and desc:
                lines.append(f"    * {opt_id}: {label} — {desc}")
            elif label:
                lines.append(f"    * {opt_id}: {label}")
            elif desc:
                lines.append(f"    * {opt_id}: {desc}")
            else:
                lines.append(f"    * {opt_id}")

        lines.append("")

    # Describe expected JSON keys and shapes
    lines.append("Return ONLY a JSON object with keys:")
    for field_id in active_fields:
        result_key = result_keys.get(field_id, field_id)
        card = cardinality.get(field_id, "one")
        if card == "many":
            lines.append(f"- '{result_key}': array of option ids (strings).")
        else:
            lines.append(f"- '{result_key}': single option id (string).")

    lines.append("")
    lines.append("Do NOT add explanations, comments or extra keys. JSON only.")

    return "\n".join(lines)
