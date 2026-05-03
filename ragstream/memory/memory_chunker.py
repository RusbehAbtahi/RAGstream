# ragstream/memory/memory_chunker.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import re

from typing import Any


class MemoryChunker:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config: dict[str, Any] = {
            "config_version": "memory_chunker_001",
            "target_tokens": 500,
            "max_tokens": 800,
            "question_anchor_tokens": 220,
        }
        self.config.update(config or {})

    def build_vector_entries(
        self,
        record: Any,
        *,
        file_id: str,
        filename_ragmem: str = "",
        filename_meta: str = "",
    ) -> list[dict[str, Any]]:
        ingestion_hash = self._build_ingestion_hash(record, file_id)

        entries: list[dict[str, Any]] = []

        question_anchor = self._build_question_anchor(record.input_text)
        record_handle_text = self._build_record_handle_text(record, question_anchor)

        entries.append(
            self._make_entry(
                file_id=file_id,
                filename_ragmem=filename_ragmem,
                filename_meta=filename_meta,
                record=record,
                role="record_handle",
                block_id="0000",
                position=0,
                text=record_handle_text,
                start_offset=0,
                end_offset=len(question_anchor),
                ingestion_hash=ingestion_hash,
            )
        )

        for position, block in enumerate(self._split_text(record.input_text), start=1):
            entries.append(
                self._make_entry(
                    file_id=file_id,
                    filename_ragmem=filename_ragmem,
                    filename_meta=filename_meta,
                    record=record,
                    role="question",
                    block_id=f"{position:04d}",
                    position=position,
                    text=block["text"],
                    start_offset=block["start_offset"],
                    end_offset=block["end_offset"],
                    ingestion_hash=ingestion_hash,
                )
            )

        for position, block in enumerate(self._split_text(record.output_text), start=1):
            entries.append(
                self._make_entry(
                    file_id=file_id,
                    filename_ragmem=filename_ragmem,
                    filename_meta=filename_meta,
                    record=record,
                    role="answer",
                    block_id=f"{position:04d}",
                    position=position,
                    text=block["text"],
                    start_offset=block["start_offset"],
                    end_offset=block["end_offset"],
                    ingestion_hash=ingestion_hash,
                )
            )

        return [entry for entry in entries if entry["document"].strip()]

    def _build_record_handle_text(self, record: Any, question_anchor: str) -> str:
        return "\n".join(
            [
                f"PROJECT: {record.active_project_name or ''}",
                f"TAG: {record.tag or ''}",
                f"USER_KEYWORDS: {self._join_list(record.user_keywords)}",
                f"YAKE_KEYWORDS: {self._join_list(record.auto_keywords)}",
                "QUESTION_ANCHOR:",
                question_anchor.strip(),
            ]
        ).strip()

    def _build_question_anchor(self, text: str) -> str:
        clean_text = (text or "").strip()
        if not clean_text:
            return ""

        max_tokens = int(self.config["question_anchor_tokens"])
        blocks = self._split_text(clean_text)

        if blocks:
            return self._truncate_by_tokens(blocks[0]["text"], max_tokens)

        return self._truncate_by_tokens(clean_text, max_tokens)

    def _split_text(self, text: str) -> list[dict[str, Any]]:
        if not (text or "").strip():
            return []

        target_tokens = int(self.config["target_tokens"])
        max_tokens = int(self.config["max_tokens"])

        units = self._semantic_units(text)
        blocks: list[dict[str, Any]] = []

        current_units: list[tuple[int, int, str]] = []
        current_tokens = 0

        for start, end, unit_text in units:
            unit_tokens = self._count_tokens(unit_text)

            if unit_tokens > max_tokens:
                if current_units:
                    blocks.append(self._units_to_block(current_units))
                    current_units = []
                    current_tokens = 0

                blocks.extend(self._hard_split(unit_text, base_offset=start, max_tokens=max_tokens))
                continue

            if current_units and current_tokens + unit_tokens > max_tokens:
                blocks.append(self._units_to_block(current_units))
                current_units = []
                current_tokens = 0

            current_units.append((start, end, unit_text))
            current_tokens += unit_tokens

            if current_tokens >= target_tokens:
                blocks.append(self._units_to_block(current_units))
                current_units = []
                current_tokens = 0

        if current_units:
            blocks.append(self._units_to_block(current_units))

        return blocks

    def _semantic_units(self, text: str) -> list[tuple[int, int, str]]:
        units: list[tuple[int, int, str]] = []

        paragraph_pattern = re.compile(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", re.DOTALL)

        for paragraph_match in paragraph_pattern.finditer(text):
            paragraph_text = paragraph_match.group(0)
            paragraph_start = paragraph_match.start()
            paragraph_end = paragraph_match.end()

            if self._count_tokens(paragraph_text) <= int(self.config["max_tokens"]):
                units.append((paragraph_start, paragraph_end, paragraph_text))
                continue

            sentence_pattern = re.compile(r"\S[^.!?\n]*(?:[.!?]+|$)", re.DOTALL)

            for sentence_match in sentence_pattern.finditer(paragraph_text):
                sentence_text = sentence_match.group(0).strip()
                if not sentence_text:
                    continue

                start = paragraph_start + sentence_match.start()
                end = paragraph_start + sentence_match.end()
                units.append((start, end, text[start:end]))

        if not units and text.strip():
            units.append((0, len(text), text.strip()))

        return units

    def _hard_split(
        self,
        text: str,
        *,
        base_offset: int,
        max_tokens: int,
    ) -> list[dict[str, Any]]:
        word_matches = list(re.finditer(r"\S+", text))
        blocks: list[dict[str, Any]] = []

        for i in range(0, len(word_matches), max_tokens):
            group = word_matches[i : i + max_tokens]
            if not group:
                continue

            start = base_offset + group[0].start()
            end = base_offset + group[-1].end()
            block_text = text[group[0].start() : group[-1].end()]

            blocks.append(
                {
                    "text": block_text,
                    "start_offset": start,
                    "end_offset": end,
                    "token_count": self._count_tokens(block_text),
                }
            )

        return blocks

    @staticmethod
    def _units_to_block(units: list[tuple[int, int, str]]) -> dict[str, Any]:
        start = units[0][0]
        end = units[-1][1]
        text = "\n\n".join(unit[2].strip() for unit in units if unit[2].strip())

        return {
            "text": text,
            "start_offset": start,
            "end_offset": end,
            "token_count": MemoryChunker._count_tokens(text),
        }

    def _make_entry(
        self,
        *,
        file_id: str,
        filename_ragmem: str,
        filename_meta: str,
        record: Any,
        role: str,
        block_id: str,
        position: int,
        text: str,
        start_offset: int,
        end_offset: int,
        ingestion_hash: str,
    ) -> dict[str, Any]:
        metadata = {
            "file_id": file_id or "",
            "filename_ragmem": filename_ragmem or "",
            "filename_meta": filename_meta or "",
            "record_id": record.record_id or "",
            "parent_id": record.parent_id or "",
            "role": role,
            "block_id": block_id,
            "position": int(position),
            "start_offset": int(start_offset),
            "end_offset": int(end_offset),
            "token_count": int(self._count_tokens(text)),
            "tag": record.tag or "",
            "active_project_name": record.active_project_name or "",
            "source": record.source or "",
            "created_at_utc": record.created_at_utc or "",
            "input_hash": record.input_hash or "",
            "output_hash": record.output_hash or "",
            "auto_keywords_text": self._join_list(record.auto_keywords),
            "yake_keywords_text": self._join_list(record.auto_keywords),
            "user_keywords_text": self._join_list(record.user_keywords),
            "embedded_files_snapshot_text": self._join_list(record.embedded_files_snapshot),
            "chunking_config_version": str(self.config["config_version"]),
            "ingestion_hash": ingestion_hash,
        }

        return {
            "id": f"mem::{file_id}::{record.record_id}::{role}::{block_id}",
            "document": text or "",
            "metadata": metadata,
        }

    def _build_ingestion_hash(self, record: Any, file_id: str) -> str:
        payload = {
            "file_id": file_id,
            "record_id": record.record_id,
            "input_hash": record.input_hash,
            "output_hash": record.output_hash,
            "tag": record.tag,
            "auto_keywords": list(record.auto_keywords or []),
            "user_keywords": list(record.user_keywords or []),
            "active_project_name": record.active_project_name,
            "chunking_config_version": self.config["config_version"],
        }

        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _truncate_by_tokens(text: str, max_tokens: int) -> str:
        words = re.findall(r"\S+", text or "")
        if len(words) <= max_tokens:
            return (text or "").strip()
        return " ".join(words[:max_tokens]).strip()

    @staticmethod
    def _count_tokens(text: str) -> int:
        return len(re.findall(r"\S+", text or ""))

    @staticmethod
    def _join_list(values: list[str] | None) -> str:
        cleaned: list[str] = []
        seen: set[str] = set()

        for value in values or []:
            item = str(value).strip()
            if not item:
                continue

            key = item.lower()
            if key in seen:
                continue

            cleaned.append(item)
            seen.add(key)

        return "; ".join(cleaned)