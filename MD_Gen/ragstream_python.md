# Python Files Index (ragstream)

## /home/rusbeh_ab/project/RAGstream/ragstream/app

### ~\ragstream\app\agents.py
```python
"""
Agents (A1..A4)
===============
- A1 Deterministic Code Injector → builds ❖ FILES and enforces Exact File Lock.
- A2 Prompt Shaper → pass-1 propose headers; audit-2 may trigger one retrieval re-run on scope change.
- A3 NLI Gate → keep/drop via entailment (θ strictness).
- A4 Condenser → emits S_ctx (Facts / Constraints / Open Issues) with citations.
"""
from typing import List, Dict

class A1_DCI:
    def build_files_block(self, named_files: List[str], lock: bool) -> str:
        return "❖ FILES\n"

class A2_PromptShaper:
    def propose(self, question: str) -> Dict[str, str]:
        return {"intent": "explain", "domain": "software", "headers": "H"}
    def audit_and_rerun(self, shape: Dict[str, str], s_ctx: List[str]) -> bool:
        """
        Return True iff audit materially changes task scope (intent/domain),
        allowing exactly one retrieval→A3→A4 re-run.
        """
        return False

class A3_NLIGate:
    def __init__(self, theta: float = 0.6) -> None:
        self.theta = theta
    def filter(self, candidates: List[str], question: str) -> List[str]:
        return candidates

class A4_Condenser:
    def condense(self, kept: List[str]) -> List[str]:
        return ["Facts:", "Constraints:", "Open Issues:"]
```

### ~\ragstream\app\controller.py
```python
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
# The existing ingestion backend remains unchanged.
from ragstream.ingestion.chunker import Chunker
from ragstream.ingestion.embedder import Embedder
from ragstream.ingestion.ingestion_manager import IngestionManager
from ragstream.ingestion.vector_store_chroma import VectorStoreChroma

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
        self.doc_root.mkdir(parents=True, exist_ok=True)
        self.chroma_root.mkdir(parents=True, exist_ok=True)

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
        return sorted(doc_projects | chroma_projects)

    def create_project(self, project_name: str) -> dict[str, Any]:
        project_name = self._normalize_project_name(project_name)
        raw_dir = self.doc_root / project_name
        chroma_dir = self.chroma_root / project_name

        raw_dir.mkdir(parents=True, exist_ok=True)
        chroma_dir.mkdir(parents=True, exist_ok=True)

        return {
            "success": True,
            "project_name": project_name,
            "raw_dir": str(raw_dir),
            "chroma_dir": str(chroma_dir),
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
        chunker = Chunker()
        embedder = Embedder(model="text-embedding-3-large")

        stats = manager.run(
            subfolder=project_name,
            store=store,
            chunker=chunker,
            embedder=embedder,
            manifest_path=str(manifest_path),
        )

        result = asdict(stats)
        result.update(
            {
                "success": True,
                "project_name": project_name,
                "raw_dir": str(self.doc_root / project_name),
                "chroma_dir": str(self.chroma_root / project_name),
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
```

### ~\ragstream\app\controller_legacy.py
```python
"""
AppController
=============
Controller orchestrates A1..A4 with ConversationMemory and the retrieval path.
- Exact File Lock short-circuits retrieval.
- A2 runs twice (propose → audit); at most one retrieval re-run on scope change.
"""
from typing import List
from ragstream.retrieval.retriever import Retriever, DocScore
from ragstream.retrieval.reranker import Reranker
from ragstream.orchestration.prompt_builder import PromptBuilder
from ragstream.orchestration.llm_client import LLMClient
from ragstream.app.agents import A1_DCI, A2_PromptShaper, A3_NLIGate, A4_Condenser
from ragstream.memory.conversation_memory import ConversationMemory

class AppController:
    def __init__(self) -> None:
        self.retriever = Retriever()
        self.reranker = Reranker()
        self.prompt_builder = PromptBuilder()
        self.llm_client = LLMClient()
        self.a1 = A1_DCI()
        self.a2 = A2_PromptShaper()
        self.a3 = A3_NLIGate()
        self.a4 = A4_Condenser()
        self.convmem = ConversationMemory()
        self.eligibility_pool = set()  # ON/OFF file gating handled by UI/controller

    def handle(self, user_prompt: str, named_files: List[str], exact_lock: bool) -> str:
        # A2 pass-1
        _shape = self.a2.propose(user_prompt)

        # A1 — ❖ FILES
        files_block = self.a1.build_files_block(named_files, exact_lock)

        # Retrieval path (skip if lock)
        kept_chunks: List[str] = []
        if not exact_lock:
            results: List[DocScore] = self.retriever.retrieve(user_prompt, k=10)
            ids = [r.id for r in results]
            kept_chunks = self.a3.filter(ids, user_prompt)

        # A4 — condense to S_ctx
        s_ctx = self.a4.condense(kept_chunks)

        # A2 audit-2 (may trigger one re-run on scope change)
        if self.a2.audit_and_rerun(_shape, s_ctx) and not exact_lock:
            results = self.retriever.retrieve(user_prompt, k=10)
            ids = [r.id for r in results]
            kept_chunks = self.a3.filter(ids, user_prompt)
            s_ctx = self.a4.condense(kept_chunks)

        # Compose & send
        prompt = self.prompt_builder.build(user_prompt, files_block, s_ctx, shape=_shape)
        return self.llm_client.complete(prompt)
```

### ~\ragstream\app\ui_streamlit.py
```python
# ui_streamlit.py
# -*- coding: utf-8 -*-
"""
Run on a free port, e.g.:
  /home/rusbeh_ab/venvs/ragstream/bin/python -m streamlit run /home/rusbeh_ab/project/RAGstream/ragstream/app/ui_streamlit.py --server.port 8503
"""

from __future__ import annotations
import copy
import html

import streamlit as st

from ragstream.app.controller import AppController
from ragstream.orchestration.super_prompt import SuperPrompt


def main() -> None:
    st.set_page_config(page_title="RAGstream", layout="wide")

    st.markdown(
        """
        <style>
            /* Hide Streamlit header/toolbar to reduce top gap */
            header {visibility: hidden;}
            div[data-testid="stHeader"] {display: none;}
            div[data-testid="stToolbar"] {display: none;}

            /* Tighten page paddings to push content up/left */
            .block-container {
                padding-top: 0.2rem;
                padding-bottom: 0rem;
                padding-left: 0.6rem;
                padding-right: 0.6rem;
            }

            /* Big, bold custom field titles */
            .field-title {
                font-size: 1.8rem;
                font-weight: 800;
                line-height: 1.2;
                margin-bottom: 0.35rem;
            }

            /* Make the row gaps compact */
            div[data-testid="stHorizontalBlock"]{
                gap: 0.4rem !important;
            }

            .memory-box {
                border-radius: 0.45rem;
                padding: 0.55rem 0.7rem;
                border: 1px solid #d8d8d8;
                font-size: 0.95rem;
                line-height: 1.35;
                white-space: normal;
                word-break: break-word;
            }

            .memory-input-box {
                background-color: #ffffff;
            }

            .memory-output-box {
                background-color: #f3f4f6;
            }

            .memory-label {
                font-size: 0.82rem;
                font-weight: 700;
                margin-bottom: 0.25rem;
                color: #4b5563;
                letter-spacing: 0.02em;
            }

            .memory-plain-text {
                white-space: pre-wrap;
                font-size: 0.95rem;
                line-height: 1.35;
                margin: 0;
                font-family: inherit;
            }

            /* Make small select boxes look compact */
            div[data-baseweb="select"] > div {
                min-height: 34px;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("RAGstream")

    # one controller + one SuperPrompt per user session
    if "controller" not in st.session_state:
        st.session_state.controller = AppController()
    if "sp" not in st.session_state:
        st.session_state.sp = SuperPrompt()
    if "sp_pre" not in st.session_state:
        st.session_state.sp_pre = SuperPrompt()
    if "sp_a2" not in st.session_state:
        st.session_state.sp_a2 = SuperPrompt()
    if "sp_rtv" not in st.session_state:
        st.session_state.sp_rtv = SuperPrompt()
    if "sp_rrk" not in st.session_state:
        st.session_state.sp_rrk = SuperPrompt()
    if "super_prompt_text" not in st.session_state:
        st.session_state["super_prompt_text"] = ""
    if "ingestion_status" not in st.session_state:
        st.session_state["ingestion_status"] = None
    if "new_project_name" not in st.session_state:
        st.session_state["new_project_name"] = ""
    if "pending_active_project" not in st.session_state:
        # Temporary project switch key. We use this instead of modifying
        # the widget-owned key "active_project" after that widget exists.
        st.session_state["pending_active_project"] = None
    if "retrieval_top_k" not in st.session_state:
        st.session_state["retrieval_top_k"] = 100
    if "a2_memory_demo_entries" not in st.session_state:
        st.session_state["a2_memory_demo_entries"] = []
    if "a2_memory_demo_counter" not in st.session_state:
        st.session_state["a2_memory_demo_counter"] = 0

    # Layout: gutters left/right, two main columns, small spacer between
    gutter_l, col_left, spacer, col_right, gutter_r = st.columns([0.6, 4, 0.25, 4, 0.6], gap="small")

    with gutter_l:
        st.empty()

    # LEFT: Memory Demo + Prompt + two rows of pipeline buttons
    with col_left:
        st.markdown('<div class="field-title">MEMORY DEMO</div>', unsafe_allow_html=True)

        memory_entries = st.session_state["a2_memory_demo_entries"]

        try:
            memory_container = st.container(height=780)
        except TypeError:
            memory_container = st.container()

        with memory_container:
            if not memory_entries:
                st.info("No memory entries yet.")
            else:
                for entry in memory_entries:
                    entry_id = entry["id"]
                    tag_key = f"a2_memory_tag_{entry_id}"

                    if tag_key not in st.session_state:
                        st.session_state[tag_key] = entry.get("tag", "Green")

                    input_col, tag_col = st.columns([8.8, 1.0], gap="small")

                    with input_col:
                        input_html = html.escape(entry.get("input_text", "")).replace("\n", "<br>")
                        st.markdown(
                            f"""
                            <div class="memory-box memory-input-box">
                                <div class="memory-label">INPUT</div>
                                <div class="memory-plain-text">{input_html}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    with tag_col:
                        selected_tag = st.selectbox(
                            "Tag",
                            options=["Platin", "GOLD", "SILVER", "Green", "Black"],
                            key=tag_key,
                            index=["Platin", "GOLD", "SILVER", "Green", "Black"].index(
                                st.session_state[tag_key]
                            ),
                            label_visibility="collapsed",
                        )
                        entry["tag"] = selected_tag

                    output_html = html.escape(entry.get("output_text", "")).replace("\n", "<br>")
                    st.markdown(
                        f"""
                        <div class="memory-box memory-output-box">
                            <div class="memory-label">OUTPUT</div>
                            <div class="memory-plain-text">{output_html}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.markdown("<div style='height:0.40rem'></div>", unsafe_allow_html=True)

        st.markdown("<div style='height:0.45rem'></div>", unsafe_allow_html=True)

        st.markdown('<div class="field-title">Prompt</div>', unsafe_allow_html=True)
        st.text_area(
            label="Prompt (hidden)",
            key="prompt_text",
            height=240,
            label_visibility="collapsed",
        )

        # Small vertical spacer
        st.markdown("<div style='height:0.35rem'></div>", unsafe_allow_html=True)

        # Row 1: 4 buttons
        b1c1, b1c2, b1c3, b1c4 = st.columns(4, gap="small")
        with b1c1:
            clicked = st.button("Pre-Processing", key="btn_preproc", use_container_width=True)
            if clicked:
                ctrl: AppController = st.session_state.controller
                sp: SuperPrompt = st.session_state.sp
                user_text = st.session_state.get("prompt_text", "")
                sp = ctrl.preprocess(user_text, sp)
                st.session_state.sp = sp
                st.session_state.sp_pre = copy.deepcopy(sp)
                st.session_state["super_prompt_text"] = sp.prompt_ready

        with b1c2:
            clicked_a2 = st.button("A2-PromptShaper", key="btn_a2", use_container_width=True)
            if clicked_a2:
                ctrl: AppController = st.session_state.controller
                sp: SuperPrompt = st.session_state.sp

                sp = ctrl.run_a2_promptshaper(sp)
                entry = ctrl.build_a2_memory_demo_entry(sp)

                next_id = st.session_state.get("a2_memory_demo_counter", 0) + 1
                st.session_state["a2_memory_demo_counter"] = next_id
                entry["id"] = next_id

                st.session_state[f"a2_memory_tag_{next_id}"] = "Green"
                st.session_state["a2_memory_demo_entries"].append(entry)

                st.session_state.sp = sp
                st.session_state.sp_a2 = copy.deepcopy(sp)
                st.session_state["super_prompt_text"] = sp.prompt_ready

                st.rerun()

        with b1c3:
            clicked_retrieval = st.button("Retrieval", key="btn_retrieval", use_container_width=True)
            if clicked_retrieval:
                try:
                    ctrl: AppController = st.session_state.controller
                    sp: SuperPrompt = st.session_state.sp

                    project_name = st.session_state.get("active_project")
                    if not project_name:
                        available_projects = ctrl.list_projects()
                        if available_projects:
                            project_name = available_projects[0]
                            st.session_state["active_project"] = project_name

                    if not project_name or project_name == "(no projects yet)":
                        st.error("No active project is available for Retrieval.")
                    else:
                        top_k = int(st.session_state.get("retrieval_top_k", 100))
                        sp = ctrl.run_retrieval(sp, project_name, top_k)
                        sp.compose_prompt_ready()

                        st.session_state.sp = sp
                        st.session_state.sp_rtv = copy.deepcopy(sp)
                        st.session_state["super_prompt_text"] = sp.prompt_ready

                except Exception as e:
                    st.error(str(e))

        with b1c4:
            clicked_reranker = st.button("ReRanker", key="btn_reranker", use_container_width=True)
            if clicked_reranker:
          #      try:
                    ctrl: AppController = st.session_state.controller
                    sp: SuperPrompt = st.session_state.sp

                    sp = ctrl.run_reranker(sp)
                    sp.compose_prompt_ready()

                    st.session_state.sp = sp
                    st.session_state.sp_rrk = copy.deepcopy(sp)
                    st.session_state["super_prompt_text"] = sp.prompt_ready

             #   except Exception as e:
                #    st.error(str(e))

        # Row 2: 4 buttons
        b2c1, b2c2, b2c3, b2c4 = st.columns(4, gap="small")
        with b2c1:
            st.button("A3 NLI Gate", key="btn_a3", use_container_width=True)
        with b2c2:
            st.button("A4 Condenser", key="btn_a4", use_container_width=True)
        with b2c3:
            st.button("A5 Format Enforcer", key="btn_a5", use_container_width=True)
        with b2c4:
            st.button("Prompt Builder", key="btn_builder", use_container_width=True)

        st.number_input(
            "Retrieval Top-K (number of chunks)",
            min_value=1,
            max_value=1000,
            step=1,
            key="retrieval_top_k",
        )

        # New project-based ingestion controls placed below the agent buttons.
        st.markdown("<div style='height:0.45rem'></div>", unsafe_allow_html=True)

        ctrl: AppController = st.session_state.controller
        projects = ctrl.list_projects()

        # Apply requested project switch before the "active_project" widget
        # is created in this run. This avoids the Streamlit session-state error.
        pending_project = st.session_state.get("pending_active_project")
        if pending_project is not None:
            if projects and pending_project in projects:
                st.session_state["active_project"] = pending_project
            st.session_state["pending_active_project"] = None

        if projects:
            if st.session_state.get("active_project") not in projects:
                st.session_state["active_project"] = projects[0]
            st.selectbox(
                "Active DB / Project",
                options=projects,
                key="active_project",
            )
        else:
            st.selectbox(
                "Active DB / Project",
                options=["(no projects yet)"],
                index=0,
                disabled=True,
            )

        # Show the files that are actually ingested/embedded for the currently
        # active project by reading the standardized manifest through the controller.
        active_project = st.session_state.get("active_project")
        if projects and active_project in projects:
            embedded_info = ctrl.get_embedded_files(active_project)

            st.markdown("<div style='height:0.25rem'></div>", unsafe_allow_html=True)
            st.markdown(
                '<div class="field-title" style="font-size:1.05rem;">Embedded Files</div>',
                unsafe_allow_html=True,
            )

            if embedded_info.get("success"):
                embedded_files = embedded_info.get("files", [])
                embedded_text = "\n".join(embedded_files) if embedded_files else "(no embedded files yet)"
                st.text_area(
                    label="Embedded Files (hidden)",
                    value=embedded_text,
                    height=120,
                    disabled=True,
                    label_visibility="collapsed",
                )
            else:
                st.error(embedded_info.get("message", "Could not read embedded file list."))

        create_col, add_col = st.columns(2, gap="small")

        with create_col:
            with st.form("create_project_form", clear_on_submit=False):
                st.text_input("Project Name", key="new_project_name")
                create_clicked = st.form_submit_button("Create Project", use_container_width=True)
                if create_clicked:
                    try:
                        result = ctrl.create_project(st.session_state.get("new_project_name", ""))
                        st.session_state["ingestion_status"] = {
                            "type": "success",
                            "message": f"Project created: {result['project_name']}",
                            "details": [
                                f"doc_raw: {result['raw_dir']}",
                                f"chroma_db: {result['chroma_dir']}",
                                f"manifest: {result['manifest_path']}",
                            ],
                        }
                        st.session_state["pending_active_project"] = result["project_name"]
                        st.rerun()
                    except Exception as e:
                        st.session_state["ingestion_status"] = {
                            "type": "error",
                            "message": str(e),
                            "details": [],
                        }

        with add_col:
            with st.form("add_files_form", clear_on_submit=False):
                add_projects = ctrl.list_projects()
                if add_projects:
                    current_active_project = st.session_state.get("active_project")
                    if current_active_project in add_projects:
                        default_add_project = current_active_project
                    else:
                        default_add_project = add_projects[0]

                    st.selectbox(
                        "Choose Project",
                        options=add_projects,
                        key="add_files_project",
                        index=add_projects.index(default_add_project),
                    )
                    uploaded_files = st.file_uploader(
                        "Select .txt / .md files from your local machine",
                        type=["txt", "md"],
                        accept_multiple_files=True,
                        key="ingestion_uploaded_files",
                    )
                    add_clicked = st.form_submit_button("Add Files", use_container_width=True)
                    if add_clicked:
                        try:
                            result = ctrl.import_files_to_project(
                                st.session_state.get("add_files_project", ""),
                                uploaded_files=uploaded_files,
                            )
                            if result.get("success"):
                                st.session_state["ingestion_status"] = {
                                    "type": "success",
                                    "message": (
                                        f"Files added to {result['project_name']} "
                                        f"and ingestion finished."
                                    ),
                                    "details": [
                                        f"copied files: {result.get('copied_count', 0)}",
                                        f"files scanned: {result.get('files_scanned', 0)}",
                                        f"to process: {result.get('to_process', 0)}",
                                        f"unchanged: {result.get('unchanged', 0)}",
                                        f"vectors upserted: {result.get('vectors_upserted', 0)}",
                                        f"manifest: {result.get('manifest_path', '')}",
                                    ] + [
                                        f"rejected: {item}" for item in result.get("rejected_files", [])
                                    ],
                                }
                                st.session_state["pending_active_project"] = result["project_name"]
                                st.rerun()
                            else:
                                st.session_state["ingestion_status"] = {
                                    "type": "error",
                                    "message": result.get("message", "No files were added."),
                                    "details": [
                                        f"rejected: {item}" for item in result.get("rejected_files", [])
                                    ],
                                }
                        except Exception as e:
                            st.session_state["ingestion_status"] = {
                                "type": "error",
                                "message": str(e),
                                "details": [],
                            }
                else:
                    st.info("Create a project first, then add files.")

        # Small status/debug area for the new ingestion workflow.
        status = st.session_state.get("ingestion_status")
        if status:
            if status.get("type") == "success":
                st.success(status.get("message", ""))
            else:
                st.error(status.get("message", ""))
            for detail in status.get("details", []):
                st.caption(detail)

    # SPACER between columns
    with spacer:
        st.empty()

    # RIGHT: Super-Prompt box
    with col_right:
        st.markdown('<div class="field-title">Super-Prompt</div>', unsafe_allow_html=True)
        st.text_area(
            label="Super-Prompt (hidden)",
            key="super_prompt_text",
            height=240,
            label_visibility="collapsed",
        )

    with gutter_r:
        st.empty()


if __name__ == "__main__":
    main()
```

