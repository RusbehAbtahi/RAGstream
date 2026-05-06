# ragstream/retrieval/retriever_mem.py
# -*- coding: utf-8 -*-
"""
MemoryRetriever
===============
Memory Retrieval stage orchestrator.

This file is the retrieval-side entry point for the Memory subsystem.

It reads:
- current SuperPrompt
- current active MemoryManager
- dedicated MemoryVectorStore
- memory_index.sqlite3 through MemoryIndexLookup
- runtime_config["memory_retrieval"]

It writes:
- raw MemoryContextPack into SuperPrompt

It does NOT run:
- A3
- A4
- MemoryMerge
- PromptBuilder
"""

from __future__ import annotations

import json

from pathlib import Path
from typing import Any

from ragstream.memory.memory_context_pack import MemoryContextPack
from ragstream.memory.memory_index_lookup import MemoryIndexLookup
from ragstream.memory.memory_scoring import MemoryScorer
from ragstream.textforge.RagLog import LogALL as logger
from ragstream.textforge.RagLog import LogDeveloper as logger_dev


class MemoryRetriever:
    """
    Main Memory Retrieval orchestrator.

    This class is intentionally thin:
    - vector querying is delegated to MemoryVectorStore / Chroma access
    - SQLite lookup is delegated to MemoryIndexLookup
    - scoring is delegated to MemoryScorer
    - candidate storage is delegated to MemoryContextPack
    """

    def __init__(
        self,
        memory_manager: Any,
        memory_vector_store: Any,
        sqlite_path: str | Path,
        config: dict[str, Any],
    ) -> None:
        self.memory_manager = memory_manager
        self.memory_vector_store = memory_vector_store

        # Accept either the full runtime_config or only runtime_config["memory_retrieval"].
        if "memory_retrieval" in (config or {}):
            self.config = dict(config.get("memory_retrieval", {}) or {})
        else:
            self.config = dict(config or {})

        memory_root = getattr(memory_manager, "memory_root", None)
        self.index_lookup = MemoryIndexLookup(
            sqlite_path=sqlite_path,
            memory_root=memory_root,
        )
        self.scorer = MemoryScorer(self.config)

    def run(
        self,
        sp: Any,
    ) -> Any:
        """
        Run Memory Retrieval for the current SuperPrompt.

        The method mutates and returns the same SuperPrompt object.
        """
        if self.config.get("enabled", True) is False:
            logger("Memory Retrieval skipped: disabled in runtime_config.", "INFO", "INTERNAL")
            return sp

        active_file_id = str(getattr(self.memory_manager, "file_id", "") or "").strip()
        if not active_file_id:
            logger("Memory Retrieval skipped: no active memory file.", "INFO", "INTERNAL")
            return self._write_empty_pack(sp, reason="no_active_memory_file")

        query_text = self._build_query_text(sp)
        if not query_text:
            logger("Memory Retrieval skipped: empty query text.", "WARN", "PUBLIC")
            return self._write_empty_pack(sp, reason="empty_query_text")

        direct_recall_key = self._extract_direct_recall_key(sp)

        logger(
            f"Memory Retrieval started: file={active_file_id[:8]}",
            "INFO",
            "PUBLIC",
        )

        logger_dev(
            (
                "Memory Retrieval input\n"
                f"active_file_id={active_file_id}\n"
                f"memory_title={getattr(self.memory_manager, 'title', '')}\n"
                f"query_text={query_text}\n"
                f"direct_recall_key={direct_recall_key}\n"
                f"config={json.dumps(self.config, ensure_ascii=False, indent=2, default=str)}"
            ),
            "DEBUG",
            "CONFIDENTIAL",
        )

        semantic_result = self._run_semantic_pass(
            query_text=query_text,
            active_file_id=active_file_id,
        )

        index_candidates = self._collect_index_candidates(
            active_file_id=active_file_id,
            direct_recall_key=direct_recall_key,
        )

        pack = self._build_context_pack(
            semantic_chunks=semantic_result["semantic_chunks"],
            episodic_candidates=semantic_result["episodic_candidates"],
            working_candidates=index_candidates["working_memory"],
            direct_recall_candidate=index_candidates["direct_recall"],
            gold_candidates=index_candidates["gold"],
            diagnostics={
                "query_text": query_text,
                "active_file_id": active_file_id,
                "direct_recall_key": direct_recall_key,
                "raw_vector_hit_count": len(semantic_result["raw_hits"]),
                "scored_vector_hit_count": len(semantic_result["scored_hits"]),
                "parent_score_count": len(semantic_result["parent_scores"]),
                "index_counts": {
                    "working_memory": len(index_candidates["working_memory"]),
                    "gold": len(index_candidates["gold"]),
                    "direct_recall": 1 if index_candidates["direct_recall"] else 0,
                },
            },
        )

        self._write_to_superprompt(sp, pack)

        self._log_developer_diagnostics(
            query_text=query_text,
            active_file_id=active_file_id,
            semantic_result=semantic_result,
            index_candidates=index_candidates,
            pack=pack,
        )

        logger(
            (
                "Memory Retrieval finished: "
                f"working={len(pack.working_memory_candidates)}, "
                f"episodic={len(pack.episodic_candidates)}, "
                f"semantic_chunks={len(pack.semantic_memory_chunks)}, "
                f"direct_recall={1 if pack.direct_recall_candidate else 0}"
            ),
            "INFO",
            "PUBLIC",
        )

        return sp

    def _build_query_text(
        self,
        sp: Any,
    ) -> str:
        """
        Build memory retrieval query text from SuperPrompt.

        We intentionally use the same conceptual fields that document retrieval
        already cares about: task, purpose, context, and fallback prompt_ready.
        """
        body = getattr(sp, "body", {}) or {}

        parts: list[str] = []

        for key in ("task", "purpose", "context", "text"):
            value = str(body.get(key, "") or "").strip()
            if value:
                parts.append(value)

        if not parts:
            prompt_ready = str(getattr(sp, "prompt_ready", "") or "").strip()
            if prompt_ready:
                parts.append(prompt_ready)

        return "\n\n".join(parts).strip()

    def _run_semantic_pass(
        self,
        query_text: str,
        active_file_id: str,
    ) -> dict[str, Any]:
        """
        Run memory vector search and parent aggregation.
        """
        semantic_cfg = self.config.get("semantic_memory_chunks", {}) or {}
        if semantic_cfg.get("enabled", True) is False:
            return {
                "raw_hits": [],
                "scored_hits": [],
                "parent_scores": [],
                "semantic_chunks": [],
                "episodic_candidates": [],
            }

        max_memory_chunks = int(semantic_cfg.get("max_memory_chunks", 5))

        # Retrieve more raw hits than final memory chunks because parent scoring
        # needs enough question/answer/handle evidence.
        raw_hit_limit = max(max_memory_chunks * 6, 20)

        raw_hits = self._query_memory_vectors(
            query_text=query_text,
            active_file_id=active_file_id,
            n_results=raw_hit_limit,
        )

        metadata_by_record = self._metadata_by_live_record()
        scored_hits = self.scorer.score_vector_hits(raw_hits)
        parent_scores = self.scorer.aggregate_parent_scores(
            scored_hits=scored_hits,
            metadata_by_record=metadata_by_record,
        )

        semantic_chunks = self.scorer.select_semantic_chunks(
            scored_hits=scored_hits,
            max_memory_chunks=max_memory_chunks,
        )

        episodic_candidates = self._parent_scores_to_episodic_candidates(
            parent_scores=parent_scores,
            active_file_id=active_file_id,
        )

        return {
            "raw_hits": raw_hits,
            "scored_hits": scored_hits,
            "parent_scores": parent_scores,
            "semantic_chunks": semantic_chunks,
            "episodic_candidates": episodic_candidates,
        }

    def _collect_index_candidates(
        self,
        active_file_id: str,
        direct_recall_key: str,
    ) -> dict[str, Any]:
        """
        Collect deterministic non-vector memory candidates.
        """
        working_memory = self.index_lookup.get_working_memory(
            file_id=active_file_id,
            cfg=self.config,
        )

        gold = self.index_lookup.get_latest_gold(
            file_id=active_file_id,
            cfg=self.config,
        )

        direct_recall = self.index_lookup.get_direct_recall(
            direct_recall_key=direct_recall_key,
            cfg=self.config,
        )

        working_memory = self._enrich_candidates_from_live_records(working_memory)
        gold = self._enrich_candidates_from_live_records(gold)

        if direct_recall:
            direct_recall = self._enrich_candidates_from_live_records([direct_recall])[0]

        return {
            "working_memory": working_memory,
            "gold": gold,
            "direct_recall": direct_recall,
        }

    def _build_context_pack(
        self,
        semantic_chunks: list[dict[str, Any]],
        episodic_candidates: list[dict[str, Any]],
        working_candidates: list[dict[str, Any]],
        direct_recall_candidate: dict[str, Any] | None,
        gold_candidates: list[dict[str, Any]],
        diagnostics: dict[str, Any],
    ) -> MemoryContextPack:
        """
        Combine all raw memory candidates into one runtime pack.
        """
        pack = MemoryContextPack()

        for candidate in working_candidates:
            pack.add_working_memory(candidate)

        episodic_final = self._merge_episodic_candidates(
            semantic_episodic=episodic_candidates,
            gold_candidates=gold_candidates,
        )

        for candidate in episodic_final:
            pack.add_episodic_candidate(candidate)

        for candidate in semantic_chunks:
            pack.add_semantic_chunk(candidate)

        pack.set_direct_recall(direct_recall_candidate)

        pack.set_selection_diagnostics(diagnostics)
        pack.set_token_budget_report(self._estimate_token_budget(pack))

        return pack

    def _write_to_superprompt(
        self,
        sp: Any,
        pack: MemoryContextPack,
    ) -> None:
        """
        Store MemoryContextPack into SuperPrompt.

        This keeps raw memory candidates available for GUI and later stages.
        """
        setattr(sp, "memory_context_pack", pack)

        if not hasattr(sp, "extras") or getattr(sp, "extras") is None:
            setattr(sp, "extras", {})

        sp.extras["memory_context_pack"] = pack.to_dict()
        sp.extras["memory_debug_markdown"] = pack.to_debug_markdown()
        sp.extras["memory_retrieval_counts"] = pack.counts()

    def _query_memory_vectors(
        self,
        query_text: str,
        active_file_id: str,
        n_results: int,
    ) -> list[dict[str, Any]]:
        """
        Query the underlying Chroma memory vector collection.

        Current MemoryVectorStore owns the Chroma collection internally.
        This method uses that object without changing the existing store API.
        A later cleanup can move this method into MemoryVectorStore directly.
        """
        collection = getattr(self.memory_vector_store, "_collection", None)
        embedder = getattr(self.memory_vector_store, "embedder", None)

        if collection is None or embedder is None:
            logger("Memory vector search unavailable: store has no collection/embedder.", "WARN", "PUBLIC")
            return []

        query_embedding = self._embed_query(query_text, embedder)

        where = {"file_id": active_file_id} if active_file_id else None

        try:
            result = collection.query(
                query_embeddings=[query_embedding],
                n_results=int(n_results),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as first_error:
            logger(
                f"Memory vector search with file_id filter failed; retrying without filter: {first_error}",
                "WARN",
                "INTERNAL",
            )
            result = collection.query(
                query_embeddings=[query_embedding],
                n_results=int(n_results),
                include=["documents", "metadatas", "distances"],
            )

        raw_hits = self._normalize_chroma_query_result(result)

        logger_dev(
            "Raw memory vector hits\n"
            + json.dumps(raw_hits, ensure_ascii=False, indent=2, default=str),
            "DEBUG",
            "CONFIDENTIAL",
        )

        return raw_hits

    def _embed_query(
        self,
        query_text: str,
        embedder: Any,
    ) -> list[float]:
        """
        Create one dense vector for memory query text.
        """
        vectors = embedder.embed([query_text])
        vector = vectors[0]

        if hasattr(vector, "tolist"):
            vector = vector.tolist()

        return [float(value) for value in vector]

    def _normalize_chroma_query_result(
        self,
        result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Convert Chroma query result shape into a flat list of hit dictionaries.
        """
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

    def _metadata_by_live_record(self) -> dict[str, dict[str, Any]]:
        """
        Build record metadata map from live MemoryManager.records.

        Live records contain body + current metadata after .ragmeta overlay.
        """
        result: dict[str, dict[str, Any]] = {}

        for record in getattr(self.memory_manager, "records", []) or []:
            record_id = str(getattr(record, "record_id", "") or "").strip()
            if not record_id:
                continue

            if hasattr(record, "to_full_dict"):
                result[record_id] = record.to_full_dict()
            elif hasattr(record, "to_index_dict"):
                result[record_id] = record.to_index_dict()
            else:
                result[record_id] = {
                    "record_id": record_id,
                    "tag": getattr(record, "tag", ""),
                    "retrieval_source_mode": getattr(record, "retrieval_source_mode", "QA"),
                }

        return result

    def _parent_scores_to_episodic_candidates(
        self,
        parent_scores: list[dict[str, Any]],
        active_file_id: str,
    ) -> list[dict[str, Any]]:
        """
        Convert ranked parent scores into episodic candidates with Q/A body.
        """
        episodic_cfg = self.config.get("episodic_memory", {}) or {}
        if episodic_cfg.get("enabled", True) is False:
            return []

        max_total_records = int(episodic_cfg.get("max_total_records", 3))
        selected_scores = parent_scores[:max_total_records]

        live_by_id = self._live_records_by_id()
        candidates: list[dict[str, Any]] = []

        for parent in selected_scores:
            record_id = str(parent.get("record_id", "")).strip()
            candidate = dict(parent)

            live_record = live_by_id.get(record_id)
            if live_record is not None:
                candidate.update(self._record_to_candidate(live_record, active_file_id))
            else:
                # Fallback to SQLite/.ragmem if the record is not in live RAM.
                indexed = self.index_lookup.get_records_by_ids(active_file_id, [record_id])
                if indexed:
                    candidate.update(indexed[0])

            candidates.append(candidate)

        candidates = self._enrich_candidates_from_live_records(candidates)

        return candidates

    def _merge_episodic_candidates(
        self,
        semantic_episodic: list[dict[str, Any]],
        gold_candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Merge Gold and semantic episodic candidates without duplicate record_ids.
        """
        episodic_cfg = self.config.get("episodic_memory", {}) or {}
        max_total_records = int(episodic_cfg.get("max_total_records", 3))

        result: list[dict[str, Any]] = []
        seen: set[str] = set()

        for source_name, candidates in (
            ("gold", gold_candidates),
            ("semantic", semantic_episodic),
        ):
            for candidate in candidates:
                record_id = str(candidate.get("record_id", "")).strip()
                if not record_id or record_id in seen:
                    continue

                merged = dict(candidate)
                merged["episodic_source"] = source_name
                result.append(merged)
                seen.add(record_id)

                if len(result) >= max_total_records:
                    return result

        return result

    def _enrich_candidates_from_live_records(
        self,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Overlay live MemoryRecord body/metadata onto candidate dicts when possible.
        """
        live_by_id = self._live_records_by_id()

        enriched: list[dict[str, Any]] = []

        for candidate in candidates:
            record_id = str(candidate.get("record_id", "")).strip()
            live_record = live_by_id.get(record_id)

            if live_record is not None:
                enriched_candidate = dict(candidate)
                enriched_candidate.update(
                    self._record_to_candidate(
                        live_record,
                        file_id=str(candidate.get("file_id", getattr(self.memory_manager, "file_id", ""))),
                    )
                )
                enriched.append(enriched_candidate)
            else:
                enriched.append(candidate)

        return enriched

    def _record_to_candidate(
        self,
        record: Any,
        file_id: str,
    ) -> dict[str, Any]:
        """
        Convert a live MemoryRecord object into a candidate dictionary.
        """
        if hasattr(record, "to_full_dict"):
            data = record.to_full_dict()
        elif hasattr(record, "to_index_dict"):
            data = record.to_index_dict()
            data["input_text"] = getattr(record, "input_text", "")
            data["output_text"] = getattr(record, "output_text", "")
        else:
            data = {
                "record_id": getattr(record, "record_id", ""),
                "input_text": getattr(record, "input_text", ""),
                "output_text": getattr(record, "output_text", ""),
                "tag": getattr(record, "tag", ""),
                "retrieval_source_mode": getattr(record, "retrieval_source_mode", "QA"),
                "direct_recall_key": getattr(record, "direct_recall_key", ""),
            }

        data["file_id"] = file_id
        data["filename_ragmem"] = getattr(self.memory_manager, "filename_ragmem", "")
        data["filename_meta"] = getattr(self.memory_manager, "filename_meta", "")
        data["memory_title"] = getattr(self.memory_manager, "title", "")

        return data

    def _live_records_by_id(self) -> dict[str, Any]:
        result: dict[str, Any] = {}

        for record in getattr(self.memory_manager, "records", []) or []:
            record_id = str(getattr(record, "record_id", "") or "").strip()
            if record_id:
                result[record_id] = record

        return result

    def _extract_direct_recall_key(
        self,
        sp: Any,
    ) -> str:
        """
        Extract an optional Direct Recall Key from SuperPrompt.

        Current GUI does not yet require a separate direct-recall query field.
        This keeps the hook ready without forcing new UI behavior.
        """
        extras = getattr(sp, "extras", {}) or {}
        body = getattr(sp, "body", {}) or {}

        for source in (extras, body):
            for key in ("direct_recall_key", "memory_direct_recall_key"):
                value = str(source.get(key, "") or "").strip()
                if value:
                    return value

        return ""

    def _estimate_token_budget(
        self,
        pack: MemoryContextPack,
    ) -> dict[str, Any]:
        """
        Rough token estimate for diagnostics.

        MemoryMerge later owns exact trimming/compression.
        """
        data = pack.to_dict()
        text = json.dumps(data, ensure_ascii=False, default=str)

        estimated_tokens = max(1, len(text) // 4)

        return {
            "estimated_raw_memory_tokens": estimated_tokens,
            "method": "len(json)//4 rough estimate",
            "limits": {
                "working_memory": self.config.get("working_memory", {}),
                "episodic_memory": self.config.get("episodic_memory", {}),
                "direct_recall": self.config.get("direct_recall", {}),
                "semantic_memory_chunks": self.config.get("semantic_memory_chunks", {}),
            },
        }

    def _write_empty_pack(
        self,
        sp: Any,
        reason: str,
    ) -> Any:
        pack = MemoryContextPack()
        pack.set_selection_diagnostics({"empty_reason": reason})
        self._write_to_superprompt(sp, pack)
        return sp

    def _log_developer_diagnostics(
        self,
        query_text: str,
        active_file_id: str,
        semantic_result: dict[str, Any],
        index_candidates: dict[str, Any],
        pack: MemoryContextPack,
    ) -> None:
        """
        Write a complete retrieval snapshot for later manual analysis.
        """
        payload = {
            "query_text": query_text,
            "active_file_id": active_file_id,
            "memory_manager": {
                "file_id": getattr(self.memory_manager, "file_id", ""),
                "title": getattr(self.memory_manager, "title", ""),
                "filename_ragmem": getattr(self.memory_manager, "filename_ragmem", ""),
                "filename_meta": getattr(self.memory_manager, "filename_meta", ""),
                "record_count": len(getattr(self.memory_manager, "records", []) or []),
            },
            "semantic_result": semantic_result,
            "index_candidates": index_candidates,
            "memory_context_pack": pack.to_dict(),
        }

        logger_dev(
            "FULL MEMORY RETRIEVAL DIAGNOSTIC SNAPSHOT\n"
            + json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            "DEBUG",
            "CONFIDENTIAL",
        )
