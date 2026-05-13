# ragstream/preprocessing/activebrief_relation_classifier.py
# -*- coding: utf-8 -*-
"""
ActiveBrief Relation Classifier.

Runs after deterministic PreProcessing.

LLM responsibility:
- classify the current prompt using two independent dimensions:
  1. prompt_materiality: STRONG | WEAK
  2. topic_relation: SAME_TOPIC | RELATED_DOMAIN | IRRELEVANT

Deterministic responsibility:
- map the two classifier outputs to later retrieval / prompt / memory-context decisions.
- write the result into SuperPrompt.extras.

The LLM does not decide any action behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import json

from ragstream.orchestration.agent_factory import AgentFactory
from ragstream.orchestration.llm_client import LLMClient
from ragstream.orchestration.super_prompt import SuperPrompt
from ragstream.textforge.RagLog import LogDeveloper as _logger_dev


DEV_LOG_ENABLED = True


def logger_dev(*args, **kwargs):
    if DEV_LOG_ENABLED:
        return _logger_dev(*args, **kwargs)
    return None


JsonDict = dict[str, Any]


PROMPT_MATERIALITY_VALUES: set[str] = {
    "STRONG",
    "WEAK",
}

TOPIC_RELATION_VALUES: set[str] = {
    "SAME_TOPIC",
    "RELATED_DOMAIN",
    "IRRELEVANT",
}

NO_ACTIVEBRIEF_STATE = "NO_ACTIVEBRIEF"


@dataclass(frozen=True)
class ActiveBriefInfo:
    title: str
    body: str
    record_id: str


@dataclass(frozen=True)
class ActiveBriefRelationDecision:
    prompt_materiality: str
    topic_relation: str
    use_activebrief_for_retrieval: bool
    final_prompt_mode: str
    allow_memory_context: bool
    memory_context_policy: str

    def to_dict(self) -> JsonDict:
        return {
            "prompt_materiality": self.prompt_materiality,
            "topic_relation": self.topic_relation,
            "use_activebrief_for_retrieval": self.use_activebrief_for_retrieval,
            "final_prompt_mode": self.final_prompt_mode,
            "allow_memory_context": self.allow_memory_context,
            "memory_context_policy": self.memory_context_policy,
        }


class ActiveBriefRelationClassifier:
    """
    Classifies current prompt materiality and relation to the current ActiveBrief.
    """

    def __init__(
        self,
        *,
        agent_factory: AgentFactory,
        llm_client: LLMClient,
        agent_id: str = "activebrief_relation_classifier",
        version: str = "activebrief_relation_classifier_001",
    ) -> None:
        self.agent_factory = agent_factory
        self.llm_client = llm_client
        self.agent_id = agent_id
        self.version = version

    def run(
        self,
        *,
        sp: SuperPrompt,
        memory_manager: Any | None = None,
        raw_user_text: str = "",
    ) -> SuperPrompt:
        """
        Run classifier and write result into sp.extras.
        """
        if sp is None:
            raise ValueError("ActiveBriefRelationClassifier.run: 'sp' must not be None")

        activebrief_info = self._find_current_activebrief(memory_manager)

        if activebrief_info is None:
            current_prompt = str(raw_user_text or "").strip()
            self._write_result_to_superprompt(
                sp=sp,
                activebrief_info=None,
                prompt_materiality="UNKNOWN",
                topic_relation=NO_ACTIVEBRIEF_STATE,
                llm_used=False,
            )
            return sp

        current_prompt = self._build_current_prompt_text(
            sp=sp,
            raw_user_text=raw_user_text,
        )

        if not current_prompt.strip():
            self._write_result_to_superprompt(
                sp=sp,
                activebrief_info=activebrief_info,
                prompt_materiality="WEAK",
                topic_relation="IRRELEVANT",
                llm_used=False,
            )
            return sp

        classification = self.classify(
            current_prompt=current_prompt,
            activebrief_title=activebrief_info.title,
            activebrief_body=activebrief_info.body,
        )

        self._write_result_to_superprompt(
            sp=sp,
            activebrief_info=activebrief_info,
            prompt_materiality=classification["prompt_materiality"],
            topic_relation=classification["topic_relation"],
            llm_used=True,
        )

        return sp

    def classify(
        self,
        *,
        current_prompt: str,
        activebrief_title: str,
        activebrief_body: str,
    ) -> JsonDict:
        """
        LLM call.

        Returns:
        {
          "prompt_materiality": "STRONG" | "WEAK",
          "topic_relation": "SAME_TOPIC" | "RELATED_DOMAIN" | "IRRELEVANT"
        }
        """
        agent = self.agent_factory.get_agent(
            agent_id=self.agent_id,
            version=self.version,
        )

        input_payload: JsonDict = {
            "activebrief_title": str(activebrief_title or "").strip(),
            "activebrief_body": str(activebrief_body or "").strip(),
            "current_prompt": str(current_prompt or "").strip(),
            "required_output": self._build_required_output_text(),
        }

        messages, _response_format = agent.compose(
            input_payload=input_payload,
            active_fields=["prompt_materiality", "topic_relation"],
        )

        logger_dev(
            "ActiveBriefRelationClassifier LLM INPUT\n"
            + json.dumps(
                {
                    "messages": messages,
                    "input_payload": input_payload,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            "DEBUG",
            "CONFIDENTIAL",
        )

        response = self.llm_client.responses(
            messages=messages,
            model_name=agent.model_name,
            max_output_tokens=agent.max_output_tokens,
            reasoning_effort="minimal",
            return_metadata=True,
            prompt_cache_key="activebrief_rel_001",
        )

        raw_result = str(response.get("content", "") or "")

        parsed = agent.parse(
            raw_result,
            active_fields=["prompt_materiality", "topic_relation"],
        )

        prompt_materiality = str(parsed.get("prompt_materiality", "") or "").strip().upper()
        topic_relation = str(parsed.get("topic_relation", "") or "").strip().upper()

        logger_dev(
            "ActiveBriefRelationClassifier LLM OUTPUT\n"
            + json.dumps(
                {
                    "raw_result": raw_result,
                    "parsed": parsed,
                    "prompt_materiality": prompt_materiality,
                    "topic_relation": topic_relation,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            "DEBUG",
            "CONFIDENTIAL",
        )

        if prompt_materiality not in PROMPT_MATERIALITY_VALUES:
            raise ValueError(
                "ActiveBriefRelationClassifier: invalid prompt_materiality from LLM: "
                f"{prompt_materiality!r}"
            )

        if topic_relation not in TOPIC_RELATION_VALUES:
            raise ValueError(
                "ActiveBriefRelationClassifier: invalid topic_relation from LLM: "
                f"{topic_relation!r}"
            )

        return {
            "prompt_materiality": prompt_materiality,
            "topic_relation": topic_relation,
        }

    def _write_result_to_superprompt(
        self,
        *,
        sp: SuperPrompt,
        activebrief_info: ActiveBriefInfo | None,
        prompt_materiality: str,
        topic_relation: str,
        llm_used: bool,
    ) -> None:
        decision = self._build_decision(
            prompt_materiality=prompt_materiality,
            topic_relation=topic_relation,
        )

        relation_state = self._build_relation_state(
            prompt_materiality=prompt_materiality,
            topic_relation=topic_relation,
        )

        sp.extras["activebrief_prompt_materiality"] = prompt_materiality
        sp.extras["activebrief_topic_relation"] = topic_relation
        sp.extras["activebrief_relation_state"] = relation_state
        sp.extras["activebrief_relation_llm_used"] = bool(llm_used)
        sp.extras["activebrief_relation_decision"] = decision.to_dict()

        if activebrief_info is None:
            activebrief_snapshot = {
                "record_id": "",
                "title": "",
                "body": "",
            }
        else:
            activebrief_snapshot = {
                "record_id": activebrief_info.record_id,
                "title": activebrief_info.title,
                "body": activebrief_info.body,
            }

        sp.extras["activebrief_relation_activebrief"] = activebrief_snapshot

    @staticmethod
    def _build_relation_state(
        *,
        prompt_materiality: str,
        topic_relation: str,
    ) -> str:
        if topic_relation == NO_ACTIVEBRIEF_STATE:
            return NO_ACTIVEBRIEF_STATE

        return f"{prompt_materiality}_{topic_relation}"

    @staticmethod
    def _build_decision(
        *,
        prompt_materiality: str,
        topic_relation: str,
    ) -> ActiveBriefRelationDecision:
        if topic_relation == NO_ACTIVEBRIEF_STATE:
            return ActiveBriefRelationDecision(
                prompt_materiality=prompt_materiality,
                topic_relation=topic_relation,
                use_activebrief_for_retrieval=False,
                final_prompt_mode="none",
                allow_memory_context=True,
                memory_context_policy="normal_no_activebrief",
            )

        if prompt_materiality == "STRONG" and topic_relation == "SAME_TOPIC":
            return ActiveBriefRelationDecision(
                prompt_materiality=prompt_materiality,
                topic_relation=topic_relation,
                use_activebrief_for_retrieval=False,
                final_prompt_mode="full_activebrief",
                allow_memory_context=True,
                memory_context_policy="allowed",
            )

        if prompt_materiality == "WEAK" and topic_relation == "SAME_TOPIC":
            return ActiveBriefRelationDecision(
                prompt_materiality=prompt_materiality,
                topic_relation=topic_relation,
                use_activebrief_for_retrieval=True,
                final_prompt_mode="full_activebrief",
                allow_memory_context=True,
                memory_context_policy="allowed",
            )

        if prompt_materiality == "STRONG" and topic_relation == "RELATED_DOMAIN":
            return ActiveBriefRelationDecision(
                prompt_materiality=prompt_materiality,
                topic_relation=topic_relation,
                use_activebrief_for_retrieval=False,
                final_prompt_mode="title_related_domain_note",
                allow_memory_context=True,
                memory_context_policy="allowed_related_domain",
            )

        if prompt_materiality == "WEAK" and topic_relation == "RELATED_DOMAIN":
            return ActiveBriefRelationDecision(
                prompt_materiality=prompt_materiality,
                topic_relation=topic_relation,
                use_activebrief_for_retrieval=True,
                final_prompt_mode="title_related_domain_note",
                allow_memory_context=True,
                memory_context_policy="allowed_related_domain",
            )

        if prompt_materiality == "STRONG" and topic_relation == "IRRELEVANT":
            return ActiveBriefRelationDecision(
                prompt_materiality=prompt_materiality,
                topic_relation=topic_relation,
                use_activebrief_for_retrieval=False,
                final_prompt_mode="title_topic_shift_note",
                allow_memory_context=False,
                memory_context_policy="disabled",
            )

        if prompt_materiality == "WEAK" and topic_relation == "IRRELEVANT":
            return ActiveBriefRelationDecision(
                prompt_materiality=prompt_materiality,
                topic_relation=topic_relation,
                use_activebrief_for_retrieval=False,
                final_prompt_mode="none",
                allow_memory_context=False,
                memory_context_policy="disabled",
            )

        raise ValueError(
            "Unknown ActiveBrief classifier combination: "
            f"prompt_materiality={prompt_materiality!r}, topic_relation={topic_relation!r}"
        )

    @staticmethod
    def _find_current_activebrief(memory_manager: Any | None) -> ActiveBriefInfo | None:
        if memory_manager is None:
            return None

        records = list(getattr(memory_manager, "records", []) or [])

        for record in reversed(records):
            tag = str(getattr(record, "tag", "") or "").strip()
            if tag == "Black":
                continue

            body = str(getattr(record, "active_retrieval_brief", "") or "").strip()
            if not body:
                continue

            title = str(getattr(record, "active_retrieval_brief_title", "") or "").strip()
            record_id = str(getattr(record, "record_id", "") or "").strip()

            return ActiveBriefInfo(
                title=title,
                body=body,
                record_id=record_id,
            )

        return None

    @staticmethod
    def _build_current_prompt_text(
        *,
        sp: SuperPrompt,
        raw_user_text: str,
    ) -> str:
        parts: list[str] = []

        purpose = str(sp.body.get("purpose") or "").strip()
        task = str(sp.body.get("task") or "").strip()
        context = str(sp.body.get("context") or "").strip()

        if purpose:
            parts.append("PURPOSE\n" + purpose)
        if task:
            parts.append("TASK\n" + task)
        if context:
            parts.append("CONTEXT\n" + context)

        text = "\n\n".join(parts).strip()
        if text:
            return text

        return str(raw_user_text or "").strip()

    @staticmethod
    def _build_required_output_text() -> str:
        return (
            "Return exactly one JSON object:\n"
            "{\n"
            '  "prompt_materiality": "<STRONG_OR_WEAK>",\n'
            '  "topic_relation": "<SAME_TOPIC_OR_RELATED_DOMAIN_OR_IRRELEVANT>"\n'
            "}\n\n"
            "prompt_materiality must be exactly one of:\n"
            "- STRONG\n"
            "- WEAK\n\n"
            "topic_relation must be exactly one of:\n"
            "- SAME_TOPIC\n"
            "- RELATED_DOMAIN\n"
            "- IRRELEVANT"
        )