### ~\ragstream\app\ui_streamlit_demo.py
```python
# -*- coding: utf-8 -*-
"""
RAGstream - ui_streamlit.py (Version 1 GUI Shell)

Purpose
-------
Single-file Streamlit UI that:
- Defines the overall 3-zone layout and routing.
- Implements top-level controls (Send/Cancel, Progress, Status, Transparency).
- Integrates with AppController if available; otherwise uses a safe stub.
- Calls out to support views (ui_sections/*) if present; provides inline fallbacks if not.

Notes
-----
- Plain text UI (no emojis/icons), compact and readable on a standard 1080p monitor.
- Advanced panels (History, Transparency, Debug, External Replies) are tucked into tabs/accordions.
- This file is intentionally self-contained to run without the support modules.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import streamlit as st

# -----------------------------------------------------------------------------
# Optional controller import (graceful fallback if backend is not wired yet)
# -----------------------------------------------------------------------------
try:
    from .controller import AppController  # type: ignore
except Exception:
    class AppController:  # type: ignore
        """Fallback controller to keep the UI runnable without backend."""
        def __init__(self) -> None:
            self.model = "gpt-4o"
        def handle(self, user_prompt: str, named_files: list[str], exact_lock: bool) -> str:
            return "[Controller stub] No backend yet. This is a placeholder response."
        def estimate_cost(self, tokens: int) -> float:
            return 0.0


# -----------------------------------------------------------------------------
# Optional support views (graceful fallbacks provided if imports fail)
# The real app can place these under ragstream/app/ui_sections/*.py
# -----------------------------------------------------------------------------
def _fallback_prompt_area(state: Dict[str, Any]) -> None:
    st.subheader("Prompt")
    state["prompt_text"] = st.text_area("Enter your prompt", value=state.get("prompt_text", ""), height=140)
    st.subheader("Super-Prompt Preview (optional)")
    state["super_prompt"] = st.text_area("Preview (editable before send)", value=state.get("super_prompt", ""), height=120)

def _fallback_model_agent_bar(state: Dict[str, Any]) -> None:
    st.subheader("Model & Agent Controls")
    state["model"] = st.selectbox("Model", options=["gpt-4o", "gpt-4o-mini", "ollama:llama3"], index=0)
    cols = st.columns(5)
    state["a1_on"] = cols[0].checkbox("A1", value=True)
    state["a2_on"] = cols[1].checkbox("A2", value=True)
    state["a3_on"] = cols[2].checkbox("A3", value=True)
    state["a4_on"] = cols[3].checkbox("A4", value=True)
    state["a5_on"] = cols[4].checkbox("A5", value=True)
    st.caption("Cost estimate is shown before send when available.")

def _fallback_file_eligibility(state: Dict[str, Any]) -> None:
    st.subheader("Files & Eligibility")
    st.caption("Per-file ON/OFF determines the Eligibility Pool for retrieval.")
    state.setdefault("files", ["docs/Req.md", "docs/Arch.md", "notes/plan.txt"])
    state.setdefault("files_on", {f: True for f in state["files"]})
    for f in state["files"]:
        state["files_on"][f] = st.checkbox(f"ON — {f}", value=state["files_on"].get(f, True), key=f"on_{f}")
    state["exact_lock"] = st.checkbox("Exact File Lock (skip retrieval, inject ❖ FILES only)", value=False)
    st.caption("Manifest is not wired yet in this fallback. Add ui_sections/file_eligibility.py to replace.")

def _fallback_prompt_shaper(state: Dict[str, Any]) -> None:
    with st.expander("Prompt Shaper (A2)"):
        state["intent"] = st.text_input("Intent", value=state.get("intent", "explain"))
        state["domain"] = st.text_input("Domain", value=state.get("domain", "software"))
        st.text_area("Headers / Roles (advisory)", value=state.get("headers", "H"), height=80)

def _fallback_history_panel(state: Dict[str, Any]) -> None:
    st.subheader("History Controls")
    state["history_k"] = st.slider("Recent turns (Layer-G, k)", 0, 10, state.get("history_k", 3))
    state["layer_e_budget"] = st.number_input("Layer-E token budget", min_value=0, max_value=5000, value=state.get("layer_e_budget", 500), step=50)
    state["mark_important"] = st.checkbox("Mark current turn important", value=state.get("mark_important", False))
    state["persist_history"] = st.checkbox("Persist History (Layer-E) ON/OFF", value=state.get("persist_history", True))
    if st.button("Clear Persisted Layer-E"):
        state["history_cleared"] = True
        st.success("Persisted Layer-E cleared (placeholder).")
    st.file_uploader("Synonym list import (optional)", type=["txt", "csv", "json"], accept_multiple_files=False)

def _fallback_external_reply_panel(state: Dict[str, Any]) -> None:
    st.subheader("External Reply Import")
    state["external_reply"] = st.text_area("Paste external LLM reply here", value=state.get("external_reply", ""), height=140)
    if st.button("Send to History"):
        st.success("External reply appended to history (placeholder).")

def _fallback_transparency_panel(state: Dict[str, Any]) -> None:
    st.subheader("Transparency")
    st.caption("Kept/Dropped with reasons; ❖ FILES and S_ctx views.")
    st.text_area("Kept/Dropped (reasons)", value=state.get("kept_dropped", ""), height=100)
    st.text_area("❖ FILES (injected)", value=state.get("files_block", ""), height=100)
    st.text_area("S_ctx (Facts / Constraints / Open Issues)", value=state.get("s_ctx", ""), height=120)

def _fallback_output_panel(state: Dict[str, Any]) -> None:
    st.subheader("Output")
    st.text_area("Assistant Response", value=state.get("answer_text", ""), height=240)
    cols = st.columns(2)
    if cols[0].button("Export with citations"):
        st.success("Exported (placeholder).")
    state["show_transparency"] = cols[1].checkbox("Show Transparency", value=state.get("show_transparency", False))

def _fallback_debug_panel(state: Dict[str, Any]) -> None:
    st.subheader("Debug / Diagnostics")
    state["debug_on"] = st.checkbox("Enable Debug Logger", value=state.get("debug_on", False))
    st.text_input("Session ID", value=state.get("session_id", "sess-0001"))
    st.text_area("Last Ingestion Stats", value=state.get("ingestion_stats", "files=0, chunks=0, bytes=0"), height=80)
    if st.button("Snapshot Vector DB"):
        st.info("Snapshot triggered (placeholder).")


# Try to import the real support modules; if missing, keep fallbacks
try:
    from .ui_sections.prompt_area import render as render_prompt_area  # type: ignore
except Exception:
    render_prompt_area = _fallback_prompt_area  # type: ignore

try:
    from .ui_sections.model_agent_bar import render as render_model_agent_bar  # type: ignore
except Exception:
    render_model_agent_bar = _fallback_model_agent_bar  # type: ignore

try:
    from .ui_sections.file_eligibility import render as render_file_eligibility  # type: ignore
except Exception:
    render_file_eligibility = _fallback_file_eligibility  # type: ignore

try:
    from .ui_sections.prompt_shaper import render as render_prompt_shaper  # type: ignore
except Exception:
    render_prompt_shaper = _fallback_prompt_shaper  # type: ignore

try:
    from .ui_sections.history_panel import render as render_history_panel  # type: ignore
except Exception:
    render_history_panel = _fallback_history_panel  # type: ignore

try:
    from .ui_sections.external_reply_panel import render as render_external_reply_panel  # type: ignore
except Exception:
    render_external_reply_panel = _fallback_external_reply_panel  # type: ignore

try:
    from .ui_sections.transparency_panel import render as render_transparency_panel  # type: ignore
except Exception:
    render_transparency_panel = _fallback_transparency_panel  # type: ignore

try:
    from .ui_sections.output_panel import render as render_output_panel  # type: ignore
except Exception:
    render_output_panel = _fallback_output_panel  # type: ignore

try:
    from .ui_sections.debug_panel import render as render_debug_panel  # type: ignore
except Exception:
    render_debug_panel = _fallback_debug_panel  # type: ignore


# -----------------------------------------------------------------------------
# UI helper: status bar and progress markers
# -----------------------------------------------------------------------------
def _status_bar(state: Dict[str, Any]) -> None:
    cols = st.columns(4)
    cols[0].markdown(f"**Model:** {state.get('model', 'gpt-4o')}")
    cols[1].markdown(f"**History:** {'Persist ON' if state.get('persist_history', True) else 'Persist OFF'}")
    cols[2].markdown(f"**Latency:** {state.get('latency_ms', '—')} ms")
    cols[3].markdown(f"**Cost Ceiling:** {state.get('cost_ceiling', '—')}")

def _progress_strip(state: Dict[str, Any]) -> None:
    st.caption("Stages: A0 FileScope • A1 DCI • A2 Shaper • Retrieval • Rerank • A3 NLI • A4 Condense • A5 Validate")


# -----------------------------------------------------------------------------
# Main UI class
# -----------------------------------------------------------------------------
class StreamlitUI:
    def __init__(self) -> None:
        if "state" not in st.session_state:
            st.session_state["state"] = {}
        self.state: Dict[str, Any] = st.session_state["state"]
        self.ctrl = AppController()

    def _send_clicked(self) -> None:
        prompt = self.state.get("prompt_text", "").strip()
        files_on = self.state.get("files_on", {})
        named_files = [p for p, on in files_on.items() if on]
        exact_lock = bool(self.state.get("exact_lock", False))

        if not prompt:
            st.warning("Please enter a prompt.")
            return

        # Pre-send cost gate (placeholder)
        self.state["cost_estimate"] = self.ctrl.estimate_cost(tokens=len(prompt) // 4) if hasattr(self.ctrl, "estimate_cost") else 0.0
        ceiling = self.state.get("cost_ceiling_value", None)
        if ceiling is not None and self.state["cost_estimate"] > ceiling:
            st.error("Cost ceiling exceeded. Adjust prompt or settings.")
            return

        # Call controller (or stub)
        answer = self.ctrl.handle(prompt, named_files, exact_lock)
        self.state["answer_text"] = answer

    def _cancel_clicked(self) -> None:
        st.info("Cancelled (placeholder).")

    def render(self) -> None:
        st.title("RAGstream")

        # Status / Safety banners
        _status_bar(self.state)
        _progress_strip(self.state)

        # Primary action bar
        bar = st.columns([1, 1, 2, 2, 2])
        if bar[0].button("Send"):
            self._send_clicked()
        if bar[1].button("Cancel/Retry"):
            self._cancel_clicked()
        self.state["cost_ceiling_value"] = bar[2].number_input("Cost ceiling (€)", min_value=0.0, value=float(self.state.get("cost_ceiling_value", 0.0)), step=0.10, help="Pre-send ceiling; set 0 to disable")
        self.state["latency_ms"] = bar[3].text_input("Latency hint (ms)", value=str(self.state.get("latency_ms", "")))
        self.state["transparency_toggle"] = bar[4].checkbox("Transparency ON/OFF", value=self.state.get("transparency_toggle", False))

        # Three-column layout
        left, center, right = st.columns([0.33, 0.47, 0.20])

        with left:
            render_prompt_area(self.state)
            render_model_agent_bar(self.state)
            render_file_eligibility(self.state)
            render_prompt_shaper(self.state)

        with center:
            render_output_panel(self.state)

        with right:
            tabs = st.tabs(["History", "Transparency", "External", "Debug"])
            with tabs[0]:
                render_history_panel(self.state)
            with tabs[1]:
                if self.state.get("show_transparency") or self.state.get("transparency_toggle"):
                    render_transparency_panel(self.state)
                else:
                    st.info("Transparency is OFF.")
            with tabs[2]:
                render_external_reply_panel(self.state)
            with tabs[3]:
                render_debug_panel(self.state)

        # Escalation (Human-in-the-Loop) panel if present
        if self.state.get("escalate", False):
            st.error(f"Escalation: {self.state.get('escalate_reason', 'unspecified')}")
            st.write("Suggested next steps: adjust eligibility, inject ❖ FILES, or retry.")

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
def run() -> None:
    ui = StreamlitUI()
    ui.render()

if __name__ == "__main__":
    run()
```


## /home/rusbeh_ab/project/RAGstream/ragstream/config

### ~\ragstream\config\settings.py
```python
"""
Settings
========
Centralised, cached access to environment configuration.
"""
import os
from typing import Any, Dict

class Settings:
    _CACHE: Dict[str, Any] = {}

    @classmethod
    def get(cls, key: str, default: Any | None = None) -> Any:
        if key not in cls._CACHE:
            cls._CACHE[key] = os.getenv(key, default)
        return cls._CACHE[key]
```


## /home/rusbeh_ab/project/RAGstream/ragstream/ingestion

