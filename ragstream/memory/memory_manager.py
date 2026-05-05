# ragstream/memory/memory_manager.py
# -*- coding: utf-8 -*-
"""
MemoryManager
=============
Owns one active memory history file, its MemoryRecords, MetaInfo,
.ragmem persistence, .ragmeta.json persistence, and SQLite indexing.

Authority split:
- .ragmem is append-only and stores stable memory body fields only.
- .ragmeta.json stores current editable/readable metadata.
- SQLite mirrors .ragmeta.json for fast lookup/indexing.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ragstream.memory.memory_record import (
    MemoryRecord,
    RECORD_END,
    RECORD_START,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _filename_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d-%H-%M")


def _safe_title(title: str) -> str:
    value = (title or "").strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-._")
    return value or "Untitled"


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        item = str(value).strip()
        if not item:
            continue

        key = item.lower()
        if key in seen:
            continue

        result.append(item)
        seen.add(key)

    return result


def _clean_retrieval_source_mode(value: str | None) -> str | None:
    if value is None:
        return None

    mode = str(value or "").strip().upper()
    if mode in {"QA", "Q", "A"}:
        return mode

    return "QA"


def _clean_direct_recall_key(value: str | None) -> str | None:
    if value is None:
        return None

    return str(value or "").strip()


class MemoryManager:
    def __init__(
        self,
        memory_root: Path,
        sqlite_path: Path,
        title: str = "",
    ) -> None:
        self.file_id: str = uuid.uuid4().hex
        self.title: str = ""
        self.filename_ragmem: str = ""
        self.filename_meta: str = ""

        self.memory_root: Path = Path(memory_root)
        self.sqlite_path: Path = Path(sqlite_path)

        self.records: list[MemoryRecord] = []
        self.metainfo: dict[str, Any] = {}

        self.tag_catalog: list[str] = ["Gold", "Green", "Black"]
        self.b_file_created: bool = False

        self.memory_root.mkdir(parents=True, exist_ok=True)
        self.files_root.mkdir(parents=True, exist_ok=True)
        self._init_sqlite()

        if title.strip():
            self.start_new_history(title)

    @property
    def files_root(self) -> Path:
        return self.memory_root / "files"

    @property
    def ragmem_path(self) -> Path:
        return self.files_root / self.filename_ragmem

    @property
    def meta_path(self) -> Path:
        return self.files_root / self.filename_meta

    def start_new_history(self, title: str) -> None:
        clean_title = (title or "").strip()
        if not clean_title:
            raise ValueError("Memory title must not be empty.")

        self.file_id = uuid.uuid4().hex
        self.title = clean_title
        self.records = []
        self.metainfo = {}
        self.b_file_created = False

        stem = f"{_filename_timestamp()}-{_safe_title(clean_title)}"
        filename_ragmem = f"{stem}.ragmem"
        filename_meta = f"{stem}.ragmeta.json"

        if (self.files_root / filename_ragmem).exists():
            stem = f"{stem}-{self.file_id[:8]}"
            filename_ragmem = f"{stem}.ragmem"
            filename_meta = f"{stem}.ragmeta.json"

        self.filename_ragmem = filename_ragmem
        self.filename_meta = filename_meta

    def load_history(self, file_id: str) -> None:
        file_row = self._lookup_file(file_id)
        if not file_row:
            raise ValueError(f"Memory history not found: {file_id}")

        self.file_id = file_row["file_id"]
        self.title = file_row["title"]
        self.filename_ragmem = file_row["filename_ragmem"]
        self.filename_meta = file_row["filename_meta"]

        self.records = self._read_ragmem_records(self.ragmem_path)
        self.b_file_created = self.ragmem_path.exists()

        if self.meta_path.exists():
            with self.meta_path.open("r", encoding="utf-8") as f:
                loaded_meta = json.load(f)
            self.metainfo = loaded_meta if isinstance(loaded_meta, dict) else {}
            self._apply_metainfo_overlay_to_records()
        else:
            self.save_metainfo()

        self.refresh_sqlite_index()

    def list_histories(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT file_id, title, filename_ragmem, filename_meta,
                       created_at_utc, updated_at_utc, record_count
                FROM memory_files
                ORDER BY updated_at_utc DESC
                """
            ).fetchall()

        return [dict(row) for row in rows]

    def capture_pair(
        self,
        input_text: str,
        output_text: str,
        source: str,
        parent_id: str | None = None,
        user_keywords: list[str] | None = None,
        active_project_name: str | None = None,
        embedded_files_snapshot: list[str] | None = None,
    ) -> MemoryRecord:
        if not self.title.strip():
            raise ValueError("Memory title is required before the first memory record is saved.")

        record = MemoryRecord(
            input_text=input_text,
            output_text=output_text,
            source=source,
            parent_id=parent_id,
            tag="Green",
            user_keywords=user_keywords,
            active_project_name=active_project_name,
            embedded_files_snapshot=embedded_files_snapshot,
            retrieval_source_mode="QA",
            direct_recall_key="",
        )

        self.records.append(record)
        self._append_record_to_ragmem(record)
        self.save_metainfo()
        self.refresh_sqlite_index()

        return record

    def sync_gui_edits(
        self,
        gui_records_state: list[dict[str, Any]],
    ) -> None:
        if not gui_records_state:
            return

        records_by_id = {record.record_id: record for record in self.records}
        changed = False

        for item in gui_records_state:
            record_id = str(item.get("record_id", "")).strip()
            if not record_id or record_id not in records_by_id:
                continue

            record = records_by_id[record_id]

            tag = item.get("tag")
            if tag is not None:
                tag = str(tag).strip()
                if tag not in self.tag_catalog:
                    tag = None

            user_keywords = item.get("user_keywords")
            if user_keywords is not None and not isinstance(user_keywords, list):
                user_keywords = []

            retrieval_source_mode = _clean_retrieval_source_mode(item.get("retrieval_source_mode"))
            direct_recall_key = _clean_direct_recall_key(item.get("direct_recall_key"))

            before = record.to_index_dict()
            record.update_editable_metadata(
                tag=tag,
                user_keywords=user_keywords,
                retrieval_source_mode=retrieval_source_mode,
                direct_recall_key=direct_recall_key,
            )
            after = record.to_index_dict()

            if before != after:
                changed = True

        if changed:
            self.save_metainfo()
            self.refresh_sqlite_index()

    def save_metainfo(self) -> None:
        self.metainfo = self._build_metainfo()

        if not self.filename_meta:
            return

        self.files_root.mkdir(parents=True, exist_ok=True)
        with self.meta_path.open("w", encoding="utf-8") as f:
            json.dump(self.metainfo, f, ensure_ascii=False, indent=2)

    def refresh_sqlite_index(self) -> None:
        self._init_sqlite()

        if not self.file_id or not self.filename_ragmem:
            return

        metainfo = self._build_metainfo()
        now = _utc_now()

        created_at_utc = metainfo.get("created_at_utc") or now
        updated_at_utc = metainfo.get("updated_at_utc") or now
        record_count = int(metainfo.get("record_count", 0))

        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute(
                """
                INSERT INTO memory_files (
                    file_id, title, filename_ragmem, filename_meta,
                    created_at_utc, updated_at_utc, record_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_id) DO UPDATE SET
                    title = excluded.title,
                    filename_ragmem = excluded.filename_ragmem,
                    filename_meta = excluded.filename_meta,
                    created_at_utc = excluded.created_at_utc,
                    updated_at_utc = excluded.updated_at_utc,
                    record_count = excluded.record_count
                """,
                (
                    self.file_id,
                    self.title,
                    self.filename_ragmem,
                    self.filename_meta,
                    created_at_utc,
                    updated_at_utc,
                    record_count,
                ),
            )

            for record in self.records:
                index_data = record.to_index_dict()

                conn.execute(
                    """
                    INSERT INTO memory_records (
                        file_id, record_id, parent_id, created_at_utc,
                        source, tag, retrieval_source_mode, direct_recall_key,
                        auto_keywords_json, user_keywords_json,
                        active_project_name, embedded_files_snapshot_json,
                        input_hash, output_hash
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(file_id, record_id) DO UPDATE SET
                        parent_id = excluded.parent_id,
                        created_at_utc = excluded.created_at_utc,
                        source = excluded.source,
                        tag = excluded.tag,
                        retrieval_source_mode = excluded.retrieval_source_mode,
                        direct_recall_key = excluded.direct_recall_key,
                        auto_keywords_json = excluded.auto_keywords_json,
                        user_keywords_json = excluded.user_keywords_json,
                        active_project_name = excluded.active_project_name,
                        embedded_files_snapshot_json = excluded.embedded_files_snapshot_json,
                        input_hash = excluded.input_hash,
                        output_hash = excluded.output_hash
                    """,
                    (
                        self.file_id,
                        index_data["record_id"],
                        index_data["parent_id"],
                        index_data["created_at_utc"],
                        index_data["source"],
                        index_data["tag"],
                        index_data["retrieval_source_mode"],
                        index_data["direct_recall_key"],
                        json.dumps(index_data["auto_keywords"], ensure_ascii=False),
                        json.dumps(index_data["user_keywords"], ensure_ascii=False),
                        index_data["active_project_name"],
                        json.dumps(index_data["embedded_files_snapshot"], ensure_ascii=False),
                        index_data["input_hash"],
                        index_data["output_hash"],
                    ),
                )

            self._delete_sqlite_rows_not_in_memory(conn)
            conn.commit()

    def _build_metainfo(self) -> dict[str, Any]:
        record_ids = [record.record_id for record in self.records]
        parent_ids = _unique([record.parent_id for record in self.records if record.parent_id])

        tag_summary: dict[str, int] = {}
        auto_keywords: list[str] = []
        user_keywords: list[str] = []

        for record in self.records:
            tag_summary[record.tag] = tag_summary.get(record.tag, 0) + 1
            auto_keywords.extend(record.auto_keywords)
            user_keywords.extend(record.user_keywords)

        created_at_utc = self.records[0].created_at_utc if self.records else ""
        updated_at_utc = _utc_now() if self.records else ""

        return {
            "file_id": self.file_id,
            "title": self.title,
            "filename_ragmem": self.filename_ragmem,
            "filename_meta": self.filename_meta,
            "created_at_utc": created_at_utc,
            "updated_at_utc": updated_at_utc,
            "record_count": len(self.records),
            "record_ids": record_ids,
            "parent_ids": parent_ids,
            "tag_summary": tag_summary,
            "auto_keywords": _unique(auto_keywords),
            "user_keywords": _unique(user_keywords),
            "records": [record.to_index_dict() for record in self.records],
        }

    def close(self) -> None:
        self.save_metainfo()
        self.refresh_sqlite_index()

    def _append_record_to_ragmem(self, record: MemoryRecord) -> None:
        if not self.filename_ragmem:
            raise ValueError("Memory filename is not initialized.")

        self.files_root.mkdir(parents=True, exist_ok=True)

        with self.ragmem_path.open("a", encoding="utf-8") as f:
            f.write(record.to_ragmem_block())
            f.write("\n")

        self.b_file_created = True

    def _read_ragmem_records(self, path: Path) -> list[MemoryRecord]:
        if not path.exists():
            return []

        text = path.read_text(encoding="utf-8")
        pattern = re.compile(
            rf"{re.escape(RECORD_START)}\n(.*?)\n{re.escape(RECORD_END)}",
            re.DOTALL,
        )

        records: list[MemoryRecord] = []

        for match in pattern.finditer(text):
            raw_block = match.group(1)
            try:
                data = json.loads(raw_block)
                if isinstance(data, dict):
                    records.append(MemoryRecord.from_dict(data))
            except Exception:
                continue

        return records

    def _apply_metainfo_overlay_to_records(self) -> None:
        """
        Overlay current .ragmeta.json metadata onto records loaded from .ragmem.

        .ragmem supplies the stable body.
        .ragmeta.json supplies current metadata.
        """
        meta_records = self.metainfo.get("records", [])
        if not isinstance(meta_records, list):
            return

        metadata_by_record_id: dict[str, dict[str, Any]] = {}

        for item in meta_records:
            if not isinstance(item, dict):
                continue

            record_id = str(item.get("record_id", "")).strip()
            if not record_id:
                continue

            metadata_by_record_id[record_id] = item

        for record in self.records:
            metadata = metadata_by_record_id.get(record.record_id)
            if metadata is None:
                continue

            record.update_metadata_overlay(metadata)

    def _delete_sqlite_rows_not_in_memory(self, conn: sqlite3.Connection) -> None:
        """
        Keep SQLite as a mirror of the active MemoryManager.records list.
        SQLite is not allowed to keep extra current rows for this file_id.
        """
        if not self.records:
            conn.execute(
                "DELETE FROM memory_records WHERE file_id = ?",
                (self.file_id,),
            )
            return

        record_ids = [record.record_id for record in self.records]
        placeholders = ",".join("?" for _ in record_ids)

        conn.execute(
            f"""
            DELETE FROM memory_records
            WHERE file_id = ?
              AND record_id NOT IN ({placeholders})
            """,
            [self.file_id, *record_ids],
        )

    def _lookup_file(self, file_id: str) -> dict[str, Any] | None:
        self._init_sqlite()

        with sqlite3.connect(self.sqlite_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT file_id, title, filename_ragmem, filename_meta,
                       created_at_utc, updated_at_utc, record_count
                FROM memory_files
                WHERE file_id = ?
                """,
                (file_id,),
            ).fetchone()

        return dict(row) if row else None

    def _init_sqlite(self) -> None:
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_files (
                    file_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    filename_ragmem TEXT NOT NULL,
                    filename_meta TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    record_count INTEGER NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_records (
                    file_id TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    parent_id TEXT,
                    created_at_utc TEXT NOT NULL,
                    source TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    retrieval_source_mode TEXT NOT NULL DEFAULT 'QA',
                    direct_recall_key TEXT NOT NULL DEFAULT '',
                    auto_keywords_json TEXT NOT NULL,
                    user_keywords_json TEXT NOT NULL,
                    active_project_name TEXT,
                    embedded_files_snapshot_json TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    output_hash TEXT NOT NULL,
                    PRIMARY KEY (file_id, record_id)
                )
                """
            )

            self._ensure_memory_records_columns(conn)

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_records_tag
                ON memory_records(tag)
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_records_project
                ON memory_records(active_project_name)
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_records_direct_recall_key
                ON memory_records(direct_recall_key)
                """
            )

            conn.commit()

    @staticmethod
    def _ensure_memory_records_columns(conn: sqlite3.Connection) -> None:
        rows = conn.execute("PRAGMA table_info(memory_records)").fetchall()
        existing_columns = {str(row[1]) for row in rows}

        if "retrieval_source_mode" not in existing_columns:
            conn.execute(
                "ALTER TABLE memory_records "
                "ADD COLUMN retrieval_source_mode TEXT NOT NULL DEFAULT 'QA'"
            )

        if "direct_recall_key" not in existing_columns:
            conn.execute(
                "ALTER TABLE memory_records "
                "ADD COLUMN direct_recall_key TEXT NOT NULL DEFAULT ''"
            )