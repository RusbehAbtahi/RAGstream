# -*- coding: utf-8 -*-
"""
config_loader
=============

Why this helper exists:
- Agent JSON configs contain a 'fields' list with enums, defaults and cardinality.
- Converting this list into clean Python dictionaries is generic logic and should
  not clutter AgentPrompt.

What it does:
- Provides a single function `extract_field_config(fields_cfg)` that returns:
  - enums[field_id] = list of allowed option ids.
  - defaults[field_id] = default value from config (may be str or list).
  - cardinality[field_id] = "one" or "many".
  - option_descriptions[field_id][opt_id] = human-readable description (optional).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def extract_field_config(
    fields_cfg: List[Dict[str, Any]]
) -> Tuple[Dict[str, List[str]], Dict[str, Any], Dict[str, str], Dict[str, Dict[str, str]]]:
    """
    Convert the JSON 'fields' list into enums/defaults/cardinality/option_descriptions.

    - enums[field_id] = ["opt1", "opt2", ...]
    - defaults[field_id] = default value from config (may be str or list)
    - cardinality[field_id] = "one" | "many"
    - option_descriptions[field_id][opt_id] = description (if present)
    """
    enums: Dict[str, List[str]] = {}
    defaults: Dict[str, Any] = {}
    cardinality: Dict[str, str] = {}
    option_descriptions: Dict[str, Dict[str, str]] = {}

    for field in fields_cfg:
        field_id = field.get("id")
        if not field_id:
            continue

        field_type = field.get("type", "enum")
        if field_type != "enum":
            # For v1, AgentPrompt only supports enum-based Chooser behaviour.
            # Writer / Extractor / Scorer can be handled later.
            continue

        options = field.get("options", []) or []
        allowed_ids: List[str] = []
        descs: Dict[str, str] = {}

        for opt in options:
            opt_id = opt.get("id")
            if not opt_id:
                continue
            allowed_ids.append(opt_id)
            if "description" in opt:
                descs[opt_id] = opt["description"]

        if allowed_ids:
            enums[field_id] = allowed_ids
            if descs:
                option_descriptions[field_id] = descs

        defaults[field_id] = field.get("default")
        cardinality[field_id] = field.get("cardinality", "one")

    return enums, defaults, cardinality, option_descriptions