### ~\ragstream\ingestion\chroma_vector_store_base.py
```python
# -*- coding: utf-8 -*-
"""
chroma_vector_store_base.py

Shared, production-grade base class for Chroma-backed vector stores.

Context:
- Replaces the old NumPy PKL store with a persistent, crash-safe, on-disk DB.
- Both VectorStoreChroma and HistoryStoreChroma should inherit from this class.
- We intentionally removed any separate "IVectorStore" interface; this concrete
  base provides the canonical add/query/snapshot API and small hook points so
  subclasses can enforce their own policies without duplicating core logic.

Contract (compatible with your former NumPy store):
    add(ids, vectors, metadatas) -> None
    query(vector, k=10, where=None) -> List[str]
    snapshot(timestamp=None) -> Path

Design notes:
- Uses chromadb.PersistentClient(path=...) to ensure physical persistence on disk.
- Stores ONLY embeddings + metadatas (documents are optional for this project).
- Provides hook methods (_pre_add/_post_add/_pre_query/_post_query) so that the
  history store can enforce selection-only / capacity / eligibility rules later.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import shutil
from datetime import datetime

import chromadb
from chromadb.config import Settings


class ChromaVectorStoreBase:
    """
    Base implementation of a Chroma-backed vector store.

    Responsibilities:
      - Own the PersistentClient and a single collection.
      - Provide simple, deterministic add/query/snapshot methods.
      - Offer policy hooks for subclasses (history vs. document store).

    Subclasses:
      - VectorStoreChroma(ChromaVectorStoreBase)
      - HistoryStoreChroma(ChromaVectorStoreBase)

    Typical metadata for each chunk (recommended):
      {
        "path": "<relative/original file path>",
        "sha256": "<content hash>",
        "mtime": <float or iso string>,
        "chunk_idx": <int>
      }
    """

    def __init__(
        self,
        persist_dir: str,
        collection_name: str,
        *,
        anonymized_telemetry: bool = False,
    ) -> None:
        """
        Initialize a persistent Chroma client and open/create a collection.

        Args:
            persist_dir: Directory where Chroma DB files live (e.g. PATHS.chroma_db).
            collection_name: Logical collection name (e.g. "docs" or "history").
            anonymized_telemetry: Pass False to avoid any telemetry (default False).
        """
        self.persist_path = Path(persist_dir)
        self.persist_path.mkdir(parents=True, exist_ok=True)

        # Settings keep the DB local, file-backed, and quiet (no telemetry).
        self._client = chromadb.PersistentClient(
            path=str(self.persist_path),
            settings=Settings(anonymized_telemetry=anonymized_telemetry),
        )

        self.collection_name = collection_name
        self._col = self._client.get_or_create_collection(self.collection_name)

    # -------------------------------------------------------------------------
    # Public API (stable)
    # -------------------------------------------------------------------------

    def add(
        self,
        ids: List[str],
        vectors: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Upsert vectors and metadatas into the collection.

        Contract matches the previous NumPy store:
          - ids:      unique stable IDs per chunk (e.g. "path::sha256::i")
          - vectors:  2D list [N, D] of float embeddings
          - metadatas: optional [N] list of dicts (same length as ids)

        Notes:
          - If an id already exists, Chroma upserts (replaces) it.
          - Subclasses may enforce policies via _pre_add/_post_add hooks.
        """
        if not ids or not vectors:
            return
        if len(ids) != len(vectors):
            raise ValueError("ids and vectors length mismatch")
        if metadatas is not None and len(metadatas) != len(ids):
            raise ValueError("metadatas length must match ids (or be None)")

        ids, vectors, metadatas = self._pre_add(ids, vectors, metadatas)

        # Core upsert (embeddings + optional metadatas). Documents are unused here.
        self._col.upsert(
            ids=ids,
            embeddings=vectors,
            metadatas=metadatas,
        )

        self._post_add(ids, vectors, metadatas)

    def query(
        self,
        vector: List[float],
        k: int = 10,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Nearest-neighbor search against the collection by embedding vector.

        Args:
            vector: 1D float embedding of the query.
            k: number of neighbors to return.
            where: optional Chroma metadata filter; pass None for no filter.

        Returns:
            List[str]: top-k IDs (sorted by similarity).
                       This mirrors the former NumPy store return type.

        Subclasses may adjust behavior via _pre_query/_post_query.
        """
        if not isinstance(vector, list) or not vector:
            raise ValueError("query vector must be a non-empty 1D list[float]")

        k = max(1, int(k))

        # IMPORTANT: some Chroma versions reject {} and require None when no filter is used.
        where = None if not where else where

        vector, k, where = self._pre_query(vector, k, where)

        res = self._col.query(
            query_embeddings=[vector],
            n_results=k,
            where=where,               # None means "no filter"
            include=["metadatas"],     # metadatas available for post-processing if needed
        )
        # result shape: {"ids": [[...]], "metadatas": [[...]], ...}
        ids: List[str] = res.get("ids", [[]])[0] if res else []
        ids = self._post_query(ids, res)
        return ids

    def snapshot(self, timestamp: Optional[str] = None) -> Path:
        """
        Create a filesystem snapshot of the current Chroma DB directory.

        Implementation:
          - Copies the entire persist_dir into ./snapshots/<db_name>_<timestamp>/
          - This is a coarse, but deterministic snapshot suitable for local dev.
          - For very large DBs, consider OS-level copy-on-write or backup tooling.

        Returns:
            Path to the created snapshot directory.
        """
        ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshots_dir = self.persist_path.parent / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        dst = snapshots_dir / f"{self.persist_path.name}_{ts}"

        # Copy the whole DB dir. dirs_exist_ok=False to avoid accidental overwrite.
        shutil.copytree(self.persist_path, dst, dirs_exist_ok=False)
        return dst

    # Optional utility, handy for re-ingestion flows that need to remove stale chunks
    def delete_where(self, where: Dict[str, Any]) -> None:
        """
        Delete by metadata filter (two-phase: lookup ids, then delete ids).
        This makes the operation explicit and auditable.
        """
        if not where:
            return
        res = self._col.get(where=where, include=[])  # get ids only
        ids: List[str] = res.get("ids", []) if res else []
        if ids:
            self._col.delete(ids=ids)

    # Expose underlying collection for advanced ops if needed (debug, migration)
    @property
    def collection(self):
        return self._col

    # -------------------------------------------------------------------------
    # Hook methods (subclasses override as needed)
    # -------------------------------------------------------------------------

    def _pre_add(
        self,
        ids: List[str],
        vectors: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]],
    ) -> tuple[List[str], List[List[float]], Optional[List[Dict[str, Any]]]]:
        """
        Override in subclasses to enforce policies before upsert, e.g.:
          - capacity checks, eviction, dedup, eligibility constraints (history store)
          - metadata normalization or enrichment
        Default: no-op, return inputs unchanged.
        """
        return ids, vectors, metadatas

    def _post_add(
        self,
        ids: List[str],
        vectors: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]],
    ) -> None:
        """
        Override in subclasses to log / index / audit after upsert.
        Default: no-op.
        """
        return None

    def _pre_query(
        self,
        vector: List[float],
        k: int,
        where: Optional[Dict[str, Any]],
    ) -> tuple[List[float], int, Optional[Dict[str, Any]]]:
        """
        Override in subclasses to enforce query-time policies, e.g.:
          - eligibility alignment (history store)
          - metadata filter injection
        Default: no-op, return inputs unchanged.
        """
        return vector, k, where

    def _post_query(self, ids: List[str], raw_result: Dict[str, Any]) -> List[str]:
        """
        Override in subclasses to transform the result list, e.g.:
          - strip restricted items
          - reorder by additional heuristics
        Default: no-op, return ids unchanged.
        """
        return ids
```

### ~\ragstream\ingestion\chunker.py
```python
"""
Chunker
=======
Splits raw text into overlapping, character-based chunks for embedding.
"""

from typing import List, Tuple

class Chunker:
    """Window-based text splitter."""

    def split(self, file_path: str, text: str, chunk_size: int = 500, overlap: int = 100) -> List[Tuple[str, str]]:
        """
        Split the given text into overlapping chunks.

        :param file_path: Absolute path to the source file (kept with each chunk)
        :param text: The full text content of the file
        :param chunk_size: Maximum characters per chunk (default=500)
        :param overlap: Number of characters to overlap between chunks (default=100)
        :return: List of (file_path, chunk_text) tuples
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if overlap < 0:
            raise ValueError("overlap must be non-negative")
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")

        chunks: List[Tuple[str, str]] = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = min(start + chunk_size, text_length)
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append((file_path, chunk_text))
            start += chunk_size - overlap

        return chunks
```

### ~\ragstream\ingestion\embedder.py
```python
"""
Embedder
========
Wraps OpenAI embeddings API to convert text chunks into dense vectors.
"""
from typing import List
import os
from dotenv import load_dotenv
from openai import OpenAI

class Embedder:
    """High-level embedding interface using OpenAI API."""
    def __init__(self, model: str = "text-embedding-3-large"):
        load_dotenv()  # Load .env file
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment or .env file")

        self.client = OpenAI(api_key=api_key)
        self.model = model

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        Returns: list of embedding vectors (one per text)
        """
        if not texts:
            return []

        # OpenAI API allows batch embedding calls
        response = self.client.embeddings.create(
            model=self.model,
            input=texts
        )

        # Extract embeddings from response
        embeddings = [item.embedding for item in response.data]
        return embeddings
```

### ~\ragstream\ingestion\file_manifest.py
```python
# -*- coding: utf-8 -*-
"""
file_manifest.py

Purpose:
    A tiny, deterministic "ledger" for document ingestion. It tells the
    ingestion pipeline which files have changed since last run so we only
    re-chunk/re-embed what's necessary.

What this module provides:
    1) compute_sha256(file_path) -> str
       - Returns the SHA-256 hex digest for ONE file on disk.

    2) load_manifest(manifest_path) -> dict
       - Loads the last published manifest JSON (or returns an empty one).

    3) diff(records_now, manifest_prev) -> (to_process, unchanged, tombstones)
       - Compares current scan results ("records_now") against the previous
         manifest ("manifest_prev") and decides what to ingest or clean up.

    4) publish_atomic(manifest_dict, manifest_path) -> None
       - Writes the ENTIRE manifest JSON atomically: *.tmp then os.replace.

Data shapes:
    Record (one per file; used both during scan and inside the manifest):
        {
          "path":   str,    # RELATIVE path from doc root, e.g. "project1/file.md"
          "sha256": str,    # content hash (hex)
          "mtime":  float,  # UNIX mtime
          "size":   int     # bytes
        }

    Manifest JSON written to disk:
        {
          "version": "1",
          "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
          "files": [Record, Record, ...]
        }

Notes:
    - This module does NOT scan directories. IngestionManager (or caller) is
      responsible for building 'records_now' from the doc root using compute_sha256.
    - 'diff' expects 'records_now' as a list[Record] and the previous manifest dict.
    - 'tombstones' are files that were present in the previous manifest but are
      missing on disk now (useful for deleting stale vectors).
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple, TypedDict


# ---------------------------------------------------------------------------
# Typed structures for clarity (no runtime dependency; just type hints)
# ---------------------------------------------------------------------------

class Record(TypedDict):
    """A single file's state at scan time (also stored in the manifest)."""
    path: str     # relative path from doc root, POSIX style (e.g., "project1/file.md")
    sha256: str   # hex SHA-256 of the file contents
    mtime: float  # last modified time (float UNIX timestamp)
    size: int     # file size in bytes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_sha256(file_path: str, *, chunk_size: int = 1024 * 1024) -> str:
    """
    Compute a SHA-256 hex digest for a SINGLE file.

    Args:
        file_path: absolute or relative path to a file on disk.
        chunk_size: read size in bytes (default 1MB) to handle large files safely.

    Returns:
        The hex string of the SHA-256 content hash.

    Raises:
        FileNotFoundError: if the file does not exist.
        IsADirectoryError: if 'file_path' is a directory.
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if p.is_dir():
        raise IsADirectoryError(f"Expected a file, got directory: {file_path}")

    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load_manifest(manifest_path: str) -> Dict[str, Any]:
    """
    Load the manifest JSON if it exists; otherwise, return a valid empty structure.

    Args:
        manifest_path: full filesystem path to 'file_manifest.json'.

    Returns:
        Dict with keys:
            - "version": "1"
            - "generated_at": ISO-8601 string (UTC) or ""
            - "files": list[Record]
    """
    mp = Path(manifest_path)
    if not mp.exists():
        # Return a deterministic empty manifest structure.
        return {
            "version": "1",
            "generated_at": "",
            "files": [],
        }

    try:
        with mp.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        # If the file is corrupted, fail loudly; caller can decide what to do.
        raise ValueError(f"Manifest is not valid JSON: {manifest_path}") from e

    # Normalize to expected keys (be forgiving about missing keys).
    if "version" not in data:
        data["version"] = "1"
    if "generated_at" not in data:
        data["generated_at"] = ""
    if "files" not in data or not isinstance(data["files"], list):
        data["files"] = []

    return data


def diff(
    records_now: List[Record],
    manifest_prev: Dict[str, Any],
) -> Tuple[List[Record], List[Record], List[Record]]:
    """
    Compare the current scan against the previous manifest.

    Args:
        records_now: list of current file Records (built by the caller during scan).
        manifest_prev: manifest dict as returned by load_manifest().

    Returns:
        (to_process, unchanged, tombstones)
            to_process: Records that are NEW or CHANGED (sha256 differs).
            unchanged:  Records that are IDENTICAL to previous (same path + sha256).
            tombstones: Records from the PREVIOUS manifest that are MISSING now on disk.

    Matching logic:
        - Key by 'path'.
        - If 'path' is new (not in previous) => to_process.
        - If 'path' exists but sha256 changed => to_process.
        - Else => unchanged.
        - tombstones = previous paths not present in records_now.
    """
    prev_files = manifest_prev.get("files", []) if isinstance(manifest_prev, dict) else []

    # Build fast lookups by path.
    prev_by_path: Dict[str, Record] = {rec["path"]: rec for rec in prev_files}  # type: ignore[typeddict-item]
    now_by_path: Dict[str, Record] = {rec["path"]: rec for rec in records_now}

    to_process: List[Record] = []
    unchanged: List[Record] = []
    tombstones: List[Record] = []

    # Decide new/changed vs unchanged.
    for path, now_rec in now_by_path.items():
        prev_rec = prev_by_path.get(path)
        if prev_rec is None:
            # New file.
            to_process.append(now_rec)
        else:
            # Same path existed previously; compare hashes.
            if str(prev_rec["sha256"]) != str(now_rec["sha256"]):
                to_process.append(now_rec)   # Content changed.
            else:
                unchanged.append(now_rec)    # Identical (skip re-ingest).

    # Anything in previous but not in current is a tombstone (missing on disk).
    for path, prev_rec in prev_by_path.items():
        if path not in now_by_path:
            tombstones.append(prev_rec)

    return to_process, unchanged, tombstones


def publish_atomic(manifest_dict: Dict[str, Any], manifest_path: str) -> None:
    """
    Atomically write the ENTIRE manifest JSON to disk.

    Implementation:
        - Ensure parent directory exists.
        - Write to <manifest_path>.tmp with UTF-8 + pretty JSON.
        - os.replace(tmp, manifest_path) for atomic swap (POSIX-safe).

    Args:
        manifest_dict: the full manifest payload to persist.
        manifest_path: destination JSON path, e.g. ".../data/file_manifest.json".
    """
    mp = Path(manifest_path)
    mp.parent.mkdir(parents=True, exist_ok=True)

    # Stamp/refresh generated_at if caller forgot; harmless overwrite is fine.
    if "generated_at" not in manifest_dict:
        manifest_dict["generated_at"] = _utc_now_iso()
    else:
        # If present but empty, also refresh.
        if not manifest_dict["generated_at"]:
            manifest_dict["generated_at"] = _utc_now_iso()

    tmp_path = mp.with_suffix(mp.suffix + ".tmp")

    # Write JSON with a stable format (sorted keys, indentation).
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(manifest_dict, f, ensure_ascii=False, indent=2, sort_keys=True)

    # Atomic replace: either the old file stays, or the new one fully replaces it.
    os.replace(str(tmp_path), str(mp))


# ---------------------------------------------------------------------------
# Internal helpers (not part of the public API)
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    """Return a UTC timestamp in ISO-8601 format with 'Z' suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
```

