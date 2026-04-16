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

Neutrality rule:
- No agent-specific visible wording is invented here.
- Visible prompt wording must come from JSON or from the agent runtime payload.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

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
    build_user_text_for_selector,
    build_user_text_for_classifier,
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
        static_prompt: Dict[str, Any],
        dynamic_bindings: List[Dict[str, Any]],
        decision_targets: List[Dict[str, Any]],
        output_schema: Dict[str, Any],
        enums: Dict[str, List[str]],
        defaults: Dict[str, Any],
        cardinality: Dict[str, str],
        option_descriptions: Dict[str, Dict[str, str]],
        option_labels: Dict[str, Dict[str, str]],
        model_name: str,
        temperature: float,
        max_output_tokens: int,
    ) -> None:
        self.agent_name: str = agent_name
        self.version: str = version
        self.mode: str = mode  # "selector" | "classifier" | "writer" | "extractor" | "scorer"

        self.static_prompt: Dict[str, Any] = static_prompt
        self.dynamic_bindings: List[Dict[str, Any]] = dynamic_bindings
        self.decision_targets: List[Dict[str, Any]] = decision_targets
        self.output_schema: Dict[str, Any] = output_schema

        self.enums: Dict[str, List[str]] = enums
        self.defaults: Dict[str, Any] = defaults
        self.cardinality: Dict[str, str] = cardinality
        self.option_descriptions: Dict[str, Dict[str, str]] = option_descriptions
        self.option_labels: Dict[str, Dict[str, str]] = option_labels

        self.model_name: str = model_name
        self.temperature: float = temperature
        self.max_output_tokens: int = max_output_tokens

        self._result_keys: Dict[str, str] = build_result_key_map(output_schema)
        self._top_level_result_keys: Dict[str, str] = self._build_field_map(
            output_schema.get("top_level_fields", []) or []
        )
        self._item_result_keys: Dict[str, str] = self._build_field_map(
            output_schema.get("item_fields", []) or []
        )

        if self.mode not in ("selector", "classifier", "writer", "extractor", "scorer"):
            SimpleLogger.error(f"AgentPrompt[{self.agent_name}] unknown mode: {self.mode}")

    @staticmethod
    def _build_field_map(fields_cfg: List[Dict[str, Any]]) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for field in fields_cfg:
            field_id = field.get("field_id")
            if not field_id:
                continue
            result[field_id] = field.get("result_key", field_id)
        return result

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "AgentPrompt":
        agent_meta = config.get("agent_meta", {}) or {}
        llm_cfg = config.get("llm_config", {}) or {}
        output_schema = config.get("output_schema", {}) or {}

        static_prompt = config.get("static_prompt", {}) or {}
        dynamic_bindings = config.get("dynamic_bindings", []) or []
        decision_targets = config.get("decision_targets", []) or []

        if not static_prompt:
            prompt_profile = config.get("prompt_profile", {}) or {}
            static_prompt = {
                "system_role": prompt_profile.get("system_role", ""),
                "agent_purpose": prompt_profile.get("agent_purpose", ""),
                "notes": prompt_profile.get("notes", ""),
            }

        if not decision_targets:
            decision_targets = config.get("fields", []) or []

        agent_name = agent_meta.get("agent_id") or agent_meta.get("agent_name") or "unknown_agent"
        version = str(agent_meta.get("version", "000"))

        raw_mode = str(agent_meta.get("agent_type", "selector")).strip().lower()
        mode_aliases = {
            "chooser": "selector",
            "multi-chooser": "classifier",
            "multi_chooser": "classifier",
        }
        mode = mode_aliases.get(raw_mode, raw_mode)

        model_name = llm_cfg.get("model_name", "gpt-4.1-mini")
        temperature = float(llm_cfg.get("temperature", 0.0))
        max_tokens = int(llm_cfg.get("max_tokens", 256))

        enums, defaults, cardinality, opt_desc, opt_labels = extract_field_config(decision_targets)

        return cls(
            agent_name=agent_name,
            version=version,
            mode=mode,
            static_prompt=static_prompt,
            dynamic_bindings=dynamic_bindings,
            decision_targets=decision_targets,
            output_schema=output_schema,
            enums=enums,
            defaults=defaults,
            cardinality=cardinality,
            option_descriptions=opt_desc,
            option_labels=opt_labels,
            model_name=model_name,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

    @property
    def model(self) -> str:
        return self.model_name

    @property
    def max_tokens(self) -> int:
        return self.max_output_tokens

    def compose(
        self,
        input_payload: Dict[str, Any],
        active_fields: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        """
        Build SYSTEM + USER messages and the response_format for the LLM.

        Neutrality rule:
        - SYSTEM text comes only from static_prompt.
        - USER text comes only from dynamic_bindings + runtime payload.
        """
        for binding in self.dynamic_bindings:
            binding_id = binding.get("id")
            if not binding_id:
                continue
            if binding.get("required", False) and binding_id not in input_payload:
                raise AgentPromptValidationError(
                    f"AgentPrompt[{self.agent_name}] missing required input binding: '{binding_id}'"
                )

        system_text = build_system_text(
            static_prompt=self.static_prompt,
            agent_name=self.agent_name,
            version=self.version,
        )

        if self.mode == "selector":
            if active_fields is None:
                active_list: List[str] = list(self.enums.keys())
            else:
                active_list = [field_id for field_id in active_fields if field_id in self.enums]

            user_text = build_user_text_for_selector(
                input_payload=input_payload,
                dynamic_bindings=self.dynamic_bindings,
                decision_targets=self.decision_targets,
                result_keys=self._result_keys,
                active_fields=active_list,
            )

        elif self.mode == "classifier":
            user_text = build_user_text_for_classifier(
                input_payload=input_payload,
                dynamic_bindings=self.dynamic_bindings,
                decision_targets=self.decision_targets,
                output_schema=self.output_schema,
                top_level_result_keys=self._top_level_result_keys,
                item_result_keys=self._item_result_keys,
            )

        else:
            raise AgentPromptValidationError(
                f"AgentPrompt[{self.agent_name}] compose() currently only supports mode='selector' or mode='classifier'"
            )

        messages = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ]
        response_format = {"type": "json_object"}

        SimpleLogger.info(f"AgentPrompt[{self.agent_name}] SYSTEM prompt:")
        SimpleLogger.info(system_text)
        SimpleLogger.info(f"AgentPrompt[{self.agent_name}] USER prompt:")
        SimpleLogger.info(user_text)

        return messages, response_format

    def parse(
        self,
        raw_output: Any,
        active_fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Parse and validate the LLM raw output into a clean Python dict.
        """
        json_obj = extract_json_object(raw_output)

        if self.mode == "selector":
            if active_fields is None:
                active_list: List[str] = list(self.enums.keys())
            else:
                active_list = [field_id for field_id in active_fields if field_id in self.enums]

            active_set = set(active_list)
            result: Dict[str, Any] = {}

            for field_id, allowed in self.enums.items():
                if field_id not in active_set:
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

        if self.mode == "classifier":
            result: Dict[str, Any] = {}

            for field_id, result_key in self._top_level_result_keys.items():
                raw_value = json_obj.get(result_key, "")
                if isinstance(raw_value, str):
                    result[field_id] = raw_value.strip().lower()
                elif raw_value is None:
                    result[field_id] = ""
                else:
                    result[field_id] = str(raw_value).strip()

            root_key = self.output_schema.get("root_key", "item_decisions")
            item_id_key = self.output_schema.get("item_id_key", "chunk_id")

            raw_items = json_obj.get(root_key, []) or []
            if not isinstance(raw_items, list):
                raw_items = []

            normalized_items: List[Dict[str, Any]] = []

            for raw_item in raw_items:
                if not isinstance(raw_item, dict):
                    continue

                raw_chunk_id = raw_item.get(item_id_key)
                if raw_chunk_id is None:
                    continue

                chunk_id = str(raw_chunk_id).strip()
                if not chunk_id:
                    continue

                item_result: Dict[str, Any] = {"chunk_id": chunk_id}

                for field_id, allowed in self.enums.items():
                    result_key = self._item_result_keys.get(field_id, field_id)
                    default_value = self.defaults.get(field_id)
                    raw_value = raw_item.get(result_key, None)

                    normalized = normalize_one(
                        field_id=field_id,
                        raw_value=raw_value,
                        allowed=allowed,
                        default_value=default_value,
                    )
                    item_result[field_id] = normalized

                normalized_items.append(item_result)

            result[root_key] = normalized_items
            return result

        raise AgentPromptValidationError(
            f"AgentPrompt[{self.agent_name}] parse() currently only supports mode='selector' or mode='classifier'"
        )