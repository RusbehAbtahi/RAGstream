# ragstream/memory/compression/memory_active_retrieval_brief.py
# -*- coding: utf-8 -*-
"""
MemoryActiveRetrievalBriefBuilder
=================================

Creates the ActiveRetrievalBrief for a newly captured MemoryRecord.

Current design:
- runs during Memory Recording
- uses K-1 ActiveBrief + reduced Q/A of K
- creates K ActiveBrief
- writes nothing directly to disk
- returns result to MemoryManager, which owns MemoryRecord truth

LLM calls:
- first record: init JSON
- later records: update JSON

Relevance-gate behavior:
- normal case:
    Q/A passes against current ActiveBrief center -> update ActiveBrief with LLM
- unrelated case:
    Q/A fails against ActiveBrief and pending topic -> skip LLM, copy old brief
- topic-shift case:
    Q/A fails against ActiveBrief but passes against pending skipped Q/A -> create a new brief from pending Q/A + current Q/A
"""

from __future__ import annotations

import json

from pathlib import Path
from typing import Any

from ragstream.memory.memory_record import MemoryRecord
from ragstream.memory.compression.memory_sentence_reducer import (
    MemorySentenceReducer,
    ReducedQA,
)
from ragstream.memory.compression.memory_activebrief_relevance_gate import (
    MemoryActiveBriefRelevanceGate,
)
from ragstream.orchestration.agent_factory import AgentFactory
from ragstream.orchestration.agent_prompt import AgentPrompt
from ragstream.orchestration.llm_client import LLMClient
from ragstream.textforge.RagLog import LogDeveloper as logger_dev


JsonDict = dict[str, Any]


