# controller.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json

from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from ragstream.orchestration.super_prompt import SuperPrompt
from ragstream.preprocessing.prompt_schema import PromptSchema
from ragstream.preprocessing.preprocessing import preprocess

from ragstream.orchestration.agent_factory import AgentFactory
from ragstream.orchestration.llm_client import LLMClient
from ragstream.agents.a2_promptshaper import A2PromptShaper

# Added on 10.03.2026:
# Project-based document ingestion is wired here only at controller level.
from ragstream.ingestion.chunker import Chunker
from ragstream.ingestion.embedder import Embedder
from ragstream.ingestion.ingestion_manager import IngestionManager
from ragstream.ingestion.vector_store_chroma import VectorStoreChroma

# Added on 13.04.2026:
# Parallel SPLADE ingestion branch.
from ragstream.ingestion.splade_embedder import SpladeEmbedder
from ragstream.ingestion.vector_store_splade import VectorStoreSplade

# Added on 15.03.2026:
# Deterministic Retrieval stage.
from ragstream.retrieval.retriever import Retriever
from ragstream.retrieval.reranker import Reranker


class AppController:
    def __init__(self, schema_path: str = "ragstream/config/prompt_schema.json") -> None:
        """
        Central app controller.

        - Loads PromptSchema once (for PreProcessing) from the same path
          you used in your original working version.
        - Creates a shared AgentFactory + LLMClient.
        - Creates the A2PromptShaper agent.
        - Creates the Retrieval stage object.
        """
        # PreProcessing schema (OLD, working behaviour)
        self.schema = PromptSchema(schema_path)

        # Shared AgentFactory (for A2 and, later, other agents)
        self.agent_factory = AgentFactory()

        # Shared LLMClient
        self.llm_client = LLMClient()

        # A2 agent
        self.a2_promptshaper = A2PromptShaper(
            agent_factory=self.agent_factory,
            llm_client=self.llm_client,
        )

        # Added on 10.03.2026:
        # Keep project/document roots centralized in the controller so the GUI
        # stays thin and the ingestion backend continues to receive explicit paths.
        self.project_root = Path(__file__).resolve().parents[2]
        self.data_root = self.project_root / "data"
        self.doc_root = self.data_root / "doc_raw"
        self.chroma_root = self.data_root / "chroma_db"
        self.splade_root = self.data_root / "splade_db"
        self.doc_root.mkdir(parents=True, exist_ok=True)
        self.chroma_root.mkdir(parents=True, exist_ok=True)
        self.splade_root.mkdir(parents=True, exist_ok=True)

        # Added on 15.03.2026:
        # Retrieval is initialized once and re-used. It reads the active project
        # Chroma DB and reconstructs real chunk text from doc_raw.
        self.retriever = Retriever(
            doc_root=str(self.doc_root),
            chroma_root=str(self.chroma_root),
        )

        # Added on 31.03.2026:
        # ReRanker is initialized once and re-used. It consumes the Retrieval
        # candidates already stored in SuperPrompt and reorders them with the
        # agreed cross-encoder model.
        self.reranker = Reranker()

    def preprocess(self, user_text: str, sp: SuperPrompt) -> SuperPrompt:
        """
        Keep EXACTLY the old behaviour:
        - Ignore empty/whitespace-only input.
        - Otherwise run deterministic preprocessing, update sp in place.
        """
        text = (user_text or "").strip()
        if not text:
            return sp
        preprocess(text, sp, self.schema)
        return sp

    def run_a2_promptshaper(self, sp: SuperPrompt) -> SuperPrompt:
        """
        Run A2 on the current SuperPrompt.
        """
        return self.a2_promptshaper.run(sp)

    # Added on 18.03.2026:
    # Small demo helper for the future memory view in the GUI.
    # This does NOT change A2 logic. It only builds one simple input/output
    # record that can be appended by the Streamlit session layer.
    def build_a2_memory_demo_entry(self, sp: SuperPrompt) -> dict[str, str]:
        """
        Build one demo memory entry for the A2 memory view.

        The displayed INPUT contains only the three prompt parts that are
        important for later retrieval-oriented memory usage:
        TASK, PURPOSE, CONTEXT.

        The displayed OUTPUT is intentionally dummy text for the demo phase.
        """
        input_text = self._build_a2_memory_demo_input(sp)
        if not input_text:
            input_text = "(empty)"
        return {
            "input_text": input_text,
            "output_text": "XXXXX",
            "tag": "Green",
        }

    def _build_a2_memory_demo_input(self, sp: SuperPrompt) -> str:
        """
        Build a simple plain-text prompt for the memory demo.

        Design rule:
        - Use the current SuperPrompt body after A2 has shaped it.
        - Keep only TASK / PURPOSE / CONTEXT.
        - Exclude SYSTEM / DEPTH / retrieval context / other fields.
        - Return plain text, not markdown-oriented formatting.
        """
        lines: list[str] = []

        task_value = (sp.body.get("task") or "").strip()
        purpose_value = (sp.body.get("purpose") or "").strip()
        context_value = (sp.body.get("context") or "").strip()

        if task_value:
            lines.append("TASK")
            lines.append(task_value)
            lines.append("")

        if purpose_value:
            lines.append("PURPOSE")
            lines.append(purpose_value)
            lines.append("")

        if context_value:
            lines.append("CONTEXT")
            lines.append(context_value)
            lines.append("")

        return "\n".join(lines).strip()

    # Added on 15.03.2026:
    # Retrieval is a separate deterministic stage and must remain independent
    # from ReRanker / A3. The controller only passes the current SuperPrompt,
    # the active GUI project, and the GUI top-k value.
    def run_retrieval(self, sp: SuperPrompt, project_name: str, top_k: int) -> SuperPrompt:
        """
        Run Retrieval on the current SuperPrompt for the selected active project.

        Inputs:
            sp:
                Current evolving SuperPrompt.
            project_name:
                Active project selected in the GUI.
            top_k:
                Number of chunks to keep after retrieval ranking.

        Returns:
            Updated SuperPrompt after Retrieval has populated:
            - base_context_chunks
            - views_by_stage["retrieval"]
            - final_selection_ids
            - stage / history_of_stages
        """
        project_name = self._normalize_project_name(project_name)
        return self.retriever.run(
            sp=sp,
            project_name=project_name,
            top_k=int(top_k),
        )

    # Added on 31.03.2026:
    # ReRanker is a separate deterministic stage after Retrieval. The controller
    # only passes the current SuperPrompt and returns the same updated object.
    def run_reranker(self, sp: SuperPrompt) -> SuperPrompt:
        """
        Run ReRanker on the current SuperPrompt.

        Inputs:
            sp:
                Current evolving SuperPrompt, typically after Retrieval.

        Returns:
            Updated SuperPrompt after ReRanker has populated:
            - views_by_stage["reranked"]
            - final_selection_ids
            - stage / history_of_stages
        """
        return self.reranker.run(sp)

    # Added on 10.03.2026:
    # Project-based ingestion helpers for the new Streamlit buttons.
    def list_projects(self) -> list[str]:
        doc_projects = {p.name for p in self.doc_root.iterdir() if p.is_dir()}
        chroma_projects = {p.name for p in self.chroma_root.iterdir() if p.is_dir()}
        splade_projects = {p.name for p in self.splade_root.iterdir() if p.is_dir()}
        return sorted(doc_projects | chroma_projects | splade_projects)

    def create_project(self, project_name: str) -> dict[str, Any]:
        project_name = self._normalize_project_name(project_name)
        raw_dir = self.doc_root / project_name
        chroma_dir = self.chroma_root / project_name
        splade_dir = self.splade_root / project_name

        raw_dir.mkdir(parents=True, exist_ok=True)
        chroma_dir.mkdir(parents=True, exist_ok=True)
        splade_dir.mkdir(parents=True, exist_ok=True)

        return {
            "success": True,
            "project_name": project_name,
            "raw_dir": str(raw_dir),
            "chroma_dir": str(chroma_dir),
            "splade_dir": str(splade_dir),
            "manifest_path": str(chroma_dir / "file_manifest.json"),
        }

    def ingest_project(self, project_name: str) -> dict[str, Any]:
        project_name = self._normalize_project_name(project_name)
        paths = self.create_project(project_name)

        # Added on 10.03.2026:
        # The manifest file is standardized per requirement and stored inside
        # the matching Chroma DB project folder.
        manifest_path = Path(paths["manifest_path"])

        manager = IngestionManager(doc_root=str(self.doc_root))
        store = VectorStoreChroma(persist_dir=str(self.chroma_root / project_name))
        sparse_store = VectorStoreSplade(persist_dir=str(self.splade_root / project_name))
        chunker = Chunker()
        embedder = Embedder(model="text-embedding-3-large")
        sparse_embedder = SpladeEmbedder(device="cpu")

        stats = manager.run(
            subfolder=project_name,
            store=store,
            chunker=chunker,
            embedder=embedder,
            sparse_store=sparse_store,
            sparse_embedder=sparse_embedder,
            manifest_path=str(manifest_path),
        )

        result = asdict(stats)
        result.update(
            {
                "success": True,
                "project_name": project_name,
                "raw_dir": str(self.doc_root / project_name),
                "chroma_dir": str(self.chroma_root / project_name),
                "splade_dir": str(self.splade_root / project_name),
                "manifest_path": str(manifest_path),
            }
        )
        return result

    def import_files_to_project(
        self,
        project_name: str,
        *,
        uploaded_files: Iterable[Any] | None = None,
    ) -> dict[str, Any]:
        project_name = self._normalize_project_name(project_name)
        self.create_project(project_name)

        target_dir = self.doc_root / project_name
        allowed_suffixes = {".txt", ".md"}

        copied_files: list[str] = []
        rejected_files: list[str] = []

        # Added on 10.03.2026:
        # Support browser uploads from Streamlit without changing ingestion internals.
        for uploaded in uploaded_files or []:
            filename = Path(getattr(uploaded, "name", "")).name
            if not filename:
                continue
            if Path(filename).suffix.lower() not in allowed_suffixes:
                rejected_files.append(f"{filename}  [only .txt/.md allowed]")
                continue

            dst = target_dir / filename
            with dst.open("wb") as f:
                f.write(uploaded.getbuffer())
            copied_files.append(dst.name)

        if not copied_files:
            return {
                "success": False,
                "project_name": project_name,
                "copied_files": [],
                "copied_count": 0,
                "rejected_files": rejected_files,
                "message": "No valid .txt or .md files were added.",
            }

        ingest_result = self.ingest_project(project_name)
        ingest_result.update(
            {
                "copied_files": copied_files,
                "copied_count": len(copied_files),
                "rejected_files": rejected_files,
            }
        )
        return ingest_result

    # Added on 10.03.2026:
    # Read the standardized project manifest and return the file names that were
    # actually ingested/embedded for the selected project.
    def get_embedded_files(self, project_name: str) -> dict[str, Any]:
        project_name = self._normalize_project_name(project_name)
        manifest_path = self.chroma_root / project_name / "file_manifest.json"

        if not manifest_path.exists():
            return {
                "success": True,
                "project_name": project_name,
                "manifest_path": str(manifest_path),
                "files": [],
            }

        try:
            with manifest_path.open("r", encoding="utf-8") as f:
                manifest_data = json.load(f)

            records: list[dict[str, Any]] = []

            if isinstance(manifest_data, dict):
                manifest_records = manifest_data.get("files")

                if isinstance(manifest_records, list):
                    records = [r for r in manifest_records if isinstance(r, dict)]
                elif isinstance(manifest_records, dict):
                    records = [r for r in manifest_records.values() if isinstance(r, dict)]
                else:
                    # Added on 10.03.2026:
                    # Fallback in case the manifest itself is already a mapping
                    # from file path to metadata record.
                    if all(isinstance(v, dict) for v in manifest_data.values()):
                        records = [r for r in manifest_data.values() if isinstance(r, dict)]

            elif isinstance(manifest_data, list):
                records = [r for r in manifest_data if isinstance(r, dict)]

            file_names: list[str] = []
            for record in records:
                record_path = str(record.get("path", "")).strip()
                if record_path:
                    file_names.append(Path(record_path).name)

            unique_sorted_files = sorted(set(file_names), key=str.lower)

            return {
                "success": True,
                "project_name": project_name,
                "manifest_path": str(manifest_path),
                "files": unique_sorted_files,
            }

        except Exception as e:
            return {
                "success": False,
                "project_name": project_name,
                "manifest_path": str(manifest_path),
                "files": [],
                "message": str(e),
            }

    # Added on 10.03.2026:
    # Small validation/helper methods for project-scoped folder + manifest routing.
    @staticmethod
    def _normalize_project_name(project_name: str) -> str:
        name = (project_name or "").strip()
        if not name:
            raise ValueError("Project name must not be empty.")
        if "/" in name or "\\" in name:
            raise ValueError("Project name must not contain path separators.")
        if name in {".", ".."} or ".." in name:
            raise ValueError("Project name must not contain relative path markers.")
        return name