### ~\ragstream\ingestion\ingestion_manager.py
```python
# -*- coding: utf-8 -*-
"""
ingestion_manager.py

Purpose:
    Orchestrate deterministic document ingestion for RAGstream:
      scan → diff vs. manifest → chunk → embed → store → publish manifest

Scope:
    • This module focuses on the "documents" ingestion path only
      (conversation history layers are postponed as agreed).
    • Works with your existing loader, chunker, embedder, and Chroma vector store.

Key responsibilities:
    1) Build a list of current file Records by scanning a doc root/subfolder.
    2) Load the previous manifest and compute a diff (what changed vs. last run).
    3) For changed/new files: chunk → embed → upsert to VectorStoreChroma.
       Optionally delete stale vectors from previous file versions.
    4) Publish a new manifest atomically (tmp → replace) if the run succeeds.

API:
    IngestionManager(doc_root).run(
        subfolder: str,
        store: ChromaVectorStoreBase,
        chunker: Chunker,
        embedder: Embedder,
        manifest_path: str,
        *,
        chunk_size: int = 500,
        overlap: int = 100,
        delete_old_versions: bool = True,
        delete_tombstones: bool = False,
    ) -> dict (stats)

Data structures:
    Record (from file_manifest.py):
        {
          "path":   "project1/file.md",  # relative to doc_root
          "sha256": "<hex>",
          "mtime":  <float>,
          "size":   <int>
        }

Notes:
    • We compute file hashes from bytes on disk (compute_sha256), NOT from text.
    • Chunk IDs are stable: f"{rel_path}::{sha256}::{idx}" (matches your store helpers).
    • We only publish a new manifest after all target files in this run succeed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Local imports: your existing components
from .loader import DocumentLoader          # returns [(abs_path, text), ...]
from .chunker import Chunker                # split(file_path, text, chunk_size, overlap)
from .embedder import Embedder              # embed(list[str]) -> list[list[float]]
from .vector_store_chroma import VectorStoreChroma  # Chroma-backed store

# Manifest utilities
from .file_manifest import (
    compute_sha256,
    load_manifest,
    diff as manifest_diff,
    publish_atomic,
    Record,   # TypedDict
)


@dataclass(frozen=True)
class IngestionStats:
    """Aggregate numbers for quick reporting / testing."""
    files_scanned: int
    to_process: int
    unchanged: int
    tombstones: int
    chunks_added: int
    vectors_upserted: int
    deleted_old_versions: int
    deleted_tombstones: int
    published_manifest_path: str
    embedded_bytes: int  # total UTF-8 bytes sent to the embedder in this run

class IngestionManager:
    """
    Coordinates the full ingestion pipeline for a given doc root.

    Typical usage:
        mgr = IngestionManager(doc_root="/.../data/doc_raw")
        stats = mgr.run(
            subfolder="project1",
            store=VectorStoreChroma(persist_dir=".../data/chroma_db/project1"),
            chunker=Chunker(),
            embedder=Embedder(model="text-embedding-3-large"),
            manifest_path="/.../data/file_manifest.json",
        )
    """

    def __init__(self, doc_root: str) -> None:
        """
        Args:
            doc_root: Absolute path to the "doc_raw" root folder.
        """
        self.doc_root = Path(doc_root).resolve()
        if not self.doc_root.exists():
            raise FileNotFoundError(f"doc_root does not exist: {self.doc_root}")
        if not self.doc_root.is_dir():
            raise NotADirectoryError(f"doc_root is not a directory: {self.doc_root}")

        # A loader is tied to a root; it returns absolute file paths + text for a subfolder
        self.loader = DocumentLoader(root=self.doc_root)

    # -------------------------------------------------------------------------
    # Public entrypoint
    # -------------------------------------------------------------------------

    def run(
        self,
        subfolder: str,
        store: VectorStoreChroma,
        chunker: Chunker,
        embedder: Embedder,
        manifest_path: str,
        *,
        chunk_size: int = 500,
        overlap: int = 100,
        delete_old_versions: bool = True,
        delete_tombstones: bool = False,
    ) -> IngestionStats:
        """
        Execute a full ingestion cycle for one subfolder under doc_root.

        Steps:
            1) Scan subfolder → build current Records (bytes hash, mtime, size).
            2) Load previous manifest → diff → decide what to process.
            3) For each changed/new file:
                   - chunk (deterministic windows)
                   - embed (batch)
                   - upsert to Chroma (IDs: rel_path::sha256::idx; metadatas)
                   - optionally delete old-version chunks (if path existed with other sha).
            4) Optionally delete tombstone chunks (files removed from disk).
            5) Publish new manifest atomically.

        Returns:
            IngestionStats with useful counters.
        """
        manifest_path = str(Path(manifest_path).resolve())

        # 1) Load documents (absolute path + raw text) from the subfolder.
        docs = self.loader.load_documents(subfolder)  # [(abs_path, text), ...]
        # Build a quick map from abs_path to text for later reuse.
        text_by_abs: Dict[str, str] = {abs_path: text for abs_path, text in docs}

        # 2) Build current Records by hashing files on disk (bytes).
        records_now: List[Record] = []
        for abs_path, _text in docs:
            ap = Path(abs_path)
            # relative path stored in manifest and metadata
            rel_path = ap.relative_to(self.doc_root).as_posix()
            sha = compute_sha256(abs_path)
            st = ap.stat()
            records_now.append({
                "path": rel_path,
                "sha256": sha,
                "mtime": float(st.st_mtime),
                "size": int(st.st_size),
            })

        # 3) Load the previous manifest and compute the diff.
        manifest_prev = load_manifest(manifest_path)
        to_process, unchanged, tombstones = manifest_diff(records_now, manifest_prev)

        # For old-version deletion we need a map: previous[path] -> prev_sha
        prev_by_path: Dict[str, Record] = {
            rec["path"]: rec for rec in manifest_prev.get("files", [])
        }

        # 4) Process changed/new files (chunk → embed → upsert).
        total_chunks = 0
        total_upserts = 0
        total_deleted_old = 0
        total_embedded_bytes = 0  # sum of UTF-8 bytes of all chunk_texts we embed this run

        for rec in to_process:
            rel_path = rec["path"]
            sha_new = rec["sha256"]

            abs_path = (self.doc_root / rel_path).as_posix()
            text = text_by_abs.get(abs_path)
            if text is None:
                # Fallback: if loader skipped for some reason, read file now
                # (should rarely happen, but keeps us robust).
                text = Path(abs_path).read_text(encoding="utf-8", errors="ignore")

            # Build chunks deterministically (same as your ad-hoc test).
            chunks = chunker.split(abs_path, text, chunk_size=chunk_size, overlap=overlap)
            chunk_texts: List[str] = []
            ids: List[str] = []
            metas: List[Dict[str, Any]] = []

            for idx, (_fp, chunk_txt) in enumerate(chunks):
                if not chunk_txt.strip():
                    continue
                chunk_texts.append(chunk_txt)
                ids.append(store.make_chunk_id(rel_path, sha_new, idx))
                metas.append({
                    "path": rel_path,
                    "sha256": sha_new,
                    "chunk_idx": idx,
                    "mtime": rec["mtime"],
                })

            if not chunk_texts:
                # Nothing to embed/store for this file—continue gracefully.
                continue

            # Optional: delete all chunks for the OLD version of this file (same path, different sha).
            if delete_old_versions and rel_path in prev_by_path:
                sha_old = prev_by_path[rel_path]["sha256"]
                if sha_old != sha_new:
                    # Delete by metadata filter (explicit audit)
                    before = self._count_ids(store, rel_path, sha_old)
                    store.delete_where({"$and": [{"path": rel_path}, {"sha256": sha_old}]})
                    after = self._count_ids(store, rel_path, sha_old)
                    total_deleted_old += max(0, before - after)

             # Count bytes that will be embedded (exact UTF-8 length of the texts we send).
            file_embedded_bytes = sum(len(s.encode("utf-8")) for s in chunk_texts)
            total_embedded_bytes += file_embedded_bytes
            # Embed + upsert in batches (embedder handles batching internally if needed).
            vecs = embedder.embed(chunk_texts)
            store.add(ids=ids, vectors=vecs, metadatas=metas)

            total_chunks += len(chunk_texts)
            total_upserts += len(ids)

        # 5) Optionally delete tombstones (files that disappeared from disk).
        total_deleted_tombs = 0
        if delete_tombstones and tombstones:
            for prev_rec in tombstones:
                rel_path = prev_rec["path"]
                sha_prev = prev_rec["sha256"]
                before = self._count_ids(store, rel_path, sha_prev)
                store.delete_where({"$and": [{"path": rel_path}, {"sha256": sha_prev}]})
                after = self._count_ids(store, rel_path, sha_prev)
                total_deleted_tombs += max(0, before - after)

        # 6) Publish a fresh manifest that reflects the CURRENT disk state.
        manifest_new = {
            "version": "1",
            "generated_at": "",   # publish_atomic will stamp UTC if empty
            "files": records_now,
        }
        publish_atomic(manifest_new, manifest_path)

        return IngestionStats(
            files_scanned=len(records_now),
            to_process=len(to_process),
            unchanged=len(unchanged),
            tombstones=len(tombstones),
            chunks_added=total_chunks,
            vectors_upserted=total_upserts,
            deleted_old_versions=total_deleted_old,
            deleted_tombstones=total_deleted_tombs,
            published_manifest_path=manifest_path,
            embedded_bytes=total_embedded_bytes,
        )

    # -------------------------------------------------------------------------
    # Small helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _count_ids(store: VectorStoreChroma, rel_path: str, sha256: str) -> int:
        """
        Return how many IDs exist for a given (path, sha256) pair.
        Used to report how many vectors were deleted during cleanup.
        """
        res = store.collection.get(where={"$and": [{"path": rel_path}, {"sha256": sha256}]}, include=[])
        ids = res.get("ids", []) if res else []
        return len(ids)
```

### ~\ragstream\ingestion\loader.py
```python
"""
DocumentLoader
==============
Responsible for discovering and loading raw files from *data/doc_raw* and its subfolders.
"""

from pathlib import Path
from typing import List, Tuple

class DocumentLoader:
    """Scans the raw-document directory and yields (file_path, file_text) tuples."""

    def __init__(self, root: Path) -> None:
        """
        :param root: Path to the base 'data/doc_raw' folder.
        """
        self.root = root

    def load_documents(self, subfolder: str) -> List[Tuple[str, str]]:
        """
        Load all files from the given subfolder inside data/doc_raw.
        Reads any file extension as plain text.

        :param subfolder: Name of the subfolder (e.g., 'project1').
        :return: List of tuples (absolute_file_path_str, file_text).
        """
        folder_path = self.root / subfolder
        if not folder_path.exists():
            raise FileNotFoundError(f"Input folder does not exist: {folder_path}")

        docs: List[Tuple[str, str]] = []

        for file_path in folder_path.rglob("*"):
            if file_path.is_file():
                try:
                    text = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    # Fallback: try latin-1 to avoid crash on non-UTF8 files
                    text = file_path.read_text(encoding="latin-1")
                docs.append((str(file_path.resolve()), text))

        return docs
```

### ~\ragstream\ingestion\vector_store_chroma.py
```python
# -*- coding: utf-8 -*-
"""
vector_store_chroma.py

Concrete document vector store for RAGstream, backed by Chroma.
This subclass is intentionally thin: it inherits all core mechanics
(add/query/snapshot/delete_where) from ChromaVectorStoreBase and exposes
a couple of convenience helpers that are useful for the ingestion flow.

Usage:
    store = VectorStoreChroma(persist_dir=PATHS.chroma_db)   # default collection "docs"
    store.add(ids=[...], vectors=[...], metadatas=[...])
    top_ids = store.query(vector=q_emb, k=5)
    snap_dir = store.snapshot()  # filesystem snapshot of the persistent DB

Notes:
- We removed the separate "IVectorStore" interface; this concrete class
  (via its base) is now the canonical storage API for documents.
- History policies (selection-only, capacity, eligibility alignment) belong
  to a separate HistoryStoreChroma subclass and are not implemented here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .chroma_vector_store_base import ChromaVectorStoreBase


class VectorStoreChroma(ChromaVectorStoreBase):
    """
    Chroma-backed vector store for document chunks.

    Responsibilities:
      - Provide a ready-to-use, persistent collection (default: "docs").
      - Reuse base add/query/snapshot/delete_where without policy overrides.
      - Offer tiny utilities for common ingestion tasks (e.g., ID formatting).
    """

    def __init__(
        self,
        persist_dir: str,
        collection_name: str = "docs",
        *,
        anonymized_telemetry: bool = False,
    ) -> None:
        """
        Create (or open) the persistent "docs" collection inside persist_dir.

        Args:
            persist_dir: Directory where Chroma keeps its on-disk files.
            collection_name: Logical collection name (default: "docs").
            anonymized_telemetry: Disable/enable Chroma telemetry (default: False).
        """
        super().__init__(
            persist_dir=persist_dir,
            collection_name=collection_name,
            anonymized_telemetry=anonymized_telemetry,
        )

    # ---------------------------------------------------------------------
    # Convenience helpers (optional; used by ingestion code paths)
    # ---------------------------------------------------------------------

    @staticmethod
    def make_chunk_id(rel_path: str, sha256: str, chunk_idx: int) -> str:
        """
        Deterministic ID format used across RAGstream ingestion.
        Example: "docs/Req.md::a1b2c3...::12"
        """
        return f"{rel_path}::{sha256}::{chunk_idx}"

    def delete_file_version(self, rel_path: str, sha256: str) -> int:
        """
        Remove all chunks belonging to a specific file content version.

        This is typically called when a file changes: we ingest the new sha256,
        then delete the old one to prevent duplicate versions.

        Args:
            rel_path: File path relative to the project doc root.
            sha256: Content hash of the OLD version to remove.

        Returns:
            Number of deleted IDs (best-effort; 0 if nothing matched).
        """
        # Look up matching IDs by metadata, then delete by ID for clarity/audit.
        res = self.collection.get(where={"path": rel_path, "sha256": sha256}, include=[])
        ids = res.get("ids", []) if res else []
        if ids:
            self.collection.delete(ids=ids)
        return len(ids)

    # Introspection utilities (handy for tests/diagnostics)

    @property
    def name(self) -> str:
        """Return the collection name (e.g., 'docs')."""
        return self.collection_name

    @property
    def persist_root(self) -> Path:
        """Return the directory containing the on-disk Chroma database."""
        return self.persist_path

    def count(self) -> int:
        """Return total number of stored vectors (documents/chunks)."""
        try:
            return int(self.collection.count())
        except Exception:
            # Older clients may not implement .count(); fall back to get(ids=None)
            res = self.collection.get()  # may be heavy on very large stores
            return len(res.get("ids", [])) if res else 0
```


## /home/rusbeh_ab/project/RAGstream/ragstream/orchestration

### ~\ragstream\orchestration\agent_factory.py
```python
# -*- coding: utf-8 -*-
"""
AgentFactory
============


- This is the single place where AgentPrompt objects are created from JSON configs.
- It hides all file-system details (where JSON lives, how paths are built).
- It also caches created agents, so JSON is read only once per (agent_id, version).

Usage model (high level):
- Controller creates ONE AgentFactory instance at startup.
- Each Agent (A2, A3, ...) asks this factory for its AgentPrompt:
    factory.get_agent("a2_promptshaper", "001")
- The returned AgentPrompt is then used to compose/parse LLM calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ragstream.utils.logging import SimpleLogger
from ragstream.orchestration.agent_prompt import AgentPrompt


class AgentFactory:
    """
    Central factory for building and caching AgentPrompt instances.

    Design goals:
    - Neutral: knows nothing about A2/A3/etc. beyond their (agent_id, version).
    - File-based: loads JSON configs from data/agents/<agent_id>/<version>.json.
    - Cached: Agents are constructed once and reused for the lifetime of the factory.
    """

    def __init__(self, agents_root: Optional[Path] = None) -> None:
        """
        Initialize the factory.

        Parameters
        ----------
        agents_root:
            Optional base directory where all agent JSON configs live.
            If None, we derive it from the package layout assuming the repo root
            looks like:

                RAGstream/
                    data/
                        agents/
                            a2_promptshaper/001.json
                    ragstream/
                        orchestration/
                            agent_factory.py
                        ...

            In that case:
                repo_root = Path(__file__).resolve().parents[2]
                agents_root = repo_root / "data" / "agents"
        """
        if agents_root is None:
            # Go from ragstream/orchestration/agent_factory.py
            #   -> ragstream/
            #   -> RAGstream/ (repo root)
            repo_root = Path(__file__).resolve().parents[2]
            agents_root = repo_root / "data" / "agents"

        self.agents_root: Path = agents_root
        self._cache: Dict[Tuple[str, str], AgentPrompt] = {}

        SimpleLogger.info(f"AgentFactory initialized with agents_root={self.agents_root}")

    # ------------------------------------------------------------------
    # Internal path builder
    # ------------------------------------------------------------------

    def _build_config_path(self, agent_id: str, version: str) -> Path:
        """
        Internal helper: compute the JSON config path for a given agent_id/version.

        Example:
            agent_id = "a2_promptshaper"
            version  = "001"
        Path becomes:
            <agents_root>/a2_promptshaper/001.json
        """
        return self.agents_root / agent_id / f"{version}.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_config(self, agent_id: str, version: str) -> Dict[str, Any]:
        """
        Load the raw JSON config for a given agent_id and version.

        Responsibilities:
        - Build the file path.
        - Read JSON from disk.
        - Raise a clear error if the file does not exist or is invalid.

        This method does NOT cache anything; it just returns the config dict.
        """
        cfg_path = self._build_config_path(agent_id, version)

        if not cfg_path.is_file():
            msg = f"AgentFactory: config not found for {agent_id=} {version=} at {cfg_path}"
            SimpleLogger.error(msg)
            raise FileNotFoundError(msg)

        try:
            with cfg_path.open("r", encoding="utf-8") as f:
                config: Dict[str, Any] = json.load(f)
        except Exception as exc:
            msg = f"AgentFactory: failed to load JSON config from {cfg_path}: {exc}"
            SimpleLogger.error(msg)
            raise

        return config

    def get_agent(self, agent_id: str, version: str = "001") -> AgentPrompt:
        """
        Return an AgentPrompt instance for the given (agent_id, version).

        Responsibilities:
        - Check the in-memory cache first.
        - If not present:
            - Load the JSON config.
            - Build AgentPrompt via AgentPrompt.from_config(config).
            - Store it in the cache.
        - Always return the same AgentPrompt instance for the same key.

        This ensures:
        - We only hit the file system once per agent/version.
        - All callers share the same AgentPrompt configuration object.
        """
        key = (agent_id, version)
        if key in self._cache:
            return self._cache[key]

        config = self.load_config(agent_id, version)
        agent = AgentPrompt.from_config(config)
        self._cache[key] = agent

        SimpleLogger.info(
            f"AgentFactory: created AgentPrompt for agent_id={agent_id}, version={version}"
        )
        return agent

    def clear_cache(self) -> None:
        """
        Clear the internal cache of AgentPrompt instances.

        Why this exists:
        - Mostly for testing or advanced scenarios (e.g. live-reloading configs).
        - In normal operation you probably never call this.

        Behavior:
        - Simply empties the cache dict; no further side effects.
        """
        self._cache.clear()
        SimpleLogger.info("AgentFactory: cache cleared")
```

