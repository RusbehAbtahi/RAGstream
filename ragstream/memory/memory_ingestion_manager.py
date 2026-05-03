# ragstream/memory/memory_ingestion_manager.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import threading

from typing import Any

from ragstream.textforge.RagLog import LogALL as logger


class MemoryIngestionManager:
    def __init__(
        self,
        memory_manager: Any,
        memory_chunker: Any,
        memory_vector_store: Any,
    ) -> None:
        self.memory_manager = memory_manager
        self.memory_chunker = memory_chunker
        self.memory_vector_store = memory_vector_store

        self._lock = threading.Lock()
        self._active_record_ids: set[str] = set()

    def ingest_record(self, record_id: str) -> dict[str, Any]:
        clean_record_id = (record_id or "").strip()
        if not clean_record_id:
            return {
                "success": False,
                "record_id": record_id,
                "message": "record_id is empty.",
            }

        record = self._find_record(clean_record_id)
        if record is None:
            message = f"MemoryRecord not found for ingestion: {clean_record_id}"
            logger(message, "WARN", "PUBLIC")
            return {
                "success": False,
                "record_id": clean_record_id,
                "message": message,
            }

        try:
            logger(
                (
                    "Memory ingestion started: "
                    f"record={clean_record_id[:8]} | file_id={self.memory_manager.file_id[:8]}"
                ),
                "INFO",
                "INTERNAL",
            )

            entries = self.memory_chunker.build_vector_entries(
                record,
                file_id=self.memory_manager.file_id,
                filename_ragmem=self.memory_manager.filename_ragmem,
                filename_meta=self.memory_manager.filename_meta,
            )

            role_counts = self._count_roles(entries)

            logger(
                (
                    "Memory blocks prepared: "
                    f"handle={role_counts.get('record_handle', 0)}, "
                    f"question={role_counts.get('question', 0)}, "
                    f"answer={role_counts.get('answer', 0)}"
                ),
                "INFO",
                "INTERNAL",
            )

            result = self.memory_vector_store.replace_record_entries(
                record_id=clean_record_id,
                entries=entries,
            )

            result.update(
                {
                    "role_counts": role_counts,
                    "file_id": self.memory_manager.file_id,
                    "filename_ragmem": self.memory_manager.filename_ragmem,
                }
            )

            logger(
                (
                    "Memory ingestion finished: "
                    f"{role_counts.get('record_handle', 0)} handle, "
                    f"{role_counts.get('question', 0)} question blocks, "
                    f"{role_counts.get('answer', 0)} answer blocks "
                    f"→ {result.get('vectors_written', 0)} vectors."
                ),
                "INFO",
                "PUBLIC",
            )

            logger(
                (
                    "Memory vector store updated: "
                    f"path={result.get('persist_dir', '')} | "
                    f"collection={result.get('collection_name', '')} | "
                    f"record_vectors={result.get('record_vector_count', 0)}"
                ),
                "INFO",
                "INTERNAL",
            )

            return result

        except Exception as e:
            message = f"Memory ingestion failed for {clean_record_id[:8]}: {e}"
            logger(message, "ERROR", "PUBLIC")
            return {
                "success": False,
                "record_id": clean_record_id,
                "message": message,
            }

    def ingest_all(self) -> dict[str, Any]:
        records = list(getattr(self.memory_manager, "records", []) or [])

        total = len(records)
        success_count = 0
        failure_count = 0
        results: list[dict[str, Any]] = []

        logger(f"Memory ingestion started for loaded history: {total} records.", "INFO", "PUBLIC")

        for record in records:
            result = self.ingest_record(record.record_id)
            results.append(result)

            if result.get("success"):
                success_count += 1
            else:
                failure_count += 1

        logger(
            (
                "Memory history ingestion finished: "
                f"{success_count} succeeded, {failure_count} failed."
            ),
            "INFO" if failure_count == 0 else "WARN",
            "PUBLIC",
        )

        return {
            "success": failure_count == 0,
            "total": total,
            "success_count": success_count,
            "failure_count": failure_count,
            "results": results,
        }

    def ingest_record_async(self, record_id: str) -> None:
        clean_record_id = (record_id or "").strip()
        if not clean_record_id:
            return

        record = self._find_record(clean_record_id)
        if record is None:
            logger(f"Memory ingestion was not scheduled; record not found: {clean_record_id}", "WARN", "PUBLIC")
            return

        with self._lock:
            if clean_record_id in self._active_record_ids:
                logger(
                    f"Memory ingestion already running for record: {clean_record_id[:8]}",
                    "INFO",
                    "INTERNAL",
                )
                return

            self._active_record_ids.add(clean_record_id)

        logger(
            (
                "Memory ingestion scheduled: "
                f"record={clean_record_id[:8]} | "
                f"question_chars={len(record.input_text or '')} | "
                f"answer_chars={len(record.output_text or '')}"
            ),
            "INFO",
            "PUBLIC",
        )

        thread = threading.Thread(
            target=self._async_worker,
            args=(clean_record_id,),
            daemon=True,
            name=f"memory-ingest-{clean_record_id[:8]}",
        )

        try:
            from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

            ctx = get_script_run_ctx()
            if ctx is not None:
                add_script_run_ctx(thread, ctx)
        except Exception:
            pass

        thread.start()

    def _async_worker(self, record_id: str) -> None:
        try:
            self.ingest_record(record_id)
        finally:
            with self._lock:
                self._active_record_ids.discard(record_id)

    def _find_record(self, record_id: str) -> Any | None:
        for record in getattr(self.memory_manager, "records", []) or []:
            if getattr(record, "record_id", None) == record_id:
                return record
        return None

    @staticmethod
    def _count_roles(entries: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}

        for entry in entries:
            metadata = entry.get("metadata", {})
            role = str(metadata.get("role", "")).strip() or "unknown"
            counts[role] = counts.get(role, 0) + 1

        return counts