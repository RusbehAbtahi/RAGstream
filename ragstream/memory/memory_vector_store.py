# ragstream/memory/memory_vector_store.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json

from pathlib import Path
from typing import Any

from ragstream.textforge.RagLog import LogALL as logger
from ragstream.textforge.RagLog import LogDeveloper as logger_dev


class MemoryVectorStore:
    """
    Dedicated memory Chroma vector store.

    This store is separate from document Chroma stores.

    It owns:
    - memory vector persistence
    - record vector replacement
    - record vector deletion
    - file/history vector deletion by file_id
    - raw vector search for MemoryRetriever

    It does not own:
    - MemoryRecord truth
    - SQLite metadata truth
    - memory scoring
    - MemoryContextPack creation
    """

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

        logger_dev(
            (
                "MemoryVectorStore.replace_record_entries\n"
                f"record_id={clean_record_id}\n"
                f"ids={json.dumps(ids, ensure_ascii=False, indent=2)}\n"
                f"metadatas={json.dumps(metadatas, ensure_ascii=False, indent=2, default=str)}"
            ),
            "DEBUG",
            "CONFIDENTIAL",
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

    def query(
        self,
        query_text: str,
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search memory vectors and return flat hit dictionaries.

        Returned hit format:
        {
            "id": str,
            "document": str,
            "metadata": dict,
            "distance": float | None,
            "rank": int
        }
        """
        text = str(query_text or "").strip()
        if not text:
            return []

        query_embedding = self._embed_documents([text])[0]

        query_kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": int(n_results),
            "include": ["documents", "metadatas", "distances"],
        }

        if where:
            query_kwargs["where"] = self._sanitize_where(where)

        result = self._collection.query(**query_kwargs)
        hits = self._normalize_query_result(result)

        logger(
            f"MemoryVectorStore query finished: hits={len(hits)}",
            "INFO",
            "INTERNAL",
        )

        logger_dev(
            (
                "MemoryVectorStore.query\n"
                f"query_text={text}\n"
                f"n_results={n_results}\n"
                f"where={json.dumps(where or {}, ensure_ascii=False, indent=2, default=str)}\n"
                f"hits={json.dumps(hits, ensure_ascii=False, indent=2, default=str)}"
            ),
            "DEBUG",
            "CONFIDENTIAL",
        )

        return hits

    def delete_record(self, record_id: str) -> dict[str, Any]:
        """Delete all memory vectors belonging to one MemoryRecord."""
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

        deleted_vectors = max(old_count - new_count, 0)

        logger_dev(
            (
                "MemoryVectorStore.delete_record\n"
                f"record_id={clean_record_id}\n"
                f"old_count={old_count}\n"
                f"new_count={new_count}\n"
                f"deleted_vectors={deleted_vectors}"
            ),
            "DEBUG",
            "CONFIDENTIAL",
        )

        return {
            "success": True,
            "record_id": clean_record_id,
            "deleted_vectors": deleted_vectors,
            "record_vector_count": new_count,
        }

    def delete_file(self, file_id: str) -> dict[str, Any]:
        """
        Delete all memory vectors belonging to one memory history.

        This is used by FILES tab Delete.
        """
        clean_file_id = (file_id or "").strip()
        if not clean_file_id:
            return {
                "success": False,
                "file_id": file_id,
                "deleted_vectors": 0,
                "message": "file_id is empty.",
            }

        old_count = self.count_file(clean_file_id)

        if old_count > 0:
            self._collection.delete(where={"file_id": clean_file_id})

        new_count = self.count_file(clean_file_id)
        deleted_vectors = max(old_count - new_count, 0)

        logger(
            (
                "Memory vectors deleted by file_id: "
                f"file={clean_file_id[:8]} | deleted={deleted_vectors}"
            ),
            "INFO",
            "INTERNAL",
        )

        logger_dev(
            (
                "MemoryVectorStore.delete_file\n"
                f"file_id={clean_file_id}\n"
                f"old_count={old_count}\n"
                f"new_count={new_count}\n"
                f"deleted_vectors={deleted_vectors}"
            ),
            "DEBUG",
            "CONFIDENTIAL",
        )

        return {
            "success": True,
            "file_id": clean_file_id,
            "deleted_vectors": deleted_vectors,
            "file_vector_count": new_count,
            "collection_name": self.collection_name,
            "persist_dir": self.persist_dir,
        }

    def count_record(self, record_id: str) -> int:
        """Count vectors belonging to one MemoryRecord."""
        clean_record_id = (record_id or "").strip()
        if not clean_record_id:
            return 0

        try:
            result = self._collection.get(where={"record_id": clean_record_id})
            return len(result.get("ids", []))
        except Exception:
            return 0

    def count_file(self, file_id: str) -> int:
        """Count vectors belonging to one memory history."""
        clean_file_id = (file_id or "").strip()
        if not clean_file_id:
            return 0

        try:
            result = self._collection.get(where={"file_id": clean_file_id})
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
    def _normalize_query_result(result: dict[str, Any]) -> list[dict[str, Any]]:
        ids = (result.get("ids") or [[]])[0] or []
        documents = (result.get("documents") or [[]])[0] or []
        metadatas = (result.get("metadatas") or [[]])[0] or []
        distances = (result.get("distances") or [[]])[0] or []

        hits: list[dict[str, Any]] = []

        for idx, vector_id in enumerate(ids):
            metadata = metadatas[idx] if idx < len(metadatas) and metadatas[idx] else {}
            document = documents[idx] if idx < len(documents) else ""
            distance = distances[idx] if idx < len(distances) else None

            hits.append(
                {
                    "id": vector_id,
                    "document": document,
                    "metadata": metadata,
                    "distance": distance,
                    "rank": idx + 1,
                }
            )

        return hits

    @staticmethod
    def _sanitize_where(where: dict[str, Any]) -> dict[str, str | int | float | bool]:
        clean: dict[str, str | int | float | bool] = {}

        for key, value in (where or {}).items():
            if value is None:
                continue

            clean_key = str(key)

            if isinstance(value, bool):
                clean[clean_key] = value
            elif isinstance(value, int):
                clean[clean_key] = value
            elif isinstance(value, float):
                clean[clean_key] = value
            else:
                clean[clean_key] = str(value)

        return clean

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