### ~\ragstream\orchestration\agent_prompt.py
```python
# -*- coding: utf-8 -*-
"""
AgentPrompt
===========
Main neutral prompt engine used by all LLM-using agents.

This file only:
- Defines AgentPrompt (the main class).
- Defines AgentPromptValidationError (small helper exception).
- Delegates JSON parsing, field config extraction, normalization and text
  composition to helper modules in agent_prompt_helpers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Set

from ragstream.utils.logging import SimpleLogger
from ragstream.orchestration.agent_prompt_helpers.config_loader import (
    extract_field_config,
)
from ragstream.orchestration.agent_prompt_helpers.schema_map import (
    build_result_key_map,
)
from ragstream.orchestration.agent_prompt_helpers.json_parser import (
    extract_json_object,
)
from ragstream.orchestration.agent_prompt_helpers.field_normalizer import (
    normalize_one,
    normalize_many,
)
from ragstream.orchestration.agent_prompt_helpers.compose_texts import (
    build_system_text,
    build_user_text_for_chooser,
)


class AgentPromptValidationError(Exception):
    """Raised when the LLM output cannot be parsed or validated."""


class AgentPrompt:
    """
    Neutral prompt engine.

    Configuration is passed in once (from JSON via AgentFactory) and is read-only.
    No per-call state is stored inside the instance; all inputs for a run are passed
    to compose()/parse() as parameters.
    """

    def __init__(
        self,
        agent_name: str,
        version: str,
        mode: str,
        system_text: str,
        purpose_text: str,
        output_schema: Dict[str, Any],
        enums: Dict[str, List[str]],
        defaults: Dict[str, Any],
        cardinality: Dict[str, str],
        option_descriptions: Dict[str, Dict[str, str]],
        option_labels: Dict[str, Dict[str, str]],
        model_name: str,
        temperature: float,
        max_output_tokens: int,
    ) -> None:
        self.agent_name: str = agent_name
        self.version: str = version
        self.mode: str = mode  # "chooser" | "writer" | "extractor" | "scorer"
        self.system_text: str = system_text
        self.purpose_text: str = purpose_text
        self.output_schema: Dict[str, Any] = output_schema

        # Per-field configuration
        self.enums: Dict[str, List[str]] = enums
        self.defaults: Dict[str, Any] = defaults
        self.cardinality: Dict[str, str] = cardinality
        self.option_descriptions: Dict[str, Dict[str, str]] = option_descriptions
        self.option_labels: Dict[str, Dict[str, str]] = option_labels

        # Model configuration
        self.model_name: str = model_name
        self.temperature: float = temperature
        self.max_output_tokens: int = max_output_tokens

        # Derived mapping: field_id -> result_key in JSON
        self._result_keys: Dict[str, str] = build_result_key_map(output_schema)

        if self.mode not in ("chooser", "writer", "extractor", "scorer"):
            SimpleLogger.error(f"AgentPrompt[{self.agent_name}] unknown mode: {self.mode}")

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "AgentPrompt":
        """
        Build AgentPrompt from a JSON config dict as stored in data/agents/...

        Expects an A2-style schema with:
          - agent_meta
          - prompt_profile
          - llm_config
          - fields
          - output_schema
        """
        agent_meta = config.get("agent_meta", {})
        prompt_profile = config.get("prompt_profile", {})
        llm_cfg = config.get("llm_config", {})
        fields_cfg = config.get("fields", []) or []
        output_schema = config.get("output_schema", {}) or {}

        agent_name = agent_meta.get("agent_id") or agent_meta.get("agent_name") or "unknown_agent"
        version = str(agent_meta.get("version", "000"))
        mode = agent_meta.get("agent_type", "chooser")

        system_text = prompt_profile.get("system_role", "")
        purpose_text = prompt_profile.get("agent_purpose", "")

        model_name = llm_cfg.get("model_name", "gpt-5.1-mini")
        temperature = float(llm_cfg.get("temperature", 0.0))
        max_tokens = int(llm_cfg.get("max_tokens", 256))

        enums, defaults, cardinality, opt_desc, opt_labels = extract_field_config(fields_cfg)

        return cls(
            agent_name=agent_name,
            version=version,
            mode=mode,
            system_text=system_text,
            purpose_text=purpose_text,
            output_schema=output_schema,
            enums=enums,
            defaults=defaults,
            cardinality=cardinality,
            option_descriptions=opt_desc,
            option_labels=opt_labels,
            model_name=model_name,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def model(self) -> str:
        """Model name used by llm_client."""
        return self.model_name

    @property
    def max_tokens(self) -> int:
        """Maximum output tokens for llm_client."""
        return self.max_output_tokens

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def compose(
        self,
        input_payload: Dict[str, Any],
        active_fields: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        """
        Build SYSTEM + USER messages and the response_format for the LLM.

        input_payload:
            Dict with keys like "task", "purpose", "context" (from SuperPrompt).

        active_fields:
            Optional list of field_ids that are "live" for this call, decided by A2.
            If None, all known enum fields are considered active.
        """
        if self.mode != "chooser":
            raise AgentPromptValidationError(
                f"AgentPrompt[{self.agent_name}] compose() currently only supports mode='chooser'"
            )

        active_set: Set[str]
        if active_fields is None:
            active_set = set(self.enums.keys())
        else:
            active_set = set(f for f in active_fields if f in self.enums)

        system_text = build_system_text(
            system_text=self.system_text,
            purpose_text=self.purpose_text,
            agent_name=self.agent_name,
            version=self.version,
        )

        user_text = build_user_text_for_chooser(
            input_payload=input_payload,
            enums=self.enums,
            cardinality=self.cardinality,
            option_descriptions=self.option_descriptions,
            option_labels=self.option_labels,
            result_keys=self._result_keys,
            active_fields=sorted(active_set),
        )

        messages = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ]
        response_format = {"type": "json_object"}

        return messages, response_format

    def parse(
        self,
        raw_output: Any,
        active_fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Parse and validate the LLM raw output into a clean Python dict.

        raw_output:
            Raw LLM response. Usually a string; treated as JSON or JSON-like.

        active_fields:
            Optional list of field_ids that were active for this call.
            If None, all enum fields are considered active.

        Returns
        -------
        result:
            Dict with normalized values per field_id, e.g.:
            {
                "system": ["rag_architect", "prompt_engineer"],
                "audience": "self_power_user",
                "tone": "neutral_analytical",
                "depth": "exhaustive",
                "confidence": "high",
            }
        """
        if self.mode != "chooser":
            raise AgentPromptValidationError(
                f"AgentPrompt[{self.agent_name}] parse() currently only supports mode='chooser'"
            )

        if active_fields is None:
            active_set: Set[str] = set(self.enums.keys())
        else:
            active_set = set(f for f in active_fields if f in self.enums)

        json_obj = extract_json_object(raw_output)

        result: Dict[str, Any] = {}
        for field_id, allowed in self.enums.items():
            if field_id not in active_set:
                # Inactive: caller (A2) keeps the existing value (e.g. user-set).
                continue

            result_key = self._result_keys.get(field_id, field_id)
            card = self.cardinality.get(field_id, "one")
            default_value = self.defaults.get(field_id)

            raw_value = json_obj.get(result_key, None)

            if card == "many":
                normalized = normalize_many(
                    field_id=field_id,
                    raw_value=raw_value,
                    allowed=allowed,
                    default_value=default_value,
                )
            else:
                normalized = normalize_one(
                    field_id=field_id,
                    raw_value=raw_value,
                    allowed=allowed,
                    default_value=default_value,
                )

            result[field_id] = normalized

        return result
```

### ~\ragstream\orchestration\llm_client.py
```python
# ragstream/orchestration/llm_client.py
# -*- coding: utf-8 -*-
"""
LLMClient — thin wrapper around an LLM provider.

Current implementation:
- Uses OpenAI Python client v1 (OpenAI() + client.chat.completions.create).
- Reads OPENAI_API_KEY from environment (or optional api_key in __init__).
- Supports optional JSON-mode: if response_format={"type": "json_object"},
  it will attempt json.loads on the returned content and give you a dict.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Union
import os
import json

from ragstream.utils.logging import SimpleLogger

try:
    # New v1-style client
    from openai import OpenAI  # type: ignore[import]
except ImportError:  # pragma: no cover - import guard
    OpenAI = None  # type: ignore[assignment]

JsonDict = Dict[str, Any]


class LLMClient:
    """
    Neutral LLM gateway.

    You give it:
      - messages: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
      - model_name, temperature, max_output_tokens
      - optional response_format (e.g. {"type": "json_object"})

    It returns:
      - string (raw content) OR
      - dict (if JSON-mode used and parsing succeeded)
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        key = api_key or os.getenv("OPENAI_API_KEY") or ""
        self._client: Optional[OpenAI] = None  # type: ignore[type-arg]

        if OpenAI is None:
            SimpleLogger.info(
                "LLMClient: 'openai' v1 client not installed. Any LLM call will fail until you "
                "install it (e.g. 'pip install openai')."
            )
            return

        if not key:
            SimpleLogger.info(
                "LLMClient: OPENAI_API_KEY not set. Any LLM call will fail until you set it."
            )
            return

        try:
            # v1 client: hold a single instance
            self._client = OpenAI(api_key=key)
            SimpleLogger.info("LLMClient: OpenAI client initialised (v1 API).")
        except Exception as exc:
            SimpleLogger.error(f"LLMClient: failed to initialise OpenAI client: {exc!r}")
            self._client = None

    def chat(
            self,
            *,
            messages,
            model_name: str,
            temperature: float,
            max_output_tokens: int,
            response_format: dict | None = None,
    ):
        """
        Thin wrapper over OpenAI chat.completions.

        - Uses max_completion_tokens (new API) instead of max_tokens.
        - For gpt-5* reasoning models, we do NOT send temperature (it is unsupported).
        """
        if self._client is None:
            raise RuntimeError("LLMClient: OpenAI client is not initialised")

        # Base kwargs for the API call
        kwargs: dict = {
            "model": model_name,
            "messages": messages,
            "max_completion_tokens": max_output_tokens,
        }

        if response_format is not None:
            kwargs["response_format"] = response_format

        # temperature is illegal for gpt-5* reasoning models, allowed for others
        if temperature is not None and not model_name.startswith("gpt-5"):
            kwargs["temperature"] = temperature

        resp = self._client.chat.completions.create(**kwargs)
        # AgentPrompt.parse() expects the raw content (string or JSON-string)
        content = resp.choices[0].message.content
        return content if isinstance(content, str) else str(content or "")

```

### ~\ragstream\orchestration\prompt_builder.py
```python
"""
PromptBuilder
=============
Composes the Super-Prompt with fixed authority order:
[Hard Rules] → [Project Memory] → [❖ FILES] → [S_ctx] → [Task/Mode]
(RECENT HISTORY may be shown for continuity; non-authoritative.)
"""
from typing import List, Optional, Dict

class PromptBuilder:
    def build(self, question: str, files_block: Optional[str], s_ctx: List[str], shape: Optional[Dict] = None) -> str:
        return "PROMPT"
```

