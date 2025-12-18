# -*- coding: utf-8 -*-
"""
A2 PromptShaper agent.

Job:
- Read TASK, CONTEXT, PURPOSE from an existing SuperPrompt (after preprocessing).
- Ask AgentFactory for the A2 AgentPrompt configuration.
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
from ragstream.preprocessing.preprocessing import _compose_prompt_ready
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
        version: str = "002",
    ) -> SuperPrompt:
        """
        Main entry point for A2.

        Input:
          - sp: SuperPrompt that already passed through PreProcessing.

        Effect:
          - Reads TASK / CONTEXT / PURPOSE from sp.body.
          - Calls the configured A2 AgentPrompt (mode='chooser').
          - Calls LLM via LLMClient.
          - Updates SYSTEM / AUDIENCE / TONE / DEPTH / CONFIDENCE in sp.body.
          - Rebuilds sp.prompt_ready.
          - Appends 'a2' to sp.history_of_stages and sets sp.stage='a2'.

        Returns:
          - The same SuperPrompt instance (mutated in place).
        """

        # 1) Extract the parts that A2 cares about as input for the chooser.
        inputs: Dict[str, str] = {
            "task": (sp.body.get("task") or "").strip(),
            "context": (sp.body.get("context") or "").strip(),
            "purpose": (sp.body.get("purpose") or "").strip(),
        }

        # 2) Get the AgentPrompt for A2 from the factory.
        agent = self._factory.get_agent(agent_id=agent_id, version=version)

        # For now, all 5 fields are active. Later we can respect user-locked ones.
        active_fields: List[str] = ["system", "audience", "tone", "depth", "confidence"]

        # 3) Ask AgentPrompt to build the SYSTEM + USER messages and response_format.
        messages, response_format = agent.compose(
            input_payload=inputs,
            active_fields=active_fields,
        )

        # ---- Only debugging/inspection that remains: ----
        # Final payload to LLM
        SimpleLogger.info("A2PromptShaper → LLM messages:")
        try:
            SimpleLogger.info(json.dumps(messages, ensure_ascii=False, indent=2))
        except Exception:
            # Fallback, in case messages contain non-JSON-serializable types
            SimpleLogger.info(repr(messages))

        # 4) Call LLM through LLMClient — using ONLY config that came from JSON via AgentPrompt.
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

        # Log raw result once
        SimpleLogger.info("A2PromptShaper ← LLM raw result:")
        try:
            if isinstance(raw_result, dict):
                SimpleLogger.info(json.dumps(raw_result, ensure_ascii=False, indent=2))
            else:
                SimpleLogger.info(str(raw_result))
        except Exception:
            SimpleLogger.info(repr(raw_result))

        # 5) Normalize result into a dict.
        if isinstance(raw_result, dict):
            result_dict: JsonDict = raw_result
        elif isinstance(raw_result, str):
            # Try to parse JSON string
            try:
                result_dict = json.loads(raw_result)
            except Exception as exc:
                raise RuntimeError(f"A2PromptShaper: LLM did not return valid JSON: {exc}") from exc
        else:
            raise RuntimeError(
                f"A2PromptShaper: Unexpected result type from LLMClient: {type(raw_result)!r}"
            )

        # 6) Update SuperPrompt body with the chosen values.
        #    The LLM output is constrained to option ids. For a readable final prompt,
        #    translate ids -> labels (label only) using agent.option_labels.
        #
        #    We still keep the raw ids in sp.extras['a2_selected_ids'] for stability/debugging.
        selected_ids: Dict[str, Any] = {}
        labels_map: Dict[str, Dict[str, str]] = getattr(agent, "option_labels", {}) or {}

        def _to_label(field_id: str, opt_id: str) -> str:
            opt_id = (opt_id or "").strip()
            if not opt_id:
                return ""
            return (labels_map.get(field_id, {}).get(opt_id) or opt_id).strip()

        for key in active_fields:
            value = result_dict.get(key)
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

        # 7) Rebuild super-prompt markdown (right box) from the updated body.
        sp.prompt_ready = _compose_prompt_ready(
            {
                "system": sp.body.get("system"),
                "audience": sp.body.get("audience"),
                "purpose": sp.body.get("purpose"),
                "tone": sp.body.get("tone"),
                "confidence": sp.body.get("confidence"),
                "depth": sp.body.get("depth"),
                "task": sp.body.get("task"),
                "context": sp.body.get("context"),
                "format": sp.body.get("format"),
            }
        )

        # 8) Stage bookkeeping
        sp.history_of_stages.append("a2")
        sp.stage = "a2"

        return sp
