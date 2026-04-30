# ragstream/memory/memory_record.py
# -*- coding: utf-8 -*-
"""
MemoryRecord
============
One accepted input/output memory unit.

A MemoryRecord stores:
- raw Prompt input
- accepted output/response
- tag
- automatic YAKE keywords
- optional user keywords
- active project snapshot
- embedded files snapshot
"""

from __future__ import annotations

import hashlib
import json
import uuid

from datetime import datetime, timezone
from typing import Any


RECORD_START = "----- MEMORY RECORD START -----"
RECORD_END = "----- MEMORY RECORD END -----"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _clean_list(values: list[str] | None) -> list[str]:
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

    return cleaned


class MemoryRecord:
    def __init__(
        self,
        input_text: str,
        output_text: str,
        source: str,
        parent_id: str | None = None,
        tag: str = "Green",
        user_keywords: list[str] | None = None,
        active_project_name: str | None = None,
        embedded_files_snapshot: list[str] | None = None,
        *,
        record_id: str | None = None,
        created_at_utc: str | None = None,
        auto_keywords: list[str] | None = None,
        input_hash: str | None = None,
        output_hash: str | None = None,
    ) -> None:
        self.record_id: str = record_id or uuid.uuid4().hex
        self.parent_id: str | None = parent_id
        self.created_at_utc: str = created_at_utc or _utc_now()

        self.input_text: str = input_text or ""
        self.output_text: str = output_text or ""
        self.source: str = source or ""

        self.tag: str = tag or "Green"
        self.user_keywords: list[str] = _clean_list(user_keywords)

        self.active_project_name: str | None = active_project_name
        self.embedded_files_snapshot: list[str] = list(embedded_files_snapshot or [])

        self.input_hash: str = input_hash or _sha256(self.input_text)
        self.output_hash: str = output_hash or _sha256(self.output_text)

        if auto_keywords is None:
            self.auto_keywords: list[str] = self.generate_auto_keywords()
        else:
            self.auto_keywords = _clean_list(auto_keywords)

    def generate_auto_keywords(self) -> list[str]:
        text = f"{self.input_text}\n\n{self.output_text}".strip()
        if not text:
            return []

        try:
            import yake
        except Exception:
            return []

        try:
            extractor = yake.KeywordExtractor(
                lan="en",
                n=3,
                dedupLim=0.9,
                top=5,
                features=None,
            )
            keywords = extractor.extract_keywords(text)
            return _clean_list([kw for kw, _score in keywords])
        except Exception:
            return []

    def update_editable_metadata(
        self,
        tag: str | None = None,
        user_keywords: list[str] | None = None,
    ) -> None:
        if tag is not None:
            clean_tag = str(tag).strip()
            if clean_tag:
                self.tag = clean_tag

        if user_keywords is not None:
            self.user_keywords = _clean_list(user_keywords)

    def to_full_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "parent_id": self.parent_id,
            "created_at_utc": self.created_at_utc,
            "input_text": self.input_text,
            "output_text": self.output_text,
            "source": self.source,
            "tag": self.tag,
            "auto_keywords": self.auto_keywords,
            "user_keywords": self.user_keywords,
            "active_project_name": self.active_project_name,
            "embedded_files_snapshot": self.embedded_files_snapshot,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
        }

    def to_ragmem_block(self) -> str:
        body = json.dumps(self.to_full_dict(), ensure_ascii=False, indent=2)
        return f"{RECORD_START}\n{body}\n{RECORD_END}\n"

    def to_index_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "parent_id": self.parent_id,
            "created_at_utc": self.created_at_utc,
            "source": self.source,
            "tag": self.tag,
            "auto_keywords": self.auto_keywords,
            "user_keywords": self.user_keywords,
            "active_project_name": self.active_project_name,
            "embedded_files_snapshot": self.embedded_files_snapshot,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryRecord":
        return cls(
            input_text=str(data.get("input_text", "")),
            output_text=str(data.get("output_text", "")),
            source=str(data.get("source", "")),
            parent_id=data.get("parent_id"),
            tag=str(data.get("tag", "Green")),
            user_keywords=list(data.get("user_keywords") or []),
            active_project_name=data.get("active_project_name"),
            embedded_files_snapshot=list(data.get("embedded_files_snapshot") or []),
            record_id=str(data.get("record_id") or uuid.uuid4().hex),
            created_at_utc=str(data.get("created_at_utc") or _utc_now()),
            auto_keywords=list(data.get("auto_keywords") or []),
            input_hash=data.get("input_hash"),
            output_hash=data.get("output_hash"),
        )