# ragstream/memory/memory_vector_store.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json

from pathlib import Path
from typing import Any

from ragstream.textforge.RagLog import LogALL as logger


class MemoryVectorStore:
    def __init__(
        self,
        persist_dir: str,
        collection_name: str,
        embedder: Any,
    ) -> None:
        self.persist_dir = str(persist_dir)
        self.collection_name = collection_name
        self.embedder = embedder

        Path(self.persist_dir).mkdir(parents=True, exist_ok=True)

        import chromadb

        self._client = chromadb.PersistentClient(path=self.persist_dir)
        self._collection = self._client.get_or_create_collection(name=self.collection_name)

        logger(
            f"MemoryVectorStore ready: {self.persist_dir} | collection={self.collection_name}",
            "INFO",
            "INTERNAL",
        )

    def replace_record_entries(
        self,
        record_id: str,
        entries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        clean_record_id = (record_id or "").strip()
        if not clean_record_id:
            raise ValueError("record_id must not be empty.")

        old_count = self.count_record(clean_record_id)
        self.delete_record(clean_record_id)

        if not entries:
            return {
                "success": True,
                "record_id": clean_record_id,
                "deleted_old_vectors": old_count,
                "vectors_written": 0,
                "record_vector_count": 0,
                "collection_name": self.collection_name,
                "persist_dir": self.persist_dir,
            }

        ids = [str(entry["id"]) for entry in entries]
        documents = [str(entry.get("document", "")) for entry in entries]
        metadatas = [self._sanitize_metadata(entry.get("metadata", {})) for entry in entries]

        embeddings = self._embed_documents(documents)

        self._collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        new_count = self.count_record(clean_record_id)

        logger(
            (
                "Memory vectors written: "
                f"record={clean_record_id[:8]} | deleted={old_count} | "
                f"new={len(ids)} | total_for_record={new_count}"
            ),
            "INFO",
            "INTERNAL",
        )

        return {
            "success": True,
            "record_id": clean_record_id,
            "deleted_old_vectors": old_count,
            "vectors_written": len(ids),
            "record_vector_count": new_count,
            "collection_name": self.collection_name,
            "persist_dir": self.persist_dir,
        }

    def delete_record(self, record_id: str) -> dict[str, Any]:
        clean_record_id = (record_id or "").strip()
        if not clean_record_id:
            return {
                "success": False,
                "record_id": record_id,
                "deleted_vectors": 0,
                "message": "record_id is empty.",
            }

        old_count = self.count_record(clean_record_id)

        if old_count > 0:
            self._collection.delete(where={"record_id": clean_record_id})

        new_count = self.count_record(clean_record_id)

        return {
            "success": True,
            "record_id": clean_record_id,
            "deleted_vectors": max(old_count - new_count, 0),
            "record_vector_count": new_count,
        }

    def count_record(self, record_id: str) -> int:
        clean_record_id = (record_id or "").strip()
        if not clean_record_id:
            return 0

        try:
            result = self._collection.get(where={"record_id": clean_record_id})
            return len(result.get("ids", []))
        except Exception:
            return 0

    def _embed_documents(self, documents: list[str]) -> list[list[float]]:
        if not documents:
            return []

        vectors = self.embedder.embed(documents)

        result: list[list[float]] = []
        for vector in vectors:
            if hasattr(vector, "tolist"):
                vector = vector.tolist()
            result.append([float(value) for value in vector])

        return result

    @staticmethod
    def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
        clean: dict[str, str | int | float | bool] = {}

        for key, value in (metadata or {}).items():
            clean_key = str(key)

            if value is None:
                clean[clean_key] = ""
            elif isinstance(value, bool):
                clean[clean_key] = value
            elif isinstance(value, int):
                clean[clean_key] = value
            elif isinstance(value, float):
                clean[clean_key] = value
            elif isinstance(value, str):
                clean[clean_key] = value
            else:
                clean[clean_key] = json.dumps(value, ensure_ascii=False, sort_keys=True)

        return clean