### ~\ragstream\orchestration\super_prompt.py
```python
# -*- coding: utf-8 -*-
"""
SuperPrompt (v1) — central prompt object (manual __init__, no dataclass).
Place at: ragstream/orchestration/super_prompt.py

Notes (agreed pipeline choices; for reference only):
- Retrieval aggregation: LogAvgExp (length-normalized LogSumExp) with τ = 9 over per-piece cosine sims.
- Re-ranker: cross-encoder/ms-marco-MiniLM-L-6-v2 on (Prompt_MD, chunk_text).
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Literal
from enum import Enum

# Lifecycle stages for this SuperPrompt (fixed vocabulary)
Stage = Literal["raw", "preprocessed", "a2", "retrieval", "reranked", "a3", "a4", "a5"]


class A3ChunkStatus(str, Enum):
    SELECTED = "selected"
    DISCARDED = "discarded"
    DUPLICATED = "duplicated"


class SuperPrompt:
    __slots__ = (
        # session / lifecycle
        "stage",                 # string in Stage: current lifecycle state (e.g., "retrieval", "a3")
        "model_target",          # string or None: target LLM/model name for this session
        "history_of_stages",     # list[str]: append-only history of visited stages (e.g., ["raw","preprocessed","a2",...])

        # canonical prompt data
        "body",                  # dict: canonical fields from user (system, task, audience, tone, depth, context, purpose, format, text)
        "extras",                # dict: user-defined fields

        # retrieval artifacts
        "base_context_chunks",   # list[Chunk]: authoritative set of retrieved Chunk objects (combined from history + long-term memory)
        "views_by_stage",        # dict[str, list[tuple[str, float, A3ChunkStatus]]]: per stage, ordered (chunk_id, stage_score, stage_status)
        "final_selection_ids",   # list[str]: current chosen chunk_ids (from latest view after filters + token budget)

        # recent conversation (separate block)
        "recentConversation",    # dict: e.g., {"body": full transcript string, "pairs_count": N, "range": (start_idx, end_idx)}

        # rendered strings (set externally when sending to LLM; may be kept empty until render time)
        "System_MD",             # string: high-authority system/config block rendered from body (role/tone/depth/rules)
        "Prompt_MD",             # string: normalized user ask rendered from body (task/purpose/context/format)
        "S_CTX_MD",              # string: short distilled summary from final_selection_ids (facts/constraints/open issues)
        "Attachments_MD",        # string: formatted raw excerpts with provenance fences from final_selection_ids
        "prompt_ready"           # string: fully composed prompt ready to display/send.
    )

    def __init__(
        self,
        *,
        stage: Stage = "raw",
        model_target: Optional[str] = None,
    ) -> None:
        # session / lifecycle
        self.stage: Stage = stage
        self.model_target: Optional[str] = model_target
        self.history_of_stages: List[str] = []  # filled by caller/controller as stages are completed

        # canonical prompt data (each instance gets its own dict)
        self.body: Dict[str, Optional[str]] = {
            "system": "consultant",   # must-use default
            "task": None,             # must be set by caller
            "audience": None,
            "role": None,
            "tone": "neutral",
            "depth": "high",
            "context": None,
            "purpose": None,
            "format": None,
            "text": None,
        }
        self.extras: Dict[str, Any] = {}        # free-form, user-defined metadata

        # retrieval artifacts
        self.base_context_chunks: List["Chunk"] = []  # authoritative working set of Chunk objects (no duplicates)

        # stage name -> ordered list of per-chunk stage snapshots:
        # (chunk_id, stage_score, stage_status)
        #
        # Intended stage-local meaning:
        # - Retrieval:
        #     stage_score  = cosine similarity score
        #     stage_status = A3ChunkStatus.SELECTED
        #
        # - ReRanker:
        #     stage_score  = reranker score
        #     stage_status = A3ChunkStatus.SELECTED for kept chunks,
        #                    optionally A3ChunkStatus.DISCARDED for cut-off chunks
        #
        # - A3:
        #     stage_score  = 1.0 for pass / keep, 0.0 for reject
        #     stage_status = A3ChunkStatus.SELECTED / DISCARDED / DUPLICATED
        #
        # The list is always ordered according to the active stage view.
        self.views_by_stage: Dict[str, List[tuple[str, float, A3ChunkStatus]]] = {}

        self.final_selection_ids: List[str] = []        # the ids chosen for render after all filters/budgets

        # recent conversation block (kept separate from retrieved context)
        self.recentConversation: Dict[str, Any] = {}    # e.g., {"body": "...", "pairs_count": 3, "range": (12,14)}

        # rendered strings (filled by the caller at send time; may remain empty otherwise)
        self.System_MD: str = ""       # rendered from body (system/role/tone/depth)
        self.Prompt_MD: str = ""       # rendered from body (task/purpose/context/format)
        self.S_CTX_MD: str = ""        # rendered summary from final_selection_ids
        self.Attachments_MD: str = ""  # rendered excerpts from final_selection_ids with provenance
        self.prompt_ready: str = ""    # fully composed prompt ready to display/send

    def compose_prompt_ready(self) -> str:
        """
        Central render method for the current SuperPrompt.

        Purpose:
        - Build a single display/send-ready markdown text from the current object state.
        - Work already for PreProcessing and A2, where no chunks exist yet.
        - Also work for Retrieval and later stages, where chunk-based context may exist.
        - Replace the stage-local external compose functions in the future, so prompt
          rendering lives in one central place.

        Current behaviour:
        - Rebuild self.System_MD from self.body
        - Rebuild self.Prompt_MD from self.body
        - Keep self.S_CTX_MD and self.Attachments_MD if some later stage has already set them
        - If no later-stage attachments exist, render a simple "Related Context" section
          from the currently selected chunks
        - Write the final combined markdown into self.prompt_ready

        Returns:
            The final composed markdown string.
        """
        self.System_MD = self._render_system_md()
        self.Prompt_MD = self._render_prompt_md()

        parts: List[str] = []

        if self.System_MD:
            parts.append(self.System_MD)

        if self.Prompt_MD:
            parts.append(self.Prompt_MD)

        if self.S_CTX_MD:
            parts.append(self.S_CTX_MD)

        if self.Attachments_MD:
            parts.append(self.Attachments_MD)
        else:
            related_context_md = self._render_related_context_md()
            if related_context_md:
                parts.append(related_context_md)

        self.prompt_ready = "\n\n".join(parts).strip()
        return self.prompt_ready

    def _render_system_md(self) -> str:
        """
        Render the high-authority system/config part from self.body.

        This method is intentionally deterministic and simple.
        It does not depend on retrieval artifacts.
        """
        lines: List[str] = []

        system_value = (self.body.get("system") or "").strip()
        role_value = (self.body.get("role") or "").strip()
        audience_value = (self.body.get("audience") or "").strip()
        tone_value = (self.body.get("tone") or "").strip()
        depth_value = (self.body.get("depth") or "").strip()

        if system_value:
            lines.append("## System")
            lines.append(system_value)

        config_lines: List[str] = []

        if role_value:
            config_lines.append(f"- Role: {role_value}")
        if audience_value:
            config_lines.append(f"- Audience: {audience_value}")
        if tone_value:
            config_lines.append(f"- Tone: {tone_value}")
        if depth_value:
            config_lines.append(f"- Depth: {depth_value}")

        if config_lines:
            if lines:
                lines.append("")
            lines.append("## Configuration")
            lines.extend(config_lines)

        return "\n".join(lines).strip()

    def _render_prompt_md(self) -> str:
        """
        Render the user-facing prompt part from self.body.

        This method is designed to cover:
        - raw / preprocessed / a2 stages without any chunk context
        - later stages as well, because the canonical prompt body remains the same
        """
        lines: List[str] = []

        task_value = (self.body.get("task") or "").strip()
        purpose_value = (self.body.get("purpose") or "").strip()
        context_value = (self.body.get("context") or "").strip()
        format_value = (self.body.get("format") or "").strip()
        text_value = (self.body.get("text") or "").strip()

        if task_value:
            lines.append("## Task")
            lines.append(task_value)
            lines.append("")

        if purpose_value:
            lines.append("## Purpose")
            lines.append(purpose_value)
            lines.append("")

        if context_value:
            lines.append("## Context")
            lines.append(context_value)
            lines.append("")

        if format_value:
            lines.append("## Format")
            lines.append(format_value)
            lines.append("")

        if text_value:
            lines.append("## Text")
            lines.append(text_value)
            lines.append("")

        return "\n".join(lines).strip()

    def _format_score(self, score: float) -> str:
        """
        Format numeric scores compactly for the Related Context headers.
        """
        return f"{float(score):.4f}".rstrip("0").rstrip(".")

    def _render_related_context_md(self) -> str:
        """
        Render a simple chunk-based context preview from the current selected chunks.

        Design intention:
        - The GUI should show only the selected chunk texts.
        - During Retrieval, show only Rt-Score in the chunk header.
        - During ReRanker, show Rk-Score first and Rt-Score second.
        - For other stages, keep the header simple.
        - Technical metadata such as ID, source, status, and span remain
          inside SuperPrompt as internal structured data and are not rendered here.
        - If no chunks exist yet, this method returns an empty string and the caller
          simply skips the section.
        """
        ordered_chunks = self._get_ordered_context_chunks()
        if not ordered_chunks:
            return ""

        retrieval_score_map: Dict[str, float] = {
            chunk_id: float(score)
            for chunk_id, score, _status in self.views_by_stage.get("retrieval", [])
        }

        reranked_score_map: Dict[str, float] = {
            chunk_id: float(score)
            for chunk_id, score, _status in self.views_by_stage.get("reranked", [])
        }

        lines: List[str] = []
        lines.append("## Related Context")
        lines.append("")

        chunk_counter = 1
        for chunk_obj in ordered_chunks:
            header = f"### Chunk {chunk_counter}"

            if self.stage == "retrieval":
                rt_score = retrieval_score_map.get(chunk_obj.id)
                if rt_score is not None:
                    header = f"{header} [Rt-Score={self._format_score(rt_score)}]"

            elif self.stage == "reranked":
                rk_score = reranked_score_map.get(chunk_obj.id)
                rt_score = retrieval_score_map.get(chunk_obj.id)

                if rk_score is not None and rt_score is not None:
                    header = (
                        f"{header} "
                        f"[Rk-Score={self._format_score(rk_score)}, "
                        f"Rt-Score={self._format_score(rt_score)}]"
                    )
                elif rk_score is not None:
                    header = f"{header} [Rk-Score={self._format_score(rk_score)}]"

            lines.append(header)
            lines.append("")
            lines.append(chunk_obj.snippet.strip())
            lines.append("")
            chunk_counter += 1

        return "\n".join(lines).strip()

    def _get_ordered_context_chunks(self) -> List["Chunk"]:
        """
        Return the currently relevant chunks in the intended display order.

        Order policy:
        1. If final_selection_ids exists, use that order.
        2. Otherwise, if the current stage has a view in views_by_stage, use that order.
        3. Otherwise, fall back to the raw order of base_context_chunks.

        This keeps the render logic general enough for Retrieval, ReRanker, A3,
        and future later stages.
        """
        if not self.base_context_chunks:
            return []

        chunk_by_id: Dict[str, "Chunk"] = {}
        for chunk_obj in self.base_context_chunks:
            chunk_by_id[chunk_obj.id] = chunk_obj

        ordered_chunks: List["Chunk"] = []

        if self.final_selection_ids:
            for chunk_id in self.final_selection_ids:
                if chunk_id in chunk_by_id:
                    ordered_chunks.append(chunk_by_id[chunk_id])
            return ordered_chunks

        if self.stage in self.views_by_stage:
            stage_rows = self.views_by_stage[self.stage]
            for row in stage_rows:
                chunk_id = row[0]
                if chunk_id in chunk_by_id:
                    ordered_chunks.append(chunk_by_id[chunk_id])
            return ordered_chunks

        for chunk_obj in self.base_context_chunks:
            ordered_chunks.append(chunk_obj)

        return ordered_chunks

    def __repr__(self) -> str:
        return f"SuperPrompt(stage={self.stage!r})"
```

### ~\ragstream\orchestration\agent_prompt_helpers\compose_texts.py
```python
# -*- coding: utf-8 -*-
"""
compose_texts
=============

Why this helper exists:
- Composing SYSTEM and USER messages is text-heavy and easy to clutter the
  main AgentPrompt class.
- We want the core class to read like a high-level story, and all text
  formatting to live here.

What it does:
- Provides `build_system_text(...)` for the SYSTEM message.
- Provides `build_user_text_for_chooser(...)` for the USER message when
  agent_type == "chooser".
"""

from __future__ import annotations

from typing import Any, Dict, List


def build_system_text(
    system_text: str,
    purpose_text: str,
    agent_name: str,
    version: str,
) -> str:
    """
    Build the SYSTEM message content for the LLM.
    """
    lines: List[str] = []

    if system_text:
        lines.append(system_text.strip())

    if purpose_text:
        lines.append("")
        lines.append(f"Agent purpose: {purpose_text.strip()}")

    lines.append("")
    lines.append(f"Agent id: {agent_name} v{version}")
    lines.append(
        "You never answer the user's question directly. "
        "You ONLY choose configuration values as instructed."
    )
    lines.append(
        "You MUST respond with a single JSON object and nothing else "
        "(no prose, no comments)."
    )

    return "\n".join(lines)


def build_user_text_for_chooser(
    input_payload: Dict[str, Any],
    enums: Dict[str, List[str]],
    cardinality: Dict[str, str],
    option_descriptions: Dict[str, Dict[str, str]],
    option_labels: Dict[str, Dict[str, str]],
    result_keys: Dict[str, str],
    active_fields: List[str],
) -> str:
    """
    Build the USER message content for a chooser-type agent.

    Shows:
    - Current SuperPrompt state (task, purpose, context, ...).
    - For each active field: allowed option ids plus label/description for clarity, and expected JSON shape.
    """
    lines: List[str] = []

    # Show SuperPrompt state
    lines.append("Current SuperPrompt state:")
    for key, value in input_payload.items():
        lines.append(f"- {key}: {value!r}")
    lines.append("")

    # Explain the decision task
    lines.append(
        "Based on this, choose values for the following configuration fields. "
        "For each field, you MUST choose only from the allowed option ids."
    )
    lines.append("")

    # List fields and options
    for field_id in active_fields:
        allowed = enums.get(field_id, [])
        if not allowed:
            continue

        card = cardinality.get(field_id, "one")
        result_key = result_keys.get(field_id, field_id)

        lines.append(f"Field '{field_id}' (JSON key: '{result_key}'):")

        if card == "many":
            lines.append(
                "  - Type: array of one or more option ids (strings) from the list below."
            )
        else:
            lines.append("  - Type: single option id (string) from the list below.")

        labels = option_labels.get(field_id, {})
        descs = option_descriptions.get(field_id, {})
        for opt_id in allowed:
            label = labels.get(opt_id)
            desc = descs.get(opt_id)
            if label and desc:
                lines.append(f"    * {opt_id}: {label} — {desc}")
            elif label:
                lines.append(f"    * {opt_id}: {label}")
            elif desc:
                lines.append(f"    * {opt_id}: {desc}")
            else:
                lines.append(f"    * {opt_id}")

        lines.append("")

    # Describe expected JSON keys and shapes
    lines.append("Return ONLY a JSON object with keys:")
    for field_id in active_fields:
        result_key = result_keys.get(field_id, field_id)
        card = cardinality.get(field_id, "one")
        if card == "many":
            lines.append(f"- '{result_key}': array of option ids (strings).")
        else:
            lines.append(f"- '{result_key}': single option id (string).")

    lines.append("")
    lines.append("Do NOT add explanations, comments or extra keys. JSON only.")

    return "\n".join(lines)
```

### ~\ragstream\orchestration\agent_prompt_helpers\config_loader.py
```python
# -*- coding: utf-8 -*-
"""
config_loader
=============

Why this helper exists:
- Agent JSON configs contain a 'fields' list with enums, defaults and cardinality.
- Converting this list into clean Python dictionaries is generic logic and should
  not clutter AgentPrompt.

What it does:
- Provides a single function `extract_field_config(fields_cfg)` that returns:
  - enums[field_id] = list of allowed option ids.
  - defaults[field_id] = default value from config (may be str or list).
  - cardinality[field_id] = "one" or "many".
  - option_labels[field_id][opt_id] = human-readable label (optional).
  - option_descriptions[field_id][opt_id] = human-readable description (optional).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def extract_field_config(
    fields_cfg: List[Dict[str, Any]]
) -> Tuple[
    Dict[str, List[str]],
    Dict[str, Any],
    Dict[str, str],
    Dict[str, Dict[str, str]],
    Dict[str, Dict[str, str]],
]:
    """
    Convert the JSON 'fields' list into enums/defaults/cardinality/option_descriptions/option_labels.

    - enums[field_id] = ["opt1", "opt2", ...]
    - defaults[field_id] = default value from config (may be str or list)
    - cardinality[field_id] = "one" | "many"
    - option_descriptions[field_id][opt_id] = description (if present)
    - option_labels[field_id][opt_id] = label (if present)
    """
    enums: Dict[str, List[str]] = {}
    defaults: Dict[str, Any] = {}
    cardinality: Dict[str, str] = {}
    option_descriptions: Dict[str, Dict[str, str]] = {}
    option_labels: Dict[str, Dict[str, str]] = {}

    for field in fields_cfg:
        field_id = field.get("id")
        if not field_id:
            continue

        field_type = field.get("type", "enum")
        if field_type != "enum":
            # For v1, AgentPrompt only supports enum-based Chooser behaviour.
            # Writer / Extractor / Scorer can be handled later.
            continue

        options = field.get("options", []) or []
        allowed_ids: List[str] = []
        descs: Dict[str, str] = {}
        labels: Dict[str, str] = {}

        for opt in options:
            opt_id = opt.get("id")
            if not opt_id:
                continue
            allowed_ids.append(opt_id)
            if "label" in opt:
                labels[opt_id] = opt["label"]
            if "description" in opt:
                descs[opt_id] = opt["description"]

        if allowed_ids:
            enums[field_id] = allowed_ids
            if labels:
                option_labels[field_id] = labels
            if descs:
                option_descriptions[field_id] = descs

        defaults[field_id] = field.get("default")
        cardinality[field_id] = field.get("cardinality", "one")

    return enums, defaults, cardinality, option_descriptions, option_labels
```

### ~\ragstream\orchestration\agent_prompt_helpers\field_normalizer.py
```python
# -*- coding: utf-8 -*-
"""
field_normalizer
================

Why this helper exists:
- Every Chooser agent must clean and validate what the LLM returns.
- This logic (enforcing enums, cardinality and defaults) is generic and should
  not sit inside the main AgentPrompt file.

What it does:
- Provides `normalize_one()` for single-choice enum fields.
- Provides `normalize_many()` for multi-choice enum fields.
- Both functions take the allowed options and default value and always return
  a safe, normalized result.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ragstream.utils.logging import SimpleLogger


def normalize_one(
    field_id: str,
    raw_value: Any,
    allowed: List[str],
    default_value: Any,
) -> Optional[str]:
    """
    Normalize a single-choice enum field to one allowed id.

    Rules:
    - If raw_value is a string in allowed → use it.
    - If raw_value is a list → pick the first element that is in allowed.
    - Else → fall back to default_value if valid; otherwise first allowed or None.
    """
    chosen: Optional[str] = None

    if isinstance(raw_value, str) and raw_value in allowed:
        chosen = raw_value
    elif isinstance(raw_value, list):
        for item in raw_value:
            if isinstance(item, str) and item in allowed:
                chosen = item
                break

    if chosen is None:
        if isinstance(default_value, str) and default_value in allowed:
            chosen = default_value
        elif allowed:
            chosen = allowed[0]

    if chosen is None:
        SimpleLogger.error(f"field_normalizer.normalize_one: no valid value for field '{field_id}'")

    return chosen


def normalize_many(
    field_id: str,
    raw_value: Any,
    allowed: List[str],
    default_value: Any,
) -> List[str]:
    """
    Normalize a multi-choice enum field to a list of allowed ids.

    Rules:
    - If raw_value is a list → keep only items that are allowed and strings.
    - If raw_value is a single string → convert to [value] if allowed.
    - If after filtering we have nothing → use default_value if list/str and valid.
    - If still nothing and allowed is non-empty → use [allowed[0]] as last resort.
    """
    selected: List[str] = []

    if isinstance(raw_value, list):
        for item in raw_value:
            if isinstance(item, str) and item in allowed and item not in selected:
                selected.append(item)
    elif isinstance(raw_value, str) and raw_value in allowed:
        selected.append(raw_value)

    if not selected:
        if isinstance(default_value, list):
            for item in default_value:
                if isinstance(item, str) and item in allowed and item not in selected:
                    selected.append(item)
        elif isinstance(default_value, str) and default_value in allowed:
            selected.append(default_value)

    if not selected and allowed:
        selected.append(allowed[0])

    if not selected:
        SimpleLogger.error(
            f"field_normalizer.normalize_many: no valid values for field '{field_id}'"
        )

    return selected
```

### ~\ragstream\orchestration\agent_prompt_helpers\json_parser.py
```python
# -*- coding: utf-8 -*-
"""
json_parser
===========

Why this helper exists:
- LLMs often return messy strings: JSON plus explanations or extra text.
- AgentPrompt should not be cluttered with low-level parsing details.

What it does:
- Provides a single function `extract_json_object(raw_output)` that tries
  to extract and load a JSON object.
- On failure it returns {} instead of raising, so caller can fall back to defaults.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from ragstream.utils.logging import SimpleLogger


def extract_json_object(raw_output: Any) -> Dict[str, Any]:
    """
    Best-effort extraction of a JSON object from the raw LLM output.

    Strategy:
    - If already a dict: return as-is.
    - If a string: try json.loads directly.
    - If that fails: try to locate the first '{' and last '}' and parse that slice.
    - On failure: return {} (caller will fall back to defaults).
    """
    if isinstance(raw_output, dict):
        return raw_output

    if not isinstance(raw_output, str):
        SimpleLogger.error("json_parser.extract_json_object: raw_output is neither dict nor str")
        return {}

    text = raw_output.strip()

    # First attempt: direct JSON
    try:
        return json.loads(text)
    except Exception:
        pass

    # Second attempt: find JSON substring
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            SimpleLogger.error(
                "json_parser.extract_json_object: failed to parse JSON substring; returning {}"
            )

    return {}
```

### ~\ragstream\orchestration\agent_prompt_helpers\schema_map.py
```python
# -*- coding: utf-8 -*-
"""
schema_map
==========

Why this helper exists:
- The agent JSON has an 'output_schema' which maps internal field ids
  to JSON keys used in the LLM response.
- Building this field_id → result_key mapping is a small, generic task.

What it does:
- Provides `build_result_key_map(output_schema)` which returns:
    result_keys[field_id] = result_key
"""

from __future__ import annotations

from typing import Any, Dict


def build_result_key_map(output_schema: Dict[str, Any]) -> Dict[str, str]:
    """
    Build field_id -> result_key map from the 'output_schema' section
    of the JSON config.
    """
    result: Dict[str, str] = {}
    fields = output_schema.get("fields", []) or []
    for field in fields:
        field_id = field.get("field_id")
        if not field_id:
            continue
        result_key = field.get("result_key", field_id)
        result[field_id] = result_key
    return result
```


