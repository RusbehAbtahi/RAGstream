# -*- coding: utf-8 -*-
"""
AgentPrompt
===========
Main neutral prompt engine used by all LLM-using agents.

This file only:
- Defines AgentPrompt (the main class).
- Defines AgentPromptValidationError (small helper exception).
- Delegates JSON parsing, field config extraction, normalization and text
  composition to helper modules in agent_prompt_helpers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Set

from ragstream.utils.logging import SimpleLogger
from ragstream.orchestration.agent_prompt_helpers.config_loader import (
    extract_field_config,
)
from ragstream.orchestration.agent_prompt_helpers.schema_map import (
    build_result_key_map,
)
from ragstream.orchestration.agent_prompt_helpers.json_parser import (
    extract_json_object,
)
from ragstream.orchestration.agent_prompt_helpers.field_normalizer import (
    normalize_one,
    normalize_many,
)
from ragstream.orchestration.agent_prompt_helpers.compose_texts import (
    build_system_text,
    build_user_text_for_chooser,
)


class AgentPromptValidationError(Exception):
    """Raised when the LLM output cannot be parsed or validated."""


class AgentPrompt:
    """
    Neutral prompt engine.

    Configuration is passed in once (from JSON via AgentFactory) and is read-only.
    No per-call state is stored inside the instance; all inputs for a run are passed
    to compose()/parse() as parameters.
    """

    def __init__(
        self,
        agent_name: str,
        version: str,
        mode: str,
        system_text: str,
        purpose_text: str,
        output_schema: Dict[str, Any],
        enums: Dict[str, List[str]],
        defaults: Dict[str, Any],
        cardinality: Dict[str, str],
        option_descriptions: Dict[str, Dict[str, str]],
        model_name: str,
        temperature: float,
        max_output_tokens: int,
    ) -> None:
        self.agent_name: str = agent_name
        self.version: str = version
        self.mode: str = mode  # "chooser" | "writer" | "extractor" | "scorer"
        self.system_text: str = system_text
        self.purpose_text: str = purpose_text
        self.output_schema: Dict[str, Any] = output_schema

        # Per-field configuration
        self.enums: Dict[str, List[str]] = enums
        self.defaults: Dict[str, Any] = defaults
        self.cardinality: Dict[str, str] = cardinality
        self.option_descriptions: Dict[str, Dict[str, str]] = option_descriptions

        # Model configuration
        self.model_name: str = model_name
        self.temperature: float = temperature
        self.max_output_tokens: int = max_output_tokens

        # Derived mapping: field_id -> result_key in JSON
        self._result_keys: Dict[str, str] = build_result_key_map(output_schema)

        if self.mode not in ("chooser", "writer", "extractor", "scorer"):
            SimpleLogger.error(f"AgentPrompt[{self.agent_name}] unknown mode: {self.mode}")

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "AgentPrompt":
        """
        Build AgentPrompt from a JSON config dict as stored in data/agents/...

        Expects an A2-style schema with:
          - agent_meta
          - prompt_profile
          - llm_config
          - fields
          - output_schema
        """
        agent_meta = config.get("agent_meta", {})
        prompt_profile = config.get("prompt_profile", {})
        llm_cfg = config.get("llm_config", {})
        fields_cfg = config.get("fields", []) or []
        output_schema = config.get("output_schema", {}) or {}

        agent_name = agent_meta.get("agent_id") or agent_meta.get("agent_name") or "unknown_agent"
        version = str(agent_meta.get("version", "000"))
        mode = agent_meta.get("agent_type", "chooser")

        system_text = prompt_profile.get("system_role", "")
        purpose_text = prompt_profile.get("agent_purpose", "")

        model_name = llm_cfg.get("model_name", "gpt-5.1-mini")
        temperature = float(llm_cfg.get("temperature", 0.0))
        max_tokens = int(llm_cfg.get("max_tokens", 256))

        enums, defaults, cardinality, opt_desc = extract_field_config(fields_cfg)

        return cls(
            agent_name=agent_name,
            version=version,
            mode=mode,
            system_text=system_text,
            purpose_text=purpose_text,
            output_schema=output_schema,
            enums=enums,
            defaults=defaults,
            cardinality=cardinality,
            option_descriptions=opt_desc,
            model_name=model_name,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def model(self) -> str:
        """Model name used by llm_client."""
        return self.model_name

    @property
    def max_tokens(self) -> int:
        """Maximum output tokens for llm_client."""
        return self.max_output_tokens

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def compose(
        self,
        input_payload: Dict[str, Any],
        active_fields: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        """
        Build SYSTEM + USER messages and the response_format for the LLM.

        input_payload:
            Dict with keys like "task", "purpose", "context" (from SuperPrompt).

        active_fields:
            Optional list of field_ids that are "live" for this call, decided by A2.
            If None, all known enum fields are considered active.
        """
        if self.mode != "chooser":
            raise AgentPromptValidationError(
                f"AgentPrompt[{self.agent_name}] compose() currently only supports mode='chooser'"
            )

        active_set: Set[str]
        if active_fields is None:
            active_set = set(self.enums.keys())
        else:
            active_set = set(f for f in active_fields if f in self.enums)

        system_text = build_system_text(
            system_text=self.system_text,
            purpose_text=self.purpose_text,
            agent_name=self.agent_name,
            version=self.version,
        )

        user_text = build_user_text_for_chooser(
            input_payload=input_payload,
            enums=self.enums,
            cardinality=self.cardinality,
            option_descriptions=self.option_descriptions,
            result_keys=self._result_keys,
            active_fields=sorted(active_set),
        )

        messages = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ]
        response_format = {"type": "json_object"}

        return messages, response_format

    def parse(
        self,
        raw_output: Any,
        active_fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Parse and validate the LLM raw output into a clean Python dict.

        raw_output:
            Raw LLM response. Usually a string; treated as JSON or JSON-like.

        active_fields:
            Optional list of field_ids that were active for this call.
            If None, all enum fields are considered active.

        Returns
        -------
        result:
            Dict with normalized values per field_id, e.g.:
            {
                "system": ["rag_architect", "prompt_engineer"],
                "audience": "self_power_user",
                "tone": "neutral_analytical",
                "depth": "exhaustive",
                "confidence": "high",
            }
        """
        if self.mode != "chooser":
            raise AgentPromptValidationError(
                f"AgentPrompt[{self.agent_name}] parse() currently only supports mode='chooser'"
            )

        if active_fields is None:
            active_set: Set[str] = set(self.enums.keys())
        else:
            active_set = set(f for f in active_fields if f in self.enums)

        json_obj = extract_json_object(raw_output)

        result: Dict[str, Any] = {}
        for field_id, allowed in self.enums.items():
            if field_id not in active_set:
                # Inactive: caller (A2) keeps the existing value (e.g. user-set).
                continue

            result_key = self._result_keys.get(field_id, field_id)
            card = self.cardinality.get(field_id, "one")
            default_value = self.defaults.get(field_id)

            raw_value = json_obj.get(result_key, None)

            if card == "many":
                normalized = normalize_many(
                    field_id=field_id,
                    raw_value=raw_value,
                    allowed=allowed,
                    default_value=default_value,
                )
            else:
                normalized = normalize_one(
                    field_id=field_id,
                    raw_value=raw_value,
                    allowed=allowed,
                    default_value=default_value,
                )

            result[field_id] = normalized

        return result
