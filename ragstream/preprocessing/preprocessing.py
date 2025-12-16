# -*- coding: utf-8 -*-
"""
preprocessing.py — Implements exactly Steps 0–6 as ordered.

Goal:
- User prompt in; update SuperPrompt 'sp' in place; write composed text to sp.prompt_ready.

Rules:
- Deterministic only. No heuristics, no fuzzy, no LLM.
- Accept '# ', '## ', '### ' headers; last-wins if repeated.
- No writes to sp.extras. No new SuperPrompt fields. No guards beyond what is stated.

Steps implemented below with clear markers:
  Step 0: (schema is already loaded outside; we just receive it)
  Step 1: Parse headers or treat as plain text
  Step 2: Compare to standard names
  Step 3: Deterministic map via NameMatcher
  Step 4: MUST handling + TASK/CONTEXT rule
  Step 5: (deferred; do nothing)
  Step 6: Update sp.prompt_ready and stage/history
"""

from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
import re

from .prompt_schema import PromptSchema
from .name_matcher import NameMatcher


# ------- helper: deterministic markdown section parser for '# ', '## ', '### ' (last-wins)
def _parse_markdown_sections(user_text: str) -> List[Tuple[str, str]]:
    """
    Return list of (header_text, body_text).
    Header must be '# ', '## ', or '### ' (space required).
    Last-wins behavior is enforced later by overwrite.
    """
    text = user_text or ""
    matches = list(re.finditer(r"^(#{1,3})\s*(.+)$", text, flags=re.MULTILINE))
    if not matches:
        return []

    sections: List[Tuple[str, str]] = []
    for i, m in enumerate(matches):
        header_title = (m.group(2) or "").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = (text[start:end] or "").strip()
        sections.append((header_title, body))
    return sections


def preprocess(user_text: str, sp: Any, schema: PromptSchema) -> None:
    """
    Update 'sp' in place, exactly as ordered.

    Inputs:
      - user_text: raw text from GUI left box
      - sp: SuperPrompt instance (not constructed here)
      - schema: PromptSchema loaded in controller

    Outputs:
      - sp.body[...] updated for keys present in our limited set
      - sp.prompt_ready set to composed Markdown
      - sp.history_of_stages += ["preprocessed"]
      - sp.stage = "preprocessed"
    """

    # ---------------- Step 1: parse headers (or treat as plain text) ----------------
    sections = _parse_markdown_sections(user_text)

    # If no headers exist: whole text → TASK (plain mode)
    if not sections:
        task_text = (user_text or "").strip()
        # write to body
        sp.body["task"] = task_text
        # clear context explicitly not required by spec; we leave as-is
        # ---------------- Step 6: compose prompt_ready and mark stage ----------------
        sp.prompt_ready = _compose_prompt_ready({
            "system": sp.body.get("system"),
            "audience": sp.body.get("audience"),
            "purpose": sp.body.get("purpose"),
            "tone": sp.body.get("tone"),
            "confidence": sp.body.get("confidence"),
            "depth": sp.body.get("depth"),
            "task": sp.body.get("task"),
            "context": sp.body.get("context"),
            "format": sp.body.get("format"),
        })
        sp.history_of_stages.append("preprocessed")
        sp.stage = "preprocessed"
        return

    # ---------------- Step 2: check vs standard names (list is collected) ----------
    raw_headers = [h for (h, _b) in sections]

    # ---------------- Step 3: deterministic mapping via NameMatcher ----------------
    nm = NameMatcher(schema)

    breakpoint()
    # Build a map canonical -> text (last-wins via overwrite)
    mapped: Dict[str, str] = {}
    unknown_headers: List[str] = []
    for raw, body in sections:
        canonical_key, _method = nm.resolve(raw)  # unpack tuple
        if canonical_key is None:
            unknown_headers.append(raw)
            continue
        mapped[canonical_key] = body  # last definition wins


    # ---------------- Step 4: MUST handling + TASK/CONTEXT rule --------------------
    # TASK special rule:
    # - If TASK missing but CONTEXT exists => TASK := CONTEXT; CONTEXT := empty
    # - If TASK missing and CONTEXT missing => TASK := whole prompt (plain)
    if ("task" not in mapped) or (not (mapped.get("task") or "").strip()):
        context_text = (mapped.get("context") or "").strip()
        if context_text:
            mapped["task"] = context_text
            # leave CONTEXT empty (so it won't appear later)
            mapped["context"] = ""
        else:
            mapped["task"] = (user_text or "").strip()

    # For other MUST attributes (except TASK), fill defaults
    for must_key in schema.must:
        if must_key == "task":
            continue
        if (must_key not in mapped) or (not (mapped.get(must_key) or "").strip()):
            mapped[must_key] = schema.default_for(must_key)

    # ---------------- Step 5: deferred (do nothing now) ----------------------------

    # Write recognized fields into sp.body (limited to existing keys only)
    # We do not add new fields; we only touch the known ones present in sp.body.
    for k in ["system", "task", "audience", "role", "tone", "depth", "context", "purpose", "format", "text"]:
        if k in mapped:
            sp.body[k] = mapped.get(k)

    # If we consumed CONTEXT into TASK earlier and set empty string, ensure it stays empty in body
    # (No extra guards; just reflect mapped content)
    if "context" in mapped and (mapped.get("context") == ""):
        sp.body["context"] = None  # empty → not shown

    # ---------------- Step 6: compose prompt_ready and mark stage -------------------
    sp.prompt_ready = _compose_prompt_ready({
        "system": sp.body.get("system"),
        "audience": sp.body.get("audience"),
        "purpose": sp.body.get("purpose"),
        "tone": sp.body.get("tone"),
        "confidence": sp.body.get("confidence"),
        "depth": sp.body.get("depth"),
        "task": sp.body.get("task"),
        "context": sp.body.get("context"),
        "format": sp.body.get("format"),
    })

    sp.history_of_stages.append("preprocessed")
    sp.stage = "preprocessed"


# ------- helper: compose the right-box Super-Prompt exactly from present values
def _compose_prompt_ready(parts: Dict[str, Optional[str]]) -> str:
    """
    Build the markdown shown in the GUI Super-Prompt box.
    Only include keys with non-empty text. Order is fixed and simple.
    No System_MD/Prompt_MD here — a single composed view only.
    """
    order = [
        "system",
        "audience",
        "purpose",
        "tone",
        "confidence",
        "depth",
        "task",
        "context",
        "format",
    ]
    lines: List[str] = []
    for key in order:
        val = parts.get(key)
        if val is None:
            continue
        txt = str(val).strip()
        if not txt:
            continue
        lines.append(f"## {key.upper()}")
        lines.append(txt)
        lines.append("")  # blank line between blocks
    return "\n".join(lines).strip()