## /home/rusbeh_ab/project/RAGstream/ragstream/retrieval

### ~\ragstream\retrieval\attention.py
```python
"""
AttentionWeights (legacy)
=========================
Kept for compatibility; not central in current eligibility model.
"""
from typing import Dict

class AttentionWeights:
    def weight(self, scores: Dict[str, float]) -> Dict[str, float]:
        return scores
```

### ~\ragstream\retrieval\chunk.py
```python
# -*- coding: utf-8 -*-
"""
Chunk — minimal data record for retrieved context pieces (no helpers).
Place at: ragstream/retrieval/types.py
"""

from __future__ import annotations
from typing import Any, Dict, Tuple

class Chunk:
    __slots__ = (
        "id",       # str: stable identifier (e.g., vector-store id) used by views/selection_ids
        "source",   # str: provenance (file path or URI) to locate the original text
        "snippet",  # str: the actual text excerpt of this chunk
        "span",     # (int, int): start/end character (or line) offsets within the source
        "meta",     # dict: extra metadata (e.g., sha256, mtime, file_type, chunk_index)
    )

    def __init__(
        self,
        *,
        id: str,
        source: str,
        snippet: str,
        span: Tuple[int, int],
        meta: Dict[str, Any] | None = None,
    ) -> None:
        self.id = id
        self.source = source
        self.snippet = snippet
        self.span = span
        self.meta = {} if meta is None else meta
```

### ~\ragstream\retrieval\doc_score.py
```python
# -*- coding: utf-8 -*-
"""
DocScore
========
Pure data container for retrieval results.

Structure mandated by UML (Retriever ..> DocScore) and requirements:
- `id`:   document/chunk identifier (string)
- `score`: cosine similarity score (float, higher is better)
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class DocScore:
    id: str
    score: float
```

### ~\ragstream\retrieval\reranker.py
```python
# -*- coding: utf-8 -*-
"""
reranker.py

Purpose:
    Deterministic ReRanker stage for RAGstream.

Scope of this file:
    - Read the Retrieval candidates already stored in the current SuperPrompt.
    - Build one semantic reranking query from TASK / PURPOSE / CONTEXT.
    - Clean chunk text dynamically before cross-encoder scoring.
    - Score each (query, chunk_text) pair with a BERT-style cross-encoder.
    - Sort the current candidate set by reranker score.
    - Write the ReRanker stage result back into the same SuperPrompt.

Non-goals:
    - No Chroma query here.
    - No raw-file hydration here.
    - No A3 filtering here.
    - No GUI rendering here.
    - No final prompt composition here.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from sentence_transformers import CrossEncoder

from ragstream.orchestration.super_prompt import A3ChunkStatus, SuperPrompt
from ragstream.retrieval.chunk import Chunk


# ---------------------------------------------------------------------
# Module-level reranker defaults
# ---------------------------------------------------------------------

# Agreed current reranker model direction.
DEFAULT_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-12-v2"

# Conceptual cap from the current requirement set for how many Retrieval
# candidates should be passed into ReRanker.
DEFAULT_RERANK_TOP_K = 50

# Agreed current runtime direction: CPU-only deterministic stage.
DEFAULT_DEVICE = "cpu"


class Reranker:
    """
    Deterministic ReRanker stage for document chunks.

    Design:
    - Keep this class stateless with respect to pipeline history.
      The evolving pipeline state lives in SuperPrompt.
    - This class only reads the current SuperPrompt, computes reranking,
      and writes the reranked result back into the same SuperPrompt.
    - The controller decides when to call this class.
    """

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_RERANK_MODEL,
        top_k: int = DEFAULT_RERANK_TOP_K,
        device: str = DEFAULT_DEVICE,
    ) -> None:
        """
        Initialize ReRanker with the agreed cross-encoder model.

        Args:
            model_name:
                Hugging Face / SentenceTransformers model id for the reranker.
            top_k:
                Maximum number of Retrieval candidates to rerank.
            device:
                Runtime device. Current agreed direction is CPU.
        """
        self._model_name = model_name
        self._top_k = int(top_k) if int(top_k) > 0 else DEFAULT_RERANK_TOP_K
        self._device = device
        self._cross_encoder = CrossEncoder(self._model_name, device=self._device)

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def run(self, sp: SuperPrompt) -> SuperPrompt:
        """
        Execute the ReRanker stage and update the same SuperPrompt in place.

        Inputs:
            sp:
                The current evolving SuperPrompt, typically after Retrieval.

        Returns:
            The same SuperPrompt instance, mutated in place.

        Effects on SuperPrompt:
            - Writes the reranked stage snapshot into sp.views_by_stage["reranked"]
            - Writes reranked chunk IDs into sp.final_selection_ids
            - Appends "reranked" to sp.history_of_stages
            - Sets sp.stage = "reranked"
        """
        query_text, retrieval_rows, chunk_lookup = self._prepare_inputs(sp)
        scored_rows = self._score_pairs(query_text, retrieval_rows, chunk_lookup)
        reranked_view, reranked_ids = self._build_reranked_view(scored_rows)

        sp.views_by_stage["reranked"] = reranked_view
        sp.final_selection_ids = reranked_ids
        sp.stage = "reranked"
        sp.history_of_stages.append("reranked")

        return sp

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _prepare_inputs(
        self,
        sp: SuperPrompt,
    ) -> tuple[str, List[tuple[str, float, A3ChunkStatus]], Dict[str, Chunk]]:
        """
        Prepare the reranking job from the current SuperPrompt.

        Responsibilities grouped here on purpose:
        - validate stage and Retrieval availability,
        - build one semantic query text from TASK / PURPOSE / CONTEXT,
        - trim Retrieval rows to the active rerank cap,
        - build chunk_id -> Chunk lookup from base_context_chunks.
        """
        if sp is None:
            raise ValueError("Reranker.run: 'sp' must not be None")

        retrieval_rows = sp.views_by_stage.get("retrieval")
        if not retrieval_rows:
            raise ValueError(
                "Reranker.run: Retrieval candidates are missing. "
                "Please run Retrieval before ReRanker."
            )

        if not sp.base_context_chunks:
            raise ValueError(
                "Reranker.run: base_context_chunks is empty. "
                "Please run Retrieval before ReRanker."
            )

        query_blocks: List[str] = []

        task = (sp.body.get("task") or "").strip()
        purpose = (sp.body.get("purpose") or "").strip()
        context = (sp.body.get("context") or "").strip()

        if task:
            query_blocks.append("## TASK")
            query_blocks.append(task)
            query_blocks.append("")

        if purpose:
            query_blocks.append("## PURPOSE")
            query_blocks.append(purpose)
            query_blocks.append("")

        if context:
            query_blocks.append("## CONTEXT")
            query_blocks.append(context)
            query_blocks.append("")

        query_text = "\n".join(query_blocks).strip()
        if not query_text:
            raise ValueError(
                "Reranker.run: reranking query is empty. "
                "At least one of TASK / PURPOSE / CONTEXT must be present."
            )

        candidate_rows = list(retrieval_rows)
        chunk_lookup = {chunk_obj.id: chunk_obj for chunk_obj in sp.base_context_chunks}

        return query_text, candidate_rows, chunk_lookup

    def _clean_chunk_text(self, text: str) -> str:
        """
        Clean one chunk dynamically before cross-encoder scoring.

        Design intention:
        - Remove obvious markdown / YAML / prompt-artifact rubbish.
        - Keep the original stored Chunk unchanged.
        - Stay conservative: preserve normal prose headings and content.
        """
        text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return ""

        metadata_key_re = re.compile(
            r"^(title|author|version|updated|tags|date|created|modified|description)\s*:\s*.*$",
            re.IGNORECASE,
        )

        lines = text.split("\n")
        cleaned_lines: List[str] = []

        front_matter_active = False
        front_matter_checked = False
        seen_content = False

        for raw_line in lines:
            line = raw_line.strip()

            if not front_matter_checked:
                if not line:
                    continue
                if line == "---":
                    front_matter_active = True
                    front_matter_checked = True
                    continue
                front_matter_checked = True

            if front_matter_active:
                if line in {"---", "..."}:
                    front_matter_active = False
                continue

            if not line:
                if seen_content and (not cleaned_lines or cleaned_lines[-1] != ""):
                    cleaned_lines.append("")
                continue

            if line.startswith("```"):
                continue
            if line.lower().startswith("@@meta"):
                continue
            if line in {"### END_OF_PROMPT", "## END_OF_PROMPT", "END_OF_PROMPT"}:
                continue
            if metadata_key_re.match(line):
                continue

            cleaned_lines.append(line)
            seen_content = True

        while cleaned_lines and cleaned_lines[-1] == "":
            cleaned_lines.pop()

        return "\n".join(cleaned_lines).strip()

    def _score_pairs(
        self,
        query_text: str,
        retrieval_rows: List[tuple[str, float, A3ChunkStatus]],
        chunk_lookup: Dict[str, Chunk],
    ) -> List[Tuple[str, float]]:
        """
        Score all valid (query, chunk_text) pairs with the cross-encoder.

        Returns:
            List[(chunk_id, reranker_score)]

        Important robustness rule:
        - If one Retrieval row references a chunk ID that is no longer present
          in base_context_chunks, skip that row instead of crashing the stage.
        """
        valid_ids: List[str] = []
        pairs: List[tuple[str, str]] = []

        for row in retrieval_rows:
            chunk_id = row[0]
            chunk_obj = chunk_lookup.get(chunk_id)
            if chunk_obj is None:
                continue

            cleaned_snippet = self._clean_chunk_text(chunk_obj.snippet or "")
            if not cleaned_snippet:
                continue

            valid_ids.append(chunk_id)
            pairs.append((query_text, cleaned_snippet))

        if not pairs:
            raise ValueError(
                "Reranker.run: no valid (query, chunk) pairs could be built from Retrieval output."
            )

        scores = self._cross_encoder.predict(pairs, convert_to_numpy=False)
        return [(chunk_id, float(score)) for chunk_id, score in zip(valid_ids, scores)]

    def _build_reranked_view(
        self,
        scored_rows: List[Tuple[str, float]],
    ) -> tuple[List[tuple[str, float, A3ChunkStatus]], List[str]]:
        """
        Build the ordered ReRanker stage snapshot.

        Deterministic sort:
        1) higher reranker score first
        2) stable fallback by chunk_id
        """
        scored_rows.sort(key=lambda row: (-row[1], row[0]))

        reranked_view: List[tuple[str, float, A3ChunkStatus]] = []
        reranked_ids: List[str] = []

        for chunk_id, score in scored_rows:
            reranked_view.append((chunk_id, score, A3ChunkStatus.SELECTED))
            reranked_ids.append(chunk_id)

        return reranked_view, reranked_ids
