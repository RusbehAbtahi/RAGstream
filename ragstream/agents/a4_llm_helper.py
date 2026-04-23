# -*- coding: utf-8 -*-
"""
a4_llm_helper.py

Shared LLM-call helper for A4.

Responsibilities:
- receive already-created AgentPrompt objects,
- build the input payloads for the 3 A4 calls,
- compose prompts,
- log the exact prompts/messages to CLI,
- call LLMClient,
- log cache-token usage after each call,
- parse the result back into Python.
"""

from __future__ import annotations

from typing import Any, Dict

import json

from ragstream.orchestration.agent_prompt import AgentPrompt
from ragstream.orchestration.llm_client import LLMClient
from ragstream.utils.logging import SimpleLogger


JsonDict = Dict[str, Any]


class A4LLMHelper:
    """
    Shared LLM-call helper for the 3 A4 calls.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def run_chunk_phraser(
        self,
        agent_prompt: AgentPrompt,
        *,
        user_prompt_under_evaluation: str,
        evidence_chunks: str,
    ) -> JsonDict:
        inputs: Dict[str, Any] = {
            "user_prompt_under_evaluation": user_prompt_under_evaluation,
            "evidence_chunks": evidence_chunks,
            "decision_targets": (
                "Use only contiguous class ids starting from ID1.\n"
                "Return 1 to 4 active classes only.\n"
                "Each class must contain class_id, class_phrase, class_context_text."
            ),
            "required_output": (
                '{\n'
                '  "class_definitions": [\n'
                '    {\n'
                '      "class_id": "ID1",\n'
                '      "class_phrase": "...",\n'
                '      "class_context_text": "..."\n'
                '    }\n'
                '  ]\n'
                '}'
            ),
        }

        return self._run_agent_call(
            call_name="A4 Chunk Phraser",
            agent_prompt=agent_prompt,
            input_payload=inputs,
        )

    def run_chunk_classifier(
        self,
        agent_prompt: AgentPrompt,
        *,
        user_prompt_under_evaluation: str,
        evidence_chunks: str,
        active_class_definitions: str,
    ) -> JsonDict:
        inputs: Dict[str, Any] = {
            "user_prompt_under_evaluation": user_prompt_under_evaluation,
            "active_class_definitions": active_class_definitions,
            "evidence_chunks": evidence_chunks,
            "required_output": (
                '{\n'
                '  "item_decisions": [\n'
                '    {\n'
                '      "chunk_id": "1",\n'
                '      "class_id": "ID1"\n'
                '    }\n'
                '  ]\n'
                '}'
            ),
        }

        return self._run_agent_call(
            call_name="A4 Chunk Classifier",
            agent_prompt=agent_prompt,
            input_payload=inputs,
        )

    def run_final_condenser(
        self,
        agent_prompt: AgentPrompt,
        *,
        user_prompt_under_evaluation: str,
        evidence_chunks: str,
        class_groups: str,
        effective_output_token_limit: int,
        decision_targets_text: str,
    ) -> JsonDict:
        inputs: Dict[str, Any] = {
            "user_prompt_under_evaluation": user_prompt_under_evaluation,
            "class_groups": class_groups,
            "evidence_chunks": evidence_chunks,
            "decision_targets": decision_targets_text,
            "required_output": (
                '{\n'
                '  "s_ctx_md": "one coherent condensed context text"\n'
                '}\n'
                f"\nKeep s_ctx_md at or below about {int(effective_output_token_limit)} tokens."
            ),
        }

        return self._run_agent_call(
            call_name="A4 Final Condenser",
            agent_prompt=agent_prompt,
            input_payload=inputs,
        )

    def _run_agent_call(
        self,
        *,
        call_name: str,
        agent_prompt: AgentPrompt,
        input_payload: Dict[str, Any],
    ) -> JsonDict:
        """
        Shared LLM path for all 3 A4 calls.
        """
        messages, response_format = agent_prompt.compose(input_payload=input_payload)

        SimpleLogger.info(f"{call_name} → LLM messages:")
        try:
            SimpleLogger.info(json.dumps(messages, ensure_ascii=False, indent=2))
        except Exception:
            SimpleLogger.info(repr(messages))

        response = self._llm_client.chat(
            messages=messages,
            model_name=agent_prompt.model_name,
            temperature=agent_prompt.temperature,
            max_output_tokens=agent_prompt.max_output_tokens,
            response_format=response_format,
            return_metadata=True,
        )

        raw_content = str(response.get("content", "") or "")
        usage = response.get("usage", {}) or {}

        SimpleLogger.info(f"{call_name} ← LLM raw result:")
        try:
            SimpleLogger.info(raw_content)
        except Exception:
            SimpleLogger.info(repr(raw_content))

        cached_tokens = int(usage.get("cached_tokens", 0) or 0)
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        uncached_tokens = max(0, prompt_tokens - cached_tokens)

        SimpleLogger.info(
            f"{call_name} | token usage | prompt={prompt_tokens} | "
            f"cached={cached_tokens} | uncached={uncached_tokens} | "
            f"completion={completion_tokens}"
        )

        parsed = agent_prompt.parse(raw_content)

        SimpleLogger.info(f"{call_name} ← parsed result:")
        try:
            SimpleLogger.info(json.dumps(parsed, ensure_ascii=False, indent=2))
        except Exception:
            SimpleLogger.info(repr(parsed))

        return parsed