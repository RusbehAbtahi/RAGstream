# ragstream/agents/a2_promptshaper.py
# -*- coding: utf-8 -*-
"""
A2 PromptShaper agent.

Job:
- Read TASK, CONTEXT, PURPOSE from an existing SuperPrompt (after preprocessing).
- Ask AgentFactory for the A2 AgentPrompt configuration.
- Build any A2-specific runtime prompt blocks here (not in the neutral stack).
- Use AgentPrompt.compose(...) to build SYSTEM + USER messages.
- Call LLMClient with those messages, using ONLY model settings coming from JSON
  (via AgentPrompt: model_name, temperature, max_output_tokens).
- Expect a JSON object with SYSTEM / AUDIENCE / TONE / DEPTH / CONFIDENCE.
- Update the same SuperPrompt in place.
- Rebuild sp.prompt_ready and mark stage='a2'.
"""

from __future__ import annotations

from typing import Any, Dict, List, Union
import json

from ragstream.orchestration.super_prompt import SuperPrompt
from ragstream.orchestration.agent_factory import AgentFactory
from ragstream.orchestration.llm_client import LLMClient
from ragstream.utils.logging import SimpleLogger


JsonDict = Dict[str, Any]


class A2PromptShaper:
    """
    Orchestrates A2 for a single SuperPrompt.

    This class stays thin:
    - It does NOT know JSON file layout (AgentFactory does that).
    - It does NOT know prompt templates (AgentPrompt does that).
    - It only:
        * extracts input from SuperPrompt,
        * builds A2-specific runtime blocks,
        * asks AgentPrompt to compose messages,
        * calls LLMClient,
        * writes the result back into SuperPrompt.
    """

    def __init__(self, agent_factory: AgentFactory, llm_client: LLMClient) -> None:
        self._factory = agent_factory
        self._llm_client = llm_client

    def run(
        self,
        sp: SuperPrompt,
        *,
        agent_id: str = "a2_promptshaper",
        version: str = "003",
    ) -> SuperPrompt:
        """
        Main entry point for A2.
        """
        agent = self._factory.get_agent(agent_id=agent_id, version=version)

        # For now, all 5 fields are active. Later we can respect user-locked ones.
        active_fields: List[str] = ["system", "audience", "tone", "depth", "confidence"]

        inputs: Dict[str, str] = {
            "prompt_under_evaluation": self._build_prompt_under_evaluation(sp),
            # Changed:
            # decision_targets now come from the top-level JSON config and are
            # rendered inside AgentPrompt / compose_texts, not from A2 runtime payload.
            "required_output": self._build_required_output_text(agent, active_fields),
        }

        messages, response_format = agent.compose(
            input_payload=inputs,
            active_fields=active_fields,
        )

        SimpleLogger.info("A2PromptShaper → LLM messages:")
        try:
            SimpleLogger.info(json.dumps(messages, ensure_ascii=False, indent=2))
        except Exception:
            SimpleLogger.info(repr(messages))

        if not getattr(agent, "model_name", None):
            raise RuntimeError(
                "A2PromptShaper: AgentPrompt has no model_name configured (JSON missing?)"
            )
        if not hasattr(agent, "temperature") or not hasattr(agent, "max_output_tokens"):
            raise RuntimeError(
                "A2PromptShaper: AgentPrompt missing temperature/max_output_tokens configuration"
            )

        raw_result: Union[str, JsonDict] = self._llm_client.chat(
            messages=messages,
            model_name=agent.model_name,
            temperature=agent.temperature,
            max_output_tokens=agent.max_output_tokens,
            response_format=response_format,
            prompt_cache_key=f"{agent_id}_{version}",  # Added: stable cache key for repeated A2 prompts of the same agent/version.
           # prompt_cache_retention="in_memory",  # Added: explicit short-lived cache retention for repeated near-term A2 calls.
        )

        SimpleLogger.info("A2PromptShaper ← LLM raw result:")
        try:
            if isinstance(raw_result, dict):
                SimpleLogger.info(json.dumps(raw_result, ensure_ascii=False, indent=2))
            else:
                SimpleLogger.info(str(raw_result))
        except Exception:
            SimpleLogger.info(repr(raw_result))

        parsed_result = agent.parse(raw_result, active_fields=active_fields)

        # Deterministic A2 safety layer:
        # - remove every selected id that does not belong to the corresponding field catalog
        # - if a field becomes empty after removal, do NOT use catalog defaults here
        # - preserve the existing preprocessing value by simply not overwriting that field
        parsed_result = self._sanitize_selector_result(
            agent=agent,
            parsed_result=parsed_result,
            active_fields=active_fields,
        )

        selected_ids: Dict[str, Any] = {}
        labels_map: Dict[str, Dict[str, str]] = getattr(agent, "option_labels", {}) or {}

        def _to_label(field_id: str, opt_id: str) -> str:
            opt_id = (opt_id or "").strip()
            if not opt_id:
                return ""
            return (labels_map.get(field_id, {}).get(opt_id) or opt_id).strip()

        for key in active_fields:
            value = parsed_result.get(key)
            if value is None:
                continue

            selected_ids[key] = value

            if isinstance(value, list):
                label_items = [_to_label(key, str(v)) for v in value]
                label_items = [x for x in label_items if x]
                text = ", ".join(label_items)
            else:
                text = _to_label(key, str(value))

            if text:
                sp.body[key] = text

        sp.extras["a2_selected_ids"] = selected_ids

        sp.history_of_stages.append("a2")
        sp.stage = "a2"
        sp.compose_prompt_ready()

        return sp

    def _sanitize_selector_result(
        self,
        *,
        agent: Any,
        parsed_result: JsonDict,
        active_fields: List[str],
    ) -> JsonDict:
        """
        Deterministically sanitize A2 selector output.

        Rules:
        - Each field may only use ids from its own enum/catalog.
        - Invalid ids are removed.
        - Cross-field ids are removed.
        - Duplicate ids are removed while preserving order.
        - max_selected is enforced.
        - If a field becomes empty, the field is omitted from the sanitized result.
          This preserves the existing preprocessing value in sp.body.
        - Catalog defaults are intentionally NOT applied here.
        """
        sanitized: JsonDict = {}

        enums: Dict[str, List[str]] = getattr(agent, "enums", {}) or {}

        target_by_id: Dict[str, Dict[str, Any]] = {}
        for target in getattr(agent, "decision_targets", []) or []:
            field_id = str(target.get("id", "") or "").strip()
            if field_id:
                target_by_id[field_id] = target

        for field_id in active_fields:
            if field_id not in parsed_result:
                continue

            target = target_by_id.get(field_id, {}) or {}
            max_selected = int(target.get("max_selected", 1) or 1)

            allowed_values = enums.get(field_id, []) or []
            allowed_ids = [str(item).strip() for item in allowed_values if str(item).strip()]
            allowed_set = set(allowed_ids)

            if not allowed_set:
                SimpleLogger.warning(
                    f"A2PromptShaper: no enum/catalog values available for field '{field_id}'; "
                    "preserving preprocessing value."
                )
                continue

            raw_value = parsed_result.get(field_id)
            raw_items = self._normalize_selector_items(raw_value)

            valid_items: List[str] = []
            removed_items: List[str] = []

            for item in raw_items:
                if item in allowed_set:
                    if item not in valid_items:
                        valid_items.append(item)
                else:
                    removed_items.append(item)

            if removed_items:
                SimpleLogger.warning(
                    f"A2PromptShaper: removed invalid option(s) for field '{field_id}': "
                    f"{removed_items}"
                )

            if not valid_items:
                SimpleLogger.warning(
                    f"A2PromptShaper: field '{field_id}' became empty after sanitization; "
                    "preserving preprocessing value."
                )
                continue

            if len(valid_items) > max_selected:
                SimpleLogger.warning(
                    f"A2PromptShaper: field '{field_id}' returned too many valid options; "
                    f"keeping first {max_selected}: {valid_items[:max_selected]}"
                )
                valid_items = valid_items[:max_selected]

            if max_selected > 1:
                sanitized[field_id] = valid_items
            else:
                sanitized[field_id] = valid_items[0]

        return sanitized

    @staticmethod
    def _normalize_selector_items(value: Any) -> List[str]:
        """
        Normalize one selector output value into a clean list of string ids.
        """
        if value is None:
            return []

        if isinstance(value, list):
            result: List[str] = []
            for item in value:
                text = str(item or "").strip()
                if text:
                    result.append(text)
            return result

        text = str(value or "").strip()
        if not text:
            return []

        return [text]

    def _build_prompt_under_evaluation(self, sp: SuperPrompt) -> str:
        """
        Build one passive text block for the prompt under evaluation.
        """
        parts: List[str] = []

        purpose = (sp.body.get("purpose") or "").strip()
        task = (sp.body.get("task") or "").strip()
        context = (sp.body.get("context") or "").strip()

        if purpose:
            parts.append(purpose)
        if task:
            parts.append(task)
        if context:
            parts.append(context)

        return "\n\n".join(parts).strip()

    @staticmethod
    def _build_result_key_map(agent: Any) -> Dict[str, str]:
        """
        Build selector field_id -> result_key map from output_schema.
        """
        result: Dict[str, str] = {}
        output_schema = getattr(agent, "output_schema", {}) or {}
        for field in output_schema.get("fields", []) or []:
            field_id = field.get("field_id")
            if not field_id:
                continue
            result[field_id] = field.get("result_key", field_id)
        return result

    def _build_required_output_text(self, agent: Any, active_fields: List[str]) -> str:
        """
        Build the exact selector JSON shape expected from the LLM.
        """
        lines: List[str] = []
        active_set = set(active_fields)
        result_key_map = self._build_result_key_map(agent)

        lines.append("Return exactly one JSON object in this shape:")
        lines.append("")
        lines.append("{")

        visible_targets: List[Dict[str, Any]] = []
        for target in getattr(agent, "decision_targets", []) or []:
            field_id = target.get("id")
            if field_id and field_id in active_set:
                visible_targets.append(target)

        for idx, target in enumerate(visible_targets):
            field_id = target.get("id")
            result_key = result_key_map.get(field_id, field_id)
            max_selected = int(target.get("max_selected", 1))
            suffix = "," if idx < len(visible_targets) - 1 else ""

            if max_selected > 1:
                lines.append(f'  "{result_key}": ["option_id_1", "option_id_2"]{suffix}')
            else:
                lines.append(f'  "{result_key}": "option_id"{suffix}')

        lines.append("}")

        return "\n".join(lines).strip()