```

### ~\ragstream\retrieval\retriever.py
```python
# -*- coding: utf-8 -*-
"""
retriever.py

Purpose:
    Deterministic Retrieval stage for RAGstream.

Scope of this file:
    - Read retrieval query text from the current SuperPrompt
      (TASK / PURPOSE / CONTEXT).
    - Split that retrieval query into overlapping query pieces.
    - Open the active project's Chroma document store.
    - Compare every stored chunk embedding against all query-piece embeddings.
    - Aggregate per-chunk similarities with LogAvgExp (tau = 9).
    - Keep the top-k chunks.
    - Hydrate real Chunk objects from doc_raw using the same chunking logic
      as ingestion.
    - Write the Retrieval stage result back into the same SuperPrompt.

Non-goals:
    - No reranking here.
    - No A3 filtering here.
    - No GUI rendering here.
    - No final prompt composition here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from ragstream.ingestion.chunker import Chunker
from ragstream.ingestion.embedder import Embedder
from ragstream.ingestion.vector_store_chroma import VectorStoreChroma
from ragstream.orchestration.super_prompt import A3ChunkStatus, SuperPrompt
from ragstream.retrieval.chunk import Chunk
from ragstream.retrieval.doc_score import DocScore  # compatibility re-export

# Keep old import compatibility:
# from ragstream.retrieval.retriever import DocScore
DocScore = DocScore


# ---------------------------------------------------------------------
# Module-level retrieval defaults
# ---------------------------------------------------------------------

# Fallback number of chunks to keep if the caller gives no valid top-k.
DEFAULT_TOP_K = 100

# Retrieval query splitting reuses the same deterministic windowing idea
# as ingestion. These values MUST stay aligned with the active ingestion
# chunking contract unless you intentionally change both sides together.
DEFAULT_QUERY_CHUNK_SIZE = 500
DEFAULT_QUERY_OVERLAP = 100

# Agreed retrieval aggregation constant:
#P value, for P Norm Averaging
DEFAULT_P_NORM = 10


class Retriever:
    """
    Deterministic Retrieval stage for document chunks.

    Design:
    - Keep this class stateless with respect to pipeline history.
      The evolving pipeline state lives in SuperPrompt.
    - This class only reads the current SuperPrompt, computes retrieval,
      and writes the retrieval result back into the same SuperPrompt.
    - The controller decides when to call this class.
    """

    def __init__(
        self,
        *,
        doc_root: str,
        chroma_root: str,
        embedder: Embedder | None = None,
        chunker: Chunker | None = None,
    ) -> None:
        """
        Initialize Retrieval with explicit project roots and shared helpers.

        Args:
            doc_root:
                Absolute path to the doc_raw root folder.
                Example: .../data/doc_raw
            chroma_root:
                Absolute path to the chroma_db root folder.
                Example: .../data/chroma_db
            embedder:
                Optional shared Embedder instance. If omitted, a default one is created.
            chunker:
                Optional shared Chunker instance. If omitted, a default one is created.
        """
        self.doc_root = Path(doc_root).resolve()
        self.chroma_root = Path(chroma_root).resolve()

        self.embedder = embedder if embedder is not None else Embedder(model="text-embedding-3-large")
        self.chunker = chunker if chunker is not None else Chunker()

        # Keep the chunk class explicit so hydration remains readable and testable.
        self.chunk_cls = Chunk

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def run(self, sp: SuperPrompt, project_name: str, top_k: int) -> SuperPrompt:
        """
        Execute the Retrieval stage and update the same SuperPrompt in place.

        Inputs:
            sp:
                The current evolving SuperPrompt, typically after PreProcessing / A2.
            project_name:
                The active project selected in the GUI.
            top_k:
                Number of chunks to keep after retrieval ranking.

        Returns:
            The same SuperPrompt instance, mutated in place.

        Effects on SuperPrompt:
            - Writes hydrated Chunk objects into sp.base_context_chunks
            - Writes the retrieval stage snapshot into sp.views_by_stage["retrieval"]
            - Writes ordered chunk IDs into sp.final_selection_ids
            - Appends "retrieval" to sp.history_of_stages
            - Sets sp.stage = "retrieval"
        """
        if sp is None:
            raise ValueError("Retriever.run: 'sp' must not be None")

        project_name = (project_name or "").strip()
        if not project_name:
            raise ValueError("Retriever.run: project_name must not be empty")

        if not self.doc_root.exists():
            raise FileNotFoundError(f"Retriever.run: doc_root does not exist: {self.doc_root}")

        project_db_dir = self.chroma_root / project_name
        if not project_db_dir.exists():
            raise FileNotFoundError(
                f"Retriever.run: active project Chroma DB does not exist: {project_db_dir}"
            )

        query_text = self._build_query_text(sp)
        if not query_text:
            raise ValueError(
                "Retriever.run: retrieval query is empty. "
                "At least one of TASK / PURPOSE / CONTEXT must be present."
            )

        query_pieces = self._split_query_into_pieces(
            query_text=query_text,
            chunk_size=DEFAULT_QUERY_CHUNK_SIZE,
            overlap=DEFAULT_QUERY_OVERLAP,
        )

        ranked_rows = self._retrieve_and_rank(
            project_name=project_name,
            query_pieces=query_pieces,
            top_k=top_k,
        )

        valid_ranked_rows, hydrated_chunks = self._hydrate_ranked_chunks(ranked_rows)
        self._write_stage_to_superprompt(sp, valid_ranked_rows, hydrated_chunks)

        return sp

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _build_query_text(self, sp: SuperPrompt) -> str:
        """
        Build the retrieval query text from the structured SuperPrompt body.

        Current design choice:
        - Use only TASK / PURPOSE / CONTEXT.
        - Keep the order explicit and stable.
        - Skip empty fields.
        """
        blocks: List[str] = []

        task = (sp.body.get("task") or "").strip()
        purpose = (sp.body.get("purpose") or "").strip()
        context = (sp.body.get("context") or "").strip()

        if task:
            blocks.append("## TASK")
            blocks.append(task)
            blocks.append("")

        if purpose:
            blocks.append("## PURPOSE")
            blocks.append(purpose)
            blocks.append("")

        if context:
            blocks.append("## CONTEXT")
            blocks.append(context)
            blocks.append("")

        return "\n".join(blocks).strip()

    def _split_query_into_pieces(
        self,
        *,
        query_text: str,
        chunk_size: int,
        overlap: int,
    ) -> List[str]:
        """
        Split the retrieval query into overlapping query pieces.

        We intentionally reuse the same deterministic chunking idea as ingestion
        so the prompt side and document side follow the same windowing culture.
        """
        query_text = (query_text or "").strip()
        if not query_text:
            return []

        pieces = self.chunker.split(
            file_path="__prompt__",
            text=query_text,
            chunk_size=chunk_size,
            overlap=overlap,
        )

        return [chunk_text for _fp, chunk_text in pieces if (chunk_text or "").strip()]

    def _retrieve_and_rank(
        self,
        *,
        project_name: str,
        query_pieces: List[str],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """
        Read all stored chunk embeddings from the active project Chroma DB,
        score them against all query pieces, aggregate with LogAvgExp, and keep top-k.

        Return format:
            List of dictionaries, one per selected chunk:
            {
                "id": <chunk_id>,
                "score": <retrieval_score>,
                "status": A3ChunkStatus.SELECTED,
                "meta": <stored metadata dict>
            }

        Notes:
        - This stage is deterministic.
        - No reranking happens here.
        - We read ALL stored chunk embeddings because the agreed Retrieval stage
          should compute its own final ranking across the complete project store.
        """
        if not query_pieces:
            return []

        k = int(top_k) if int(top_k) > 0 else DEFAULT_TOP_K

        store = VectorStoreChroma(persist_dir=str(self.chroma_root / project_name))

        raw = store.collection.get(include=["embeddings", "metadatas"])
        ids: List[str] = raw.get("ids", []) if raw else []
        metadatas: List[Dict[str, Any] | None] = raw.get("metadatas", []) if raw else []
        embeddings = raw.get("embeddings", []) if raw else []

        # embeddings may come back as a NumPy array, so never test it with
        # "if not embeddings". Use explicit length checks instead.
        if len(ids) == 0 or len(embeddings) == 0:
            return []

        if len(ids) != len(embeddings):
            raise RuntimeError(
                "Retriever._retrieve_and_rank: Chroma returned mismatched ids/embeddings lengths"
            )

        if len(metadatas) > 0 and len(metadatas) != len(ids):
            raise RuntimeError(
                "Retriever._retrieve_and_rank: Chroma returned mismatched ids/metadatas lengths"
            )

        query_vectors = self.embedder.embed(query_pieces)

        # query_vectors may also be array-like, so use explicit length checks.
        if len(query_vectors) == 0:
            return []

        A = np.asarray(embeddings, dtype=np.float32)    # stored chunks: [N, D]
        Q = np.asarray(query_vectors, dtype=np.float32) # query pieces:  [M, D]

        if A.ndim != 2 or Q.ndim != 2:
            raise RuntimeError(
                "Retriever._retrieve_and_rank: unexpected embedding dimensions returned by Chroma/OpenAI"
            )

        if A.shape[1] != Q.shape[1]:
            raise RuntimeError(
                "Retriever._retrieve_and_rank: stored vectors and query vectors have different dimensions"
            )

        # Normalize rows to compute cosine similarity as a matrix product.
        # Similarities shape: [N_chunks, M_query_pieces]
        A_norm = A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-12)
        Q_norm = Q / (np.linalg.norm(Q, axis=1, keepdims=True) + 1e-12)
        sims = A_norm @ Q_norm.T

        # P-mean aggregation over the query-piece axis.
        # Strongly favors the best match, but is still not pure max.
        p = DEFAULT_P_NORM
        sims_pos = np.clip(sims, 0.0, None)
        aggregated_scores = np.power(np.mean(np.power(sims_pos, p), axis=1), 1.0 / p)

        rows: List[Dict[str, Any]] = []
        for idx, chunk_id in enumerate(ids):
            meta = metadatas[idx] if (len(metadatas) > 0 and metadatas[idx] is not None) else {}
            rows.append(
                {
                    "id": chunk_id,
                    "score": float(aggregated_scores[idx]),
                    "status": A3ChunkStatus.SELECTED,
                    "meta": meta,
                }
            )

        # Deterministic sort:
        # 1) higher score first
        # 2) stable fallback by chunk_id
        rows.sort(key=lambda row: (-row["score"], row["id"]))

        return rows[: min(k, len(rows))]

    def _hydrate_ranked_chunks(
        self,
        ranked_rows: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], List[Chunk]]:
        """
        Reconstruct real Chunk objects for the selected ranked rows.

        Why reconstruction is needed:
        - Chroma stores embeddings + metadata only.
        - The actual chunk text must therefore be rebuilt from doc_raw
          using the same chunker and the stored chunk_idx.

        Important robustness rule:
        - If one retrieved row points to a stale or broken source file,
          we skip that row instead of crashing the whole Retrieval stage.

        Returns:
            (valid_ranked_rows, hydrated_chunks)

            valid_ranked_rows:
                Only the rows that could be reconstructed successfully.
            hydrated_chunks:
                Chunk objects aligned 1:1 with valid_ranked_rows.
        """
        valid_ranked_rows: List[Dict[str, Any]] = []
        hydrated: List[Chunk] = []

        # Local caches avoid re-reading and re-splitting the same source file
        # when several retrieved chunks come from that file.
        text_cache: Dict[str, str] = {}
        split_cache: Dict[str, List[tuple[str, str]]] = {}

        step = DEFAULT_QUERY_CHUNK_SIZE - DEFAULT_QUERY_OVERLAP

        for row in ranked_rows:
            chunk_id = row["id"]
            meta = row.get("meta", {}) or {}

            rel_path = str(meta.get("path") or "").strip()
            if not rel_path:
                continue

            raw_path = self.doc_root / rel_path
            if not raw_path.exists():
                continue

            chunk_idx_raw = meta.get("chunk_idx")
            if chunk_idx_raw is None:
                continue

            chunk_idx = int(chunk_idx_raw)

            cache_key = raw_path.as_posix()
            if cache_key not in text_cache:
                text_cache[cache_key] = raw_path.read_text(encoding="utf-8", errors="ignore")

            if cache_key not in split_cache:
                split_cache[cache_key] = self.chunker.split(
                    file_path=str(raw_path),
                    text=text_cache[cache_key],
                    chunk_size=DEFAULT_QUERY_CHUNK_SIZE,
                    overlap=DEFAULT_QUERY_OVERLAP,
                )

            all_chunks_for_file = split_cache[cache_key]
            if chunk_idx < 0 or chunk_idx >= len(all_chunks_for_file):
                continue

            _fp, snippet = all_chunks_for_file[chunk_idx]

            source_text = text_cache[cache_key]
            start = chunk_idx * step
            end = min(start + DEFAULT_QUERY_CHUNK_SIZE, len(source_text))

            chunk_obj = self.chunk_cls(
                id=chunk_id,
                source=rel_path,
                snippet=snippet,
                span=(start, end),
                meta=dict(meta),
            )

            valid_ranked_rows.append(row)
            hydrated.append(chunk_obj)

        return valid_ranked_rows, hydrated

    def _write_stage_to_superprompt(
        self,
        sp: SuperPrompt,
        ranked_rows: List[Dict[str, Any]],
        hydrated_chunks: List[Chunk],
    ) -> None:
        """
        Persist the Retrieval result into the evolving SuperPrompt.

        Write-back contract for this stage:
        - base_context_chunks:
            the hydrated Chunk objects in retrieval order
        - views_by_stage["retrieval"]:
            ordered triples (chunk_id, retrieval_score, SELECTED)
        - final_selection_ids:
            ordered chunk IDs from the current retrieval result
        - stage/history:
            bookkeeping for the pipeline lifecycle
        """
        if len(ranked_rows) != len(hydrated_chunks):
            raise RuntimeError(
                "Retriever._write_stage_to_superprompt: ranked_rows and hydrated_chunks length mismatch"
            )

        sp.base_context_chunks = list(hydrated_chunks)

        retrieval_view: List[tuple[str, float, A3ChunkStatus]] = []
        final_ids: List[str] = []

        for row in ranked_rows:
            chunk_id = str(row["id"])
            score = float(row["score"])
            status = row["status"]

            retrieval_view.append((chunk_id, score, status))
            final_ids.append(chunk_id)

        sp.views_by_stage["retrieval"] = retrieval_view
        sp.final_selection_ids = final_ids
        sp.stage = "retrieval"
        sp.history_of_stages.append("retrieval")
```

### ~\ragstream\retrieval\retriever_old.py
```python
# -*- coding: utf-8 -*-
"""
Retriever
=========
Implements RET-01 (cosine top-k) and plugs optional RET-02 rerank stage.

Pipeline: query text --(Embedder)--> vector --(VectorStoreNP.query)--> ids
          [optional rerank] --> List[DocScore]

Notes
-----
* Current concrete vector store is NumPy-backed `VectorStoreNP` (exact cosine).
* The vector-store interface returns *ids*. To fulfill the requirement of
  returning cosine scores, we compute per-id cosine scores by reading the
  concrete store's in-memory arrays when available (VectorStoreNP exposes
  `_emb`, `_ids`, and `_id2idx`). This avoids changing the public interface.
  If such internals are unavailable (e.g. future Chroma backend), we still
  return `DocScore` with a neutral score of 0.0.
"""
from __future__ import annotations

from typing import List, Optional, Sequence
import math

import numpy as np

from ragstream.retrieval.doc_score import DocScore  # re-exported via this module
# Re-export so existing imports `from ragstream.retrieval.retriever import DocScore` keep working.
DocScore = DocScore  # noqa: F401  (module-level alias for compatibility)

from ragstream.ingestion.embedder import Embedder
from ragstream.ingestion.vector_store_np import VectorStoreNP

from ragstream.retrieval.reranker import Reranker
from ragstream.utils.paths import PATHS


class Retriever:
    """
    High-level retrieval orchestrator.

    Parameters
    ----------
    persist_dir : Optional[str]
        Directory for the NumPy vector store snapshots. Defaults to PATHS['vector_pkls'].
    embedder : Optional[Embedder]
        Custom embedder instance. If None, a default Embedder() is created.
    store : Optional[VectorStoreNP]
        Custom VectorStoreNP instance. If None, a default store is opened at `persist_dir`.
    reranker : Optional[Reranker]
        Optional cross-encoder reranker; if None, rerank step is skipped.
    """

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        embedder: Optional[Embedder] = None,
        store: Optional[VectorStoreNP] = None,
        reranker: Optional[Reranker] = None,
    ) -> None:
        self._persist_dir = persist_dir or str(PATHS["vector_pkls"])
        self._emb = embedder or Embedder()
        self._vs = store or VectorStoreNP(self._persist_dir)
        self._reranker = reranker or Reranker()

    # ---- public API ----
    def retrieve(self, query: str, k: int = 10, do_rerank: bool = True) -> List[DocScore]:
        """
        Retrieve top-k candidates for a query as `DocScore(id, score)`.

        Steps:
        1) Embed the query.
        2) Ask the vector store for candidate ids (k).
        3) Compute cosine scores for these ids (when store internals available).
        4) Optional rerank (order only), preserving computed scores.
        5) Return `DocScore` list (length ≤ k).

        Notes:
        - If no vectors are present, returns [].
        - If reranker is a no-op (current placeholder), order remains unchanged.
        """
        if not query or not isinstance(query, str):
            return []

        vecs = self._emb.embed([query])
        if not vecs:
            return []
        q = np.asarray(vecs[0], dtype=np.float32)
        if q.ndim != 1:
            q = q.reshape(-1)

        # Ask store for candidate ids (VectorStoreNP performs exact-cosine top-k by ids)
        ids: List[str] = self._vs.query(q.tolist(), k=k)  # type: ignore[arg-type]

        if not ids:
            return []

        # Compute cosine scores for the candidate ids when VectorStoreNP internals are available.
        scores = self._compute_cosine_scores(ids, q)

        # Optional rerank (RET-02). Current Reranker returns ids order; we preserve the computed scores.
        if do_rerank and self._reranker is not None:
            try:
                reranked_ids = self._reranker.rerank(ids, query)
                # Keep only ids we have scores for, preserve reranked order.
                ordered = [(i, scores.get(i, 0.0)) for i in reranked_ids if i in scores]
            except Exception:
                # Fail-safe: skip rerank on any error.
                ordered = [(i, scores.get(i, 0.0)) for i in ids]
        else:
            ordered = [(i, scores.get(i, 0.0)) for i in ids]

        # Truncate to k and wrap as DocScore
        ordered = ordered[: max(0, int(k))]
        return [DocScore(id=doc_id, score=float(sc)) for doc_id, sc in ordered]

    # ---- helpers ----
    def _compute_cosine_scores(self, ids: Sequence[str], q: np.ndarray) -> dict[str, float]:
        """
        Compute cosine similarity for a set of ids against query vector q using
        VectorStoreNP internal arrays when available. Falls back to 0.0 if not.
        """
        scores: dict[str, float] = {}
        # Use VectorStoreNP internals if present.
        emb = getattr(self._vs, "_emb", None)
        id2idx = getattr(self._vs, "_id2idx", None)
        if emb is None or id2idx is None:
            # No access to raw vectors (e.g., future Chroma backend).
            for _id in ids:
                scores[_id] = 0.0
            return scores

        A = np.asarray(emb, dtype=np.float32)  # (N, D)
        if A.ndim != 2 or A.size == 0:
            for _id in ids:
                scores[_id] = 0.0
            return scores

        qn = float(np.linalg.norm(q) + 1e-12)
        # Compute per-id cosine using the stored row corresponding to id.
        for _id in ids:
            idx = id2idx.get(_id, None)
            if idx is None:
                scores[_id] = 0.0
                continue
            v = A[idx]
            vn = float(np.linalg.norm(v) + 1e-12)
            sim = float(np.dot(v, q) / (vn * qn))
            # Clip to [-1, 1] to avoid tiny numerical overshoots.
            if sim > 1.0:
                sim = 1.0
            elif sim < -1.0:
                sim = -1.0
            scores[_id] = sim
        return scores
```


## /home/rusbeh_ab/project/RAGstream/ragstream/memory

### ~\ragstream\memory\conversation_memory.py
```python
"""
ConversationMemory (read-only)
==============================
Two-layer history:
- Layer-G: recency window (last k turns), always available.
- Layer-E: episodic store with metadata (on-topic, soft fading).
Not part of the document store; no embeddings/retrieval.
"""
from typing import List, Tuple

class ConversationMemory:
    def __init__(self, k_default: int = 5) -> None:
        self.k_default = k_default
        self.soft_fading = True
        self.conflict_policy = "FILES>newer>older"

    def get_recent(self, k: int | None = None) -> List[Tuple[str, str]]:
        return []

    def get_episodic(self) -> List[Tuple[str, str]]:
        return []
```


## /home/rusbeh_ab/project/RAGstream/ragstream/utils

### ~\ragstream\utils\logging.py
```python
# -*- coding: utf-8 -*-
"""
SimpleLogger — tiny logging facade for RAGstream.

Goal:
- Avoid crashes when code calls SimpleLogger.info/debug/warning/error.
- Keep it trivial: one class with classmethods, printing to stdout.
- Later you can swap this to Python's 'logging' without touching callers.
"""

from __future__ import annotations
import sys
import datetime
from typing import ClassVar


class SimpleLogger:
    """
    Very small logging helper.

    Usage:
        SimpleLogger.info("message")
        SimpleLogger.debug("details")
    """

    _enabled: ClassVar[bool] = True
    _prefix: ClassVar[str] = "RAGstream"

    @classmethod
    def _log(cls, level: str, msg: str) -> None:
        if not cls._enabled:
            return
        now = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"{cls._prefix} | {level.upper():5s} | {now} | {msg}"
        print(line, file=sys.stdout, flush=True)

    @classmethod
    def debug(cls, msg: str) -> None:
        cls._log("DEBUG", msg)

    @classmethod
    def info(cls, msg: str) -> None:
        cls._log("INFO", msg)

    @classmethod
    def warning(cls, msg: str) -> None:
        cls._log("WARN", msg)

    @classmethod
    def error(cls, msg: str) -> None:
        cls._log("ERROR", msg)

    @classmethod
    def set_enabled(cls, enabled: bool) -> None:
        cls._enabled = enabled

    @classmethod
    def set_prefix(cls, prefix: str) -> None:
        cls._prefix = prefix
```

### ~\ragstream\utils\paths.py
```python
"""
Paths
=====
Centralises on-disk locations so a single import
(`from ragstream.utils.paths import PATHS`) gives typed access.
"""
from pathlib import Path
from typing import TypedDict

class _Paths(TypedDict):
    root:        Path
    data:        Path
    raw_docs:    Path
    chroma_db:   Path
    vector_pkls: Path
    logs:        Path

ROOT = Path(__file__).resolve().parents[2]

PATHS: _Paths = {
    "root":        ROOT,
    "data":        ROOT / "data",
    "raw_docs":    ROOT / "data" / "doc_raw",
    "chroma_db":   ROOT / "data" / "chroma_db",   # planned
    "vector_pkls": ROOT / "data" / "vector_pkls", # current persistence
    "logs":        ROOT / "logs",                 # present as a path; no persistent logging required
}
```