class MemoryActiveRetrievalBriefBuilder:
    def __init__(
        self,
        *,
        runtime_config: JsonDict | None = None,
        agent_factory: AgentFactory | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.runtime_config = runtime_config if isinstance(runtime_config, dict) else self._load_runtime_config()

        cfg = self.runtime_config.get("memory_active_retrieval_brief", {}) or {}
        reducer_cfg = cfg.get("reducer", {}) or {}
        llm_cfg = cfg.get("llm", {}) or {}
        gate_cfg = cfg.get("activebrief_relevance_gate", {}) or {}

        self.target_brief_tokens = int(llm_cfg.get("target_brief_tokens", 700))
        self.prompt_cache_key = str(
            llm_cfg.get("prompt_cache_key", "memory_activebrief_qa_summarizer")
        )

        self.agent_id = str(
            llm_cfg.get("agent_id", "memory_activebrief_qa_summarizer")
        )
        self.init_agent_version = str(
            llm_cfg.get(
                "init_agent_version",
                "memory_activebrief_qa_summarizer_init_001",
            )
        )
        self.update_agent_version = str(
            llm_cfg.get(
                "update_agent_version",
                "memory_activebrief_qa_summarizer_update_001",
            )
        )

        embedding_model = str(reducer_cfg.get("embedding_model", "text-embedding-3-small"))
        window_size_sentences = int(reducer_cfg.get("window_size_sentences", 3))
        window_overlap_sentences = int(reducer_cfg.get("window_overlap_sentences", 1))

        self.relevance_gate_enabled = bool(gate_cfg.get("enabled", True))

        self.reducer = MemorySentenceReducer(
            max_tokens_total=int(reducer_cfg.get("max_tokens_total", 3000)),
            question_max_tokens=int(reducer_cfg.get("question_max_tokens", 1000)),
            window_size_sentences=window_size_sentences,
            window_overlap_sentences=window_overlap_sentences,
            redundancy_threshold=float(reducer_cfg.get("redundancy_threshold", 0.92)),
            embedding_model=embedding_model,
        )

        self.relevance_gate = MemoryActiveBriefRelevanceGate(
            embedding_model=embedding_model,
            window_size_sentences=window_size_sentences,
            window_overlap_sentences=window_overlap_sentences,
            activebrief_threshold=float(gate_cfg.get("activebrief_threshold", 0.25)),
            pending_topic_threshold=float(gate_cfg.get("pending_topic_threshold", 0.25)),
        )

        self.agent_factory = agent_factory or AgentFactory()
        self.llm_client = llm_client or LLMClient()

    def build_for_record(
        self,
        *,
        record: MemoryRecord,
        previous_records: list[MemoryRecord],
        pending_topic_buffer: dict[str, Any] | None = None,
    ) -> JsonDict:
        if record is None:
            raise ValueError("MemoryActiveRetrievalBriefBuilder.build_for_record: record is None")

        pending_topic_buffer = pending_topic_buffer if isinstance(pending_topic_buffer, dict) else {}

        previous_brief_info = self._find_previous_clean_brief(previous_records)

        reduced_qa = self.reducer.reduce_with_centroid(
            input_text=record.input_text,
            output_text=record.output_text,
        )

        logger_dev(
            "ActiveBrief current raw Q/A\n"
            + json.dumps(
                {
                    "record_id": record.record_id,
                    "input_text": record.input_text,
                    "output_text": record.output_text,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            "DEBUG",
            "CONFIDENTIAL",
        )

        logger_dev(
            "ActiveBrief reduced Q/A after deterministic reduction\n"
            + json.dumps(
                {
                    "record_id": record.record_id,
                    "reduced_question": reduced_qa.reduced_question,
                    "reduced_answer": reduced_qa.reduced_answer,
                    "question_vector_count": len(reduced_qa.question_vectors),
                    "answer_vector_count": len(reduced_qa.answer_vectors),
                    "diagnostics": reduced_qa.diagnostics,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            "DEBUG",
            "CONFIDENTIAL",
        )

        logger_dev(
            "ActiveBrief previous clean brief and pending-topic state\n"
            + json.dumps(
                {
                    "previous_brief_info": previous_brief_info,
                    "pending_topic_buffer": self._pending_buffer_log_view(pending_topic_buffer),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            "DEBUG",
            "CONFIDENTIAL",
        )

        if previous_brief_info["previous_active_retrieval_brief"]:
            return self._handle_update_or_skip(
                record=record,
                reduced_qa=reduced_qa,
                previous_brief_info=previous_brief_info,
                pending_topic_buffer=pending_topic_buffer,
            )

        result = self._run_init_agent(
            record=record,
            reduced_qa=reduced_qa,
            call_name="Memory ActiveBrief Init",
        )
        contributor_ids = [record.record_id]
        active_brief = str(result.get("active_retrieval_brief", "") or "").strip()

        logger_dev(
            "ActiveBrief new LLM result\n"
            + json.dumps(
                {
                    "record_id": record.record_id,
                    "route": "init_no_previous_activebrief",
                    "active_retrieval_brief": active_brief,
                    "active_retrieval_brief_contributor_ids": contributor_ids,
                    "pending_topic_buffer_after": {},
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            "DEBUG",
            "CONFIDENTIAL",
        )

        return {
            "active_retrieval_brief": active_brief,
            "active_retrieval_brief_contributor_ids": contributor_ids,
            "reduced_qa_diagnostics": reduced_qa.diagnostics,
            "activebrief_llm_skipped": False,
            "activebrief_gate_route": "init_no_previous_activebrief",
            "pending_activebrief_topic_buffer": {},
        }

    def _handle_update_or_skip(
        self,
        *,
        record: MemoryRecord,
        reduced_qa: ReducedQA,
        previous_brief_info: JsonDict,
        pending_topic_buffer: dict[str, Any],
    ) -> JsonDict:
        previous_brief = str(previous_brief_info["previous_active_retrieval_brief"])
        previous_contributor_ids = list(previous_brief_info.get("contributor_ids") or [])

        if not self.relevance_gate_enabled:
            result = self._run_update_agent(
                record=record,
                reduced_qa=reduced_qa,
                previous_brief=previous_brief,
                call_name="Memory ActiveBrief Update",
            )
            contributor_ids = self._merge_contributor_ids(previous_contributor_ids, [record.record_id])
            active_brief = str(result.get("active_retrieval_brief", "") or "").strip()

            return {
                "active_retrieval_brief": active_brief,
                "active_retrieval_brief_contributor_ids": contributor_ids,
                "reduced_qa_diagnostics": reduced_qa.diagnostics,
                "activebrief_llm_skipped": False,
                "activebrief_gate_route": "gate_disabled",
                "pending_activebrief_topic_buffer": {},
            }

        gate_result = self.relevance_gate.evaluate(
            record_id=record.record_id,
            previous_active_retrieval_brief=previous_brief,
            question_vectors=reduced_qa.question_vectors,
            answer_vectors=reduced_qa.answer_vectors,
            pending_topic_buffer=pending_topic_buffer,
        )

        if gate_result.route == "activebrief_update":
            result = self._run_update_agent(
                record=record,
                reduced_qa=reduced_qa,
                previous_brief=previous_brief,
                call_name="Memory ActiveBrief Update",
            )
            contributor_ids = self._merge_contributor_ids(previous_contributor_ids, [record.record_id])
            active_brief = str(result.get("active_retrieval_brief", "") or "").strip()

            logger_dev(
                "ActiveBrief update accepted by relevance gate\n"
                + json.dumps(
                    {
                        "record_id": record.record_id,
                        "route": gate_result.route,
                        "reason": gate_result.reason,
                        "active_retrieval_brief_contributor_ids": contributor_ids,
                        "pending_topic_buffer_after": {},
                        "gate_diagnostics": gate_result.diagnostics,
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                "DEBUG",
                "CONFIDENTIAL",
            )

            return {
                "active_retrieval_brief": active_brief,
                "active_retrieval_brief_contributor_ids": contributor_ids,
                "reduced_qa_diagnostics": reduced_qa.diagnostics,
                "activebrief_relevance_gate": gate_result.diagnostics,
                "activebrief_llm_skipped": False,
                "activebrief_gate_route": gate_result.route,
                "pending_activebrief_topic_buffer": {},
            }

        if gate_result.route == "pending_topic_shift":
            combined_reduced_qa = self._combine_pending_and_current_reduced_qa(
                pending_topic_buffer=pending_topic_buffer,
                current_reduced_qa=reduced_qa,
            )

            result = self._run_update_agent(
                record=record,
                reduced_qa=combined_reduced_qa,
                previous_brief=previous_brief,
                call_name="Memory ActiveBrief Topic Shift",
            )

            pending_record_id = str(pending_topic_buffer.get("record_id", "") or "")
            contributor_ids = self._merge_contributor_ids(
                previous_contributor_ids,
                [pending_record_id, record.record_id],
            )
            active_brief = str(result.get("active_retrieval_brief", "") or "").strip()

            logger_dev(
                "ActiveBrief topic shift confirmed by pending-topic gate\n"
                + json.dumps(
                    {
                        "record_id": record.record_id,
                        "pending_record_id": pending_record_id,
                        "route": gate_result.route,
                        "reason": gate_result.reason,
                        "active_retrieval_brief": active_brief,
                        "active_retrieval_brief_contributor_ids": contributor_ids,
                        "pending_topic_buffer_after": {},
                        "gate_diagnostics": gate_result.diagnostics,
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                "DEBUG",
                "CONFIDENTIAL",
            )

            return {
                "active_retrieval_brief": active_brief,
                "active_retrieval_brief_contributor_ids": contributor_ids,
                "reduced_qa_diagnostics": reduced_qa.diagnostics,
                "activebrief_relevance_gate": gate_result.diagnostics,
                "activebrief_llm_skipped": False,
                "activebrief_gate_route": gate_result.route,
                "pending_activebrief_topic_buffer": {},
            }

        new_pending_buffer = self.relevance_gate.build_pending_topic_buffer(
            record_id=record.record_id,
            created_at_utc=record.created_at_utc,
            reduced_question=reduced_qa.reduced_question,
            reduced_answer=reduced_qa.reduced_answer,
            question_vectors=reduced_qa.question_vectors,
            answer_vectors=reduced_qa.answer_vectors,
        )

        logger_dev(
            "ActiveBrief update skipped by relevance gate\n"
            + json.dumps(
                {
                    "record_id": record.record_id,
                    "route": gate_result.route,
                    "reason": gate_result.reason,
                    "copied_previous_brief_record_id": previous_brief_info.get("record_id", ""),
                    "active_retrieval_brief": previous_brief,
                    "active_retrieval_brief_contributor_ids": previous_contributor_ids,
                    "pending_topic_buffer_after": self._pending_buffer_log_view(new_pending_buffer),
                    "gate_diagnostics": gate_result.diagnostics,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            "DEBUG",
            "CONFIDENTIAL",
        )

        return {
            "active_retrieval_brief": previous_brief,
            "active_retrieval_brief_contributor_ids": previous_contributor_ids,
            "reduced_qa_diagnostics": reduced_qa.diagnostics,
            "activebrief_relevance_gate": gate_result.diagnostics,
            "activebrief_llm_skipped": True,
            "activebrief_gate_route": gate_result.route,
            "pending_activebrief_topic_buffer": new_pending_buffer,
        }

    def _run_init_agent(
        self,
        *,
        record: MemoryRecord,
        reduced_qa: ReducedQA,
        call_name: str,
    ) -> JsonDict:
        agent_prompt = self.agent_factory.get_agent(
            self.agent_id,
            self.init_agent_version,
        )

        payload = self._compose_init_payload(
            record=record,
            reduced_qa=reduced_qa,
        )

        return self._run_agent_call(
            call_name=call_name,
            agent_prompt=agent_prompt,
            input_payload=payload,
        )

    def _run_update_agent(
        self,
        *,
        record: MemoryRecord,
        reduced_qa: ReducedQA,
        previous_brief: str,
        call_name: str,
    ) -> JsonDict:
        agent_prompt = self.agent_factory.get_agent(
            self.agent_id,
            self.update_agent_version,
        )

        payload = self._compose_update_payload(
            record=record,
            reduced_qa=reduced_qa,
            previous_brief=previous_brief,
        )

        return self._run_agent_call(
            call_name=call_name,
            agent_prompt=agent_prompt,
            input_payload=payload,
        )

    def _compose_init_payload(
        self,
        *,
        record: MemoryRecord,
        reduced_qa: ReducedQA,
    ) -> JsonDict:
        return {
            "reduced_question": reduced_qa.reduced_question,
            "reduced_answer": reduced_qa.reduced_answer,
            "memory_record_metadata": self._build_metadata_text(record),
            "required_output": self._build_required_output_text(),
        }

    def _compose_update_payload(
        self,
        *,
        record: MemoryRecord,
        reduced_qa: ReducedQA,
        previous_brief: str,
    ) -> JsonDict:
        return {
            "previous_active_retrieval_brief": previous_brief,
            "reduced_question": reduced_qa.reduced_question,
            "reduced_answer": reduced_qa.reduced_answer,
            "memory_record_metadata": self._build_metadata_text(record),
            "required_output": self._build_required_output_text(),
        }

    def _run_agent_call(
        self,
        *,
        call_name: str,
        agent_prompt: AgentPrompt,
        input_payload: JsonDict,
    ) -> JsonDict:
        messages, response_format = agent_prompt.compose(input_payload=input_payload)

        logger_dev(
            f"{call_name} LLM prompt payload\n"
            + json.dumps(input_payload, ensure_ascii=False, indent=2, default=str),
            "DEBUG",
            "CONFIDENTIAL",
        )

        logger_dev(
            f"{call_name} LLM messages\n"
            + json.dumps(messages, ensure_ascii=False, indent=2, default=str),
            "DEBUG",
            "CONFIDENTIAL",
        )

        response = self.llm_client.responses(
            messages=messages,
            model_name=agent_prompt.model_name,
            max_output_tokens=agent_prompt.max_output_tokens,
            reasoning_effort="minimal",
            return_metadata=True,
            prompt_cache_key=self.prompt_cache_key,
        )

        raw_content = str(response.get("content", "") or "")
        usage = response.get("usage", {}) or {}

        logger_dev(
            f"{call_name} LLM raw response\n"
            + json.dumps(
                {
                    "content": raw_content,
                    "usage": usage,
                    "model_name": response.get("model_name", ""),
                    "status": response.get("status", ""),
                    "incomplete_reason": response.get("incomplete_reason", ""),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            "DEBUG",
            "CONFIDENTIAL",
        )

        parsed = agent_prompt.parse(raw_content)

        logger_dev(
            f"{call_name} parsed result\n"
            + json.dumps(parsed, ensure_ascii=False, indent=2, default=str),
            "DEBUG",
            "CONFIDENTIAL",
        )

        return parsed

    def _combine_pending_and_current_reduced_qa(
        self,
        *,
        pending_topic_buffer: dict[str, Any],
        current_reduced_qa: ReducedQA,
    ) -> ReducedQA:
        """
        Topic-shift LLM payload.

        When the current Q/A is not related to the old ActiveBrief but is related
        to the previously skipped Q/A, we create a new ActiveBrief from both:
        - the previous pending Q/A
        - the current Q/A

        This prevents the first skipped item of the new theme from being lost.
        """
        pending_question = str(pending_topic_buffer.get("reduced_question", "") or "").strip()
        pending_answer = str(pending_topic_buffer.get("reduced_answer", "") or "").strip()

        combined_question_parts = []
        if pending_question:
            combined_question_parts.append("[Pending skipped Q/A question]\n" + pending_question)
        if current_reduced_qa.reduced_question:
            combined_question_parts.append("[Current Q/A question]\n" + current_reduced_qa.reduced_question)

        combined_answer_parts = []
        if pending_answer:
            combined_answer_parts.append("[Pending skipped Q/A answer]\n" + pending_answer)
        if current_reduced_qa.reduced_answer:
            combined_answer_parts.append("[Current Q/A answer]\n" + current_reduced_qa.reduced_answer)

        return ReducedQA(
            reduced_question="\n\n".join(combined_question_parts).strip(),
            reduced_answer="\n\n".join(combined_answer_parts).strip(),
            question_vectors=[],
            answer_vectors=[],
            diagnostics={
                "mode": "topic_shift_combined_pending_and_current",
                "pending_record_id": str(pending_topic_buffer.get("record_id", "") or ""),
                "current_question_vector_count": len(current_reduced_qa.question_vectors),
                "current_answer_vector_count": len(current_reduced_qa.answer_vectors),
            },
        )

    def _find_previous_clean_brief(
        self,
        previous_records: list[MemoryRecord],
    ) -> JsonDict:
        records = list(previous_records or [])
        black_ids = {
            record.record_id
            for record in records
            if str(getattr(record, "tag", "") or "").strip() == "Black"
        }

        for record in reversed(records):
            if str(getattr(record, "tag", "") or "").strip() == "Black":
                continue

            brief = str(getattr(record, "active_retrieval_brief", "") or "").strip()
            if not brief:
                continue

            contributor_ids = list(
                getattr(record, "active_retrieval_brief_contributor_ids", []) or []
            )

            if any(contributor_id in black_ids for contributor_id in contributor_ids):
                continue

            return {
                "record_id": record.record_id,
                "previous_active_retrieval_brief": brief,
                "contributor_ids": contributor_ids or [record.record_id],
            }

        return {
            "record_id": "",
            "previous_active_retrieval_brief": "",
            "contributor_ids": [],
        }

    def _build_metadata_text(
        self,
        record: MemoryRecord,
    ) -> str:
        data = {
            "record_id": record.record_id,
            "parent_id": record.parent_id,
            "created_at_utc": record.created_at_utc,
            "source": record.source,
            "tag": record.tag,
            "retrieval_source_mode": record.retrieval_source_mode,
            "active_project_name": record.active_project_name,
            "auto_keywords": record.auto_keywords,
            "user_keywords": record.user_keywords,
            "embedded_files_snapshot": record.embedded_files_snapshot,
        }

        return json.dumps(data, ensure_ascii=False, indent=2, default=str)

    def _build_required_output_text(self) -> str:
        return (
            "{\n"
            '  "active_retrieval_brief": "one compact query-independent Current Working Conversation brief"\n'
            "}\n\n"
            f"Keep active_retrieval_brief at or below about {self.target_brief_tokens} tokens."
        )

    @staticmethod
    def _merge_contributor_ids(
        old_ids: list[str],
        new_ids: list[str],
    ) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        for value in list(old_ids or []) + list(new_ids or []):
            item = str(value or "").strip()
            if not item:
                continue

            if item in seen:
                continue

            result.append(item)
            seen.add(item)

        return result

    @staticmethod
    def _pending_buffer_log_view(buffer: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(buffer, dict) or not buffer:
            return {}

        return {
            "record_id": str(buffer.get("record_id", "") or ""),
            "created_at_utc": str(buffer.get("created_at_utc", "") or ""),
            "question_vector_count": len(buffer.get("question_vectors", []) or []),
            "answer_vector_count": len(buffer.get("answer_vectors", []) or []),
            "vector_count": int(buffer.get("vector_count", 0) or 0),
            "has_center_vector": bool(buffer.get("center_vector", [])),
            "reduced_question_preview": str(buffer.get("reduced_question", "") or "")[:500],
            "reduced_answer_preview": str(buffer.get("reduced_answer", "") or "")[:500],
        }

    @staticmethod
    def _load_runtime_config() -> JsonDict:
        root = Path(__file__).resolve().parents[3]
        path = root / "ragstream" / "config" / "runtime_config.json"

        if not path.exists():
            return {}

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}