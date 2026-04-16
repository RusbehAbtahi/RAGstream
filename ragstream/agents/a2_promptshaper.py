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
            "decision_targets": self._build_decision_targets_text(agent, active_fields),
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

    def _build_decision_targets_text(self, agent: Any, active_fields: List[str]) -> str:
        """
        Build the selector-specific decision-target block here in A2,
        not in the neutral compose helper.
        """
        lines: List[str] = []
        active_set = set(active_fields)
        result_key_map = self._build_result_key_map(agent)

        option_labels: Dict[str, Dict[str, str]] = getattr(agent, "option_labels", {}) or {}
        option_descriptions: Dict[str, Dict[str, str]] = getattr(agent, "option_descriptions", {}) or {}
        enums: Dict[str, List[str]] = getattr(agent, "enums", {}) or {}

        for target in getattr(agent, "decision_targets", []) or []:
            field_id = target.get("id")
            if not field_id or field_id not in active_set:
                continue

            label = target.get("label", field_id)
            result_key = result_key_map.get(field_id, field_id)

            min_selected = int(target.get("min_selected", 1))
            max_selected = int(target.get("max_selected", 1))

            lines.append(f"Field '{label}' (JSON key: '{result_key}')")

            if max_selected > 1:
                lines.append(f"- Select between {min_selected} and {max_selected} option ids.")
            else:
                lines.append("- Select exactly one option id.")

            for opt_id in enums.get(field_id, []):
                opt_label = (option_labels.get(field_id, {}).get(opt_id) or "").strip()
                opt_desc = (option_descriptions.get(field_id, {}).get(opt_id) or "").strip()

                if opt_label and opt_desc:
                    lines.append(f"  * {opt_id}: {opt_label} — {opt_desc}")
                elif opt_label:
                    lines.append(f"  * {opt_id}: {opt_label}")
                elif opt_desc:
                    lines.append(f"  * {opt_id}: {opt_desc}")
                else:
                    lines.append(f"  * {opt_id}")

            lines.append("")

        return "\n".join(lines).strip()

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