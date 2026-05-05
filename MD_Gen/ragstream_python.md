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
from ragstream.agents.a3_nli_gate import A3NLIGate
from ragstream.agents.a4_condenser import A4Condenser

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
from ragstream.textforge.RagLog import LogALL as logger


class AppController:
    def __init__(self, schema_path: str = "ragstream/config/prompt_schema.json") -> None:
        """
        Central app controller.

        Light initialization only.

        - Loads PromptSchema once (for PreProcessing).
        - Creates a shared AgentFactory + LLMClient.
        - Creates the A2PromptShaper agent.
        - Creates the A3NLIGate agent.
        - Creates the A4Condenser agent.
        - Prepares project/data paths.
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

        # A3 agent
        self.a3_nli_gate = A3NLIGate(
            agent_factory=self.agent_factory,
            llm_client=self.llm_client,
        )

        # A4 agent
        self.a4_condenser = A4Condenser(
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

    def initialize_heavy_components(self) -> None:
        """
        Heavy initialization only.

        - Creates the Retrieval stage object.
        - Creates the ReRanker stage object.
        """

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
        logger("PreProcessing started.", "INFO", "PUBLIC")
        preprocess(text, sp, self.schema)
        logger("PreProcessing completed.", "INFO", "PUBLIC")
        return sp

    def run_a2_promptshaper(self, sp: SuperPrompt) -> SuperPrompt:
        """
        Run A2 on the current SuperPrompt.
        """
        return self.a2_promptshaper.run(sp)

    def run_a3(self, sp: SuperPrompt) -> SuperPrompt:
        """
        Run A3 on the current SuperPrompt.

        Inputs:
            sp:
                Current evolving SuperPrompt, typically after ReRanker.

        Returns:
            Updated SuperPrompt after A3 has populated:
            - views_by_stage["a3"]
            - extras["a3_selection_band"]
            - extras["a3_item_decisions"]
            - final_selection_ids
            - stage / history_of_stages
        """
        return self.a3_nli_gate.run(sp)

    def run_a4(
        self,
        sp: SuperPrompt,
        *,
        effective_output_token_limit: int | None = None,
    ) -> SuperPrompt:
        """
        Run A4 on the current SuperPrompt.

        Inputs:
            sp:
                Current evolving SuperPrompt, typically after A3.
            effective_output_token_limit:
                Optional external override for the final condenser output allowance.

        Returns:
            Updated SuperPrompt after A4 has populated:
            - S_CTX_MD
            - views_by_stage["a4"]
            - final_selection_ids
            - extras["a4_*"]
            - stage / history_of_stages
        """
        return self.a4_condenser.run(
            sp,
            effective_output_token_limit=effective_output_token_limit,
        )

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
    def run_retrieval(
        self,
        sp: SuperPrompt,
        project_name: str,
        top_k: int,
        *,
        use_retrieval_splade: bool = True,
    ) -> SuperPrompt:
        """
        Run Retrieval on the current SuperPrompt for the selected active project.

        Inputs:
            sp:
                Current evolving SuperPrompt.
            project_name:
                Active project selected in the GUI.
            top_k:
                Number of chunks to keep after retrieval ranking.
            use_retrieval_splade:
                If False, bypass the real SPLADE branch and duplicate the dense
                ranking into the SPLADE input slot before RRF so the Retrieval
                output contract stays unchanged.

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
            use_retrieval_splade=bool(use_retrieval_splade),
        )

    # Added on 31.03.2026:
    # ReRanker is a separate deterministic stage after Retrieval. The controller
    # only passes the current SuperPrompt and returns the same updated object.
    def run_reranker(
        self,
        sp: SuperPrompt,
        *,
        use_reranking_colbert: bool = True,
    ) -> SuperPrompt:
        """
        Run ReRanker on the current SuperPrompt.

        Inputs:
            sp:
                Current evolving SuperPrompt, typically after Retrieval.
            use_reranking_colbert:
                If False, bypass real ColBERT scoring and copy the Retrieval
                order into the reranked stage so A3 can run immediately.

        Returns:
            Updated SuperPrompt after ReRanker has populated:
            - views_by_stage["reranked"]
            - final_selection_ids
            - stage / history_of_stages
        """
        return self.reranker.run(
            sp,
            use_reranking_colbert=bool(use_reranking_colbert),
        )

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

### ~\ragstream\app\Hook_ChatGTP.py
```python
# Hook_ChatGTP.py
# Logic:
# - attach to an already running Chrome/Chromium via CDP
# - identify the active ChatGPT tab
# - optionally write a message into the composer
# - optionally send it
# - read the latest assistant message from the page

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import sys

from playwright.sync_api import sync_playwright, Page, Locator


CDP_URL = "http://127.0.0.1:9222"
MESSAGE_TEXT = "hello, how are you"


@dataclass
class TabInfo:
    page: Page
    url: str
    title: str
    has_focus: bool
    visibility_state: str


def _safe_title(page: Page) -> str:
    try:
        return page.title()
    except Exception:
        return ""


def _safe_has_focus(page: Page) -> bool:
    try:
        return bool(page.evaluate("document.hasFocus()"))
    except Exception:
        return False


def _safe_visibility(page: Page) -> str:
    try:
        value = page.evaluate("document.visibilityState")
        return str(value) if value is not None else ""
    except Exception:
        return ""


def _is_chatgpt_tab(page: Page) -> bool:
    url = (page.url or "").lower()
    return ("chatgpt.com" in url) or ("chat.openai.com" in url)


def _score_tab(info: TabInfo) -> int:
    score = 0

    if info.has_focus:
        score += 100
    if info.visibility_state == "visible":
        score += 50

    url_lower = info.url.lower()
    title_lower = info.title.lower()

    if "/c/" in url_lower:
        score += 20
    if "chatgpt" in title_lower or "rag" in title_lower:
        score += 10

    return score


def _find_active_chatgpt_tab(browser) -> Optional[TabInfo]:
    candidates: list[TabInfo] = []

    for context in browser.contexts:
        for page in context.pages:
            if not _is_chatgpt_tab(page):
                continue

            info = TabInfo(
                page=page,
                url=page.url or "",
                title=_safe_title(page),
                has_focus=_safe_has_focus(page),
                visibility_state=_safe_visibility(page),
            )
            candidates.append(info)

    if not candidates:
        return None

    candidates.sort(key=_score_tab, reverse=True)
    return candidates[0]


def _first_working_locator(page: Page) -> Optional[Locator]:
    candidates = [
        page.get_by_role("textbox").last,
        page.locator("textarea").last,
        page.locator('[contenteditable="true"]').last,
    ]

    for locator in candidates:
        try:
            locator.wait_for(state="visible", timeout=1500)
            if locator.is_visible(timeout=1500):
                return locator
        except Exception:
            pass

    return None


def _last_visible_assistant_message(page: Page) -> Optional[Locator]:
    selectors = [
        'div[data-message-author-role="assistant"]',
        'article [data-message-author-role="assistant"]',
        '[data-message-author-role="assistant"]',
    ]

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            count = 0

        if count == 0:
            continue

        for i in range(count - 1, -1, -1):
            item = locator.nth(i)
            try:
                if item.is_visible(timeout=1000):
                    return item
            except Exception:
                pass

    return None


def get_last_assistant_message(page: Page) -> Optional[str]:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=3000)
    except Exception:
        pass

    try:
        page.wait_for_timeout(700)
    except Exception:
        pass

    message = _last_visible_assistant_message(page)
    if message is None:
        return None

    try:
        text = message.inner_text(timeout=2000).strip()
        return text if text else None
    except Exception:
        return None


def _write_into_composer(page: Page, text: str, submit: bool = False) -> bool:
    locator = _first_working_locator(page)
    if locator is None:
        return False

    try:
        locator.click(timeout=3000)

        try:
            locator.fill("")
        except Exception:
            try:
                locator.press("Control+A")
                locator.press("Backspace")
            except Exception:
                pass

        try:
            locator.fill(text, timeout=3000)
        except Exception:
            locator.press_sequentially(text, delay=20)

        if submit:
            locator.press("Enter")

        return True

    except Exception:
        return False

def wait_for_last_assistant_message_ready(
    page: Page,
    timeout_ms: int = 120000,
    poll_ms: int = 400,
    stable_rounds: int = 4,
) -> Optional[str]:
    start = page.evaluate("Date.now()")
    last_text = None
    stable_count = 0

    while True:
        now = page.evaluate("Date.now()")
        if now - start > timeout_ms:
            return last_text.strip() if last_text and last_text.strip() else None

        message = _last_visible_assistant_message(page)
        if message is None:
            page.wait_for_timeout(poll_ms)
            continue

        try:
            current_text = message.inner_text(timeout=1500).strip()
        except Exception:
            current_text = ""

        if current_text and current_text == last_text:
            stable_count += 1
        else:
            stable_count = 0
            last_text = current_text

        if current_text and stable_count >= stable_rounds:
            return current_text

        page.wait_for_timeout(poll_ms)


def run() -> None:
    text_to_send: Optional[str] = None
    if len(sys.argv) >= 2:
        text_to_send = " ".join(sys.argv[1:]).strip()
        if not text_to_send:
            print("Text argument was provided but is empty.")
            sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        try:
            tab = _find_active_chatgpt_tab(browser)

            if tab is None:
                print("No ChatGPT tab was found through CDP.")
                print("Most likely reason: the special Chrome window is not open.")
                sys.exit(2)

            print("FOUND ACTIVE CHATGPT TAB")
            print(f"URL   : {tab.url}")
            print(f"TITLE : {tab.title}")
            print(f"FOCUS : {tab.has_focus}")
            print(f"VIS   : {tab.visibility_state}")
            print()

            if text_to_send is not None:
                ok = _write_into_composer(tab.page, text_to_send, submit=True)

                if not ok:
                    print("ACTIVE TAB WAS FOUND, BUT COMPOSER COULD NOT BE DETECTED")
                    sys.exit(3)

                print("TEXT WRITTEN INTO CHATGPT COMPOSER")
                print("MESSAGE WAS SENT")
                print()

                # Small wait so the page can start updating.
                try:
                    tab.page.wait_for_timeout(2500)
                except Exception:
                    pass

            last_message = wait_for_last_assistant_message_ready(tab.page)

            print("LAST ASSISTANT MESSAGE:")
            if last_message:
                print(last_message)
            else:
                print("(not found)")

        finally:
            browser.close()


if __name__ == "__main__":
    run()
```

### ~\ragstream\app\Hook_ChatGTP2.py
```python
# Hook_ChatGTP.py
# Logic:
# - attach to an already running Chrome/Chromium via CDP
# - identify the active ChatGPT tab
# - locate the composer box
# - write dynamic text into the box
# - do NOT send anything

from __future__ import annotations

import sys

from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import sync_playwright, Page, Locator


CDP_URL = "http://127.0.0.1:9222"


@dataclass
class TabInfo:
    page: Page
    url: str
    title: str
    has_focus: bool
    visibility_state: str


def _safe_title(page: Page) -> str:
    try:
        return page.title()
    except Exception:
        return ""


def _safe_has_focus(page: Page) -> bool:
    try:
        return bool(page.evaluate("document.hasFocus()"))
    except Exception:
        return False


def _safe_visibility(page: Page) -> str:
    try:
        value = page.evaluate("document.visibilityState")
        return str(value) if value is not None else ""
    except Exception:
        return ""


def _is_chatgpt_tab(page: Page) -> bool:
    url = (page.url or "").lower()
    return ("chatgpt.com" in url) or ("chat.openai.com" in url)


def _score_tab(info: TabInfo) -> int:
    score = 0

    if info.has_focus:
        score += 100
    if info.visibility_state == "visible":
        score += 50

    url_lower = info.url.lower()
    title_lower = info.title.lower()

    if "/c/" in url_lower:
        score += 20
    if "chatgpt" in title_lower or "rag" in title_lower:
        score += 10

    return score


def _find_active_chatgpt_tab(browser) -> Optional[TabInfo]:
    candidates: list[TabInfo] = []

    for context in browser.contexts:
        for page in context.pages:
            if not _is_chatgpt_tab(page):
                continue

            info = TabInfo(
                page=page,
                url=page.url or "",
                title=_safe_title(page),
                has_focus=_safe_has_focus(page),
                visibility_state=_safe_visibility(page),
            )
            candidates.append(info)

    if not candidates:
        return None

    candidates.sort(key=_score_tab, reverse=True)
    return candidates[0]


def _first_working_locator(page: Page) -> Optional[Locator]:
    candidates = [
        page.get_by_role("textbox").last,
        page.locator("textarea").last,
        page.locator('[contenteditable="true"]').last,
    ]

    for locator in candidates:
        try:
            locator.wait_for(state="visible", timeout=1500)
            if locator.is_visible(timeout=1500):
                return locator
        except Exception:
            pass

    return None


def _write_into_composer(page: Page, text: str, submit: bool = False) -> bool:
    locator = _first_working_locator(page)
    if locator is None:
        return False

    try:
        locator.click(timeout=3000)

        try:
            locator.fill("")
        except Exception:
            try:
                locator.press("Control+A")
                locator.press("Backspace")
            except Exception:
                pass

        try:
            locator.fill(text, timeout=3000)
        except Exception:
            locator.press_sequentially(text, delay=20)

        if submit:
            locator.press("Enter")

        return True

    except Exception:
        return False


def write_text_to_active_chatgpt(text: str) -> bool:
    if not text or not text.strip():
        raise ValueError("Text must not be empty.")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        try:
            tab = _find_active_chatgpt_tab(browser)

            if tab is None:
                print("No ChatGPT tab was found through CDP.")
                print("Most likely reason: the special Chrome window is not open.")
                return False

            print("FOUND ACTIVE CHATGPT TAB")
            print(f"URL   : {tab.url}")
            print(f"TITLE : {tab.title}")
            print(f"FOCUS : {tab.has_focus}")
            print(f"VIS   : {tab.visibility_state}")

            ok = _write_into_composer(tab.page, text, submit=True)

            if ok:
                print("TEXT WRITTEN INTO CHATGPT COMPOSER")
                print("MESSAGE WAS NOT SENT")
                return True

            print("ACTIVE TAB WAS FOUND, BUT COMPOSER COULD NOT BE DETECTED")
            return False

        finally:
            browser.close()


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python Hook_ChatGTP.py "your text here"')
        sys.exit(1)

    text = " ".join(sys.argv[1:])
    ok = write_text_to_active_chatgpt(text)

    if not ok:
        sys.exit(2)


if __name__ == "__main__":
    main()
```

### ~\ragstream\app\ui_actions.py
```python
# ragstream/app/ui_actions.py
# -*- coding: utf-8 -*-
"""
Small callback helpers for Streamlit button/form actions.
Keep controller calls and session-state mutations here.
"""

from __future__ import annotations

import copy
import time

from typing import Any

import streamlit as st

from ragstream.app.controller import AppController
from ragstream.memory.memory_actions import capture_memory_pair
from ragstream.memory.memory_manager import MemoryManager
from ragstream.orchestration.super_prompt import SuperPrompt
from ragstream.textforge.RagLog import LogALL as logger


def do_preprocess() -> None:
    ctrl: AppController = st.session_state.controller
    user_text = st.session_state.get("prompt_text", "")

    # Start a fresh pipeline run from clean SuperPrompt objects
    st.session_state.sp = SuperPrompt()
    st.session_state.sp_pre = SuperPrompt()
    st.session_state.sp_a2 = SuperPrompt()
    st.session_state.sp_rtv = SuperPrompt()
    st.session_state.sp_rrk = SuperPrompt()
    st.session_state.sp_a3 = SuperPrompt()
    st.session_state.sp_a4 = SuperPrompt()

    sp: SuperPrompt = st.session_state.sp
    sp = ctrl.preprocess(user_text, sp)

    st.session_state.sp = sp
    st.session_state.sp_pre = copy.deepcopy(sp)
    st.session_state["super_prompt_text"] = sp.prompt_ready


def do_a2_promptshaper() -> None:
    """A2 button callback."""
    ctrl: AppController = st.session_state.controller
    sp: SuperPrompt = st.session_state.sp

    sp = ctrl.run_a2_promptshaper(sp)

    st.session_state.sp = sp
    st.session_state.sp_a2 = copy.deepcopy(sp)
    st.session_state["super_prompt_text"] = sp.prompt_ready


def do_feed_memory_manually() -> None:
    """Manual memory feed button callback."""
    prompt_text = st.session_state.get("prompt_text", "")
    output_text = st.session_state.get("manual_memory_feed_text", "")

    if not (prompt_text or "").strip():
        logger("Prompt is empty. No memory record was created.", "WARN", "PUBLIC")
        return

    if not (output_text or "").strip():
        logger("Manual memory response is empty. No memory record was created.", "WARN", "PUBLIC")
        return

    memory_manager: MemoryManager = st.session_state.memory_manager

    if not memory_manager.title.strip():
        st.session_state["pending_manual_memory_pair"] = {
            "input_text": prompt_text,
            "output_text": output_text,
        }
        st.session_state["memory_title_required"] = True
        logger("Enter a memory title to create the first memory file.", "INFO", "PUBLIC")
        st.session_state["runtime_log_flash_until"] = time.time() + 5
        st.rerun()

    _save_memory_pair(
        input_text=prompt_text,
        output_text=output_text,
    )


def do_confirm_memory_title_and_save() -> None:
    """Confirm first memory title and save pending manual memory pair."""
    title = (st.session_state.get("memory_title_input", "") or "").strip()
    if not title:
        logger("Memory title must not be empty.", "WARN", "PUBLIC")
        return

    memory_manager: MemoryManager = st.session_state.memory_manager

    if not memory_manager.title.strip():
        memory_manager.start_new_history(title)
        logger(f"Memory file created: {memory_manager.filename_ragmem}", "INFO", "PUBLIC")

    pending_pair = st.session_state.get("pending_manual_memory_pair")
    if pending_pair:
        input_text = pending_pair.get("input_text", "")
        output_text = pending_pair.get("output_text", "")
    else:
        input_text = st.session_state.get("prompt_text", "")
        output_text = st.session_state.get("manual_memory_feed_text", "")

    _save_memory_pair(
        input_text=input_text,
        output_text=output_text,
    )


def _save_memory_pair(
    input_text: str,
    output_text: str,
) -> None:
    try:
        ctrl: AppController = st.session_state.controller
        memory_manager: MemoryManager = st.session_state.memory_manager

        active_project_name, embedded_files_snapshot = _get_active_project_snapshot(ctrl)
        gui_records_state = _collect_memory_gui_state(memory_manager)

        result = capture_memory_pair(
            memory_manager=memory_manager,
            input_text=input_text,
            output_text=output_text,
            source="manual_memory_feed",
            active_project_name=active_project_name,
            embedded_files_snapshot=embedded_files_snapshot,
            gui_records_state=gui_records_state,
            memory_ingestion_manager=st.session_state.get("memory_ingestion_manager"),
        )

        if result.get("success"):
            st.session_state["pending_manual_memory_pair"] = None
            st.session_state["memory_title_required"] = False
            st.session_state["manual_memory_feed_text"] = ""
            st.rerun()
        else:
            logger(result.get("message", "Memory record was not saved."), "WARN", "PUBLIC")

    except Exception as e:
        logger(str(e), "ERROR", "PUBLIC")


def _get_active_project_snapshot(ctrl: AppController) -> tuple[str | None, list[str]]:
    active_project = st.session_state.get("active_project")

    if not active_project or active_project == "(no projects yet)":
        return None, []

    try:
        embedded_info = ctrl.get_embedded_files(active_project)
    except Exception:
        return active_project, []

    if embedded_info.get("success"):
        return active_project, list(embedded_info.get("files", []))

    return active_project, []


def _collect_memory_gui_state(memory_manager: MemoryManager) -> list[dict[str, Any]]:
    gui_state: list[dict[str, Any]] = []

    for record in memory_manager.records:
        tag_key = f"memory_tag_{record.record_id}"
        source_mode_key = f"memory_retrieval_source_mode_{record.record_id}"
        keywords_key = f"memory_user_keywords_{record.record_id}"
        direct_recall_key = f"memory_direct_recall_key_{record.record_id}"

        tag = st.session_state.get(tag_key, record.tag)
        retrieval_source_mode = st.session_state.get(
            source_mode_key,
            getattr(record, "retrieval_source_mode", "QA"),
        )
        user_keywords_text = st.session_state.get(
            keywords_key,
            ", ".join(record.user_keywords),
        )
        direct_recall_value = st.session_state.get(
            direct_recall_key,
            getattr(record, "direct_recall_key", ""),
        )

        gui_state.append(
            {
                "record_id": record.record_id,
                "tag": tag,
                "retrieval_source_mode": retrieval_source_mode,
                "user_keywords": _parse_user_keywords(user_keywords_text),
                "direct_recall_key": str(direct_recall_value or "").strip(),
            }
        )

    return gui_state


def _parse_user_keywords(text: str) -> list[str]:
    raw_items = str(text or "").replace("\n", ",").split(",")

    result: list[str] = []
    seen: set[str] = set()

    for item in raw_items:
        keyword = item.strip()
        if not keyword:
            continue

        key = keyword.lower()
        if key in seen:
            continue

        result.append(keyword)
        seen.add(key)

    return result


def do_retrieval() -> None:
    """Retrieval button callback."""
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
            return

        top_k = int(st.session_state.get("retrieval_top_k", 100))
        use_retrieval_splade = bool(st.session_state.get("use_retrieval_splade", False))

        sp = ctrl.run_retrieval(
            sp,
            project_name,
            top_k,
            use_retrieval_splade=use_retrieval_splade,
        )
        sp.compose_prompt_ready()

        st.session_state.sp = sp
        st.session_state.sp_rtv = copy.deepcopy(sp)
        st.session_state["super_prompt_text"] = sp.prompt_ready

    except Exception as e:
        st.error(str(e))


def do_reranker() -> None:
    """ReRanker button callback."""
    try:
        ctrl: AppController = st.session_state.controller
        sp: SuperPrompt = st.session_state.sp

        use_reranking_colbert = bool(st.session_state.get("use_reranking_colbert", False))

        sp = ctrl.run_reranker(
            sp,
            use_reranking_colbert=use_reranking_colbert,
        )
        sp.compose_prompt_ready()

        st.session_state.sp = sp
        st.session_state.sp_rrk = copy.deepcopy(sp)
        st.session_state["super_prompt_text"] = sp.prompt_ready

    except Exception as e:
        st.error(str(e))


def do_a3_nli_gate() -> None:
    """A3 button callback."""
    try:
        ctrl: AppController = st.session_state.controller
        sp: SuperPrompt = st.session_state.sp

        sp = ctrl.run_a3(sp)

        st.session_state.sp = sp
        st.session_state.sp_a3 = copy.deepcopy(sp)
        st.session_state["super_prompt_text"] = sp.prompt_ready

    except Exception as e:
        st.error(str(e))


def do_a4_condenser() -> None:
    """A4 button callback."""
    try:
        ctrl: AppController = st.session_state.controller
        sp: SuperPrompt = st.session_state.sp

        sp = ctrl.run_a4(sp)
        sp.compose_prompt_ready()

        st.session_state.sp = sp
        st.session_state.sp_a4 = copy.deepcopy(sp)
        st.session_state["super_prompt_text"] = sp.prompt_ready

    except Exception as e:
        st.error(str(e))


def do_create_project() -> None:
    """Create Project form callback."""
    try:
        ctrl: AppController = st.session_state.controller
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


def do_add_files() -> None:
    """Add Files form callback."""
    try:
        ctrl: AppController = st.session_state.controller

        result = ctrl.import_files_to_project(
            st.session_state.get("add_files_project", ""),
            uploaded_files=st.session_state.get("ingestion_uploaded_files"),
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
```

### ~\ragstream\app\ui_layout.py
```python
# ragstream/app/ui_layout.py
# -*- coding: utf-8 -*-
"""
Layout / geometry helpers for Streamlit UI.
Keep columns, containers, labels and visual order here.
"""

from __future__ import annotations

import html
import time

import streamlit as st

from ragstream.app.controller import AppController
from ragstream.app.ui_actions import (
    do_a2_promptshaper,
    do_a3_nli_gate,
    do_a4_condenser,
    do_add_files,
    do_confirm_memory_title_and_save,
    do_create_project,
    do_feed_memory_manually,
    do_preprocess,
    do_reranker,
    do_retrieval,
)


TAG_COLORS: dict[str, str] = {
    "Gold": "#D4AF37",
    "Green": "#00A86B",
    "Black": "#111111",
}


def inject_base_css() -> None:
    """Global CSS for simple spacing and boxes."""
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

            /* Make row gaps compact */
            div[data-testid="stHorizontalBlock"]{
                gap: 0.4rem !important;
            }

            /* Memory card style */
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

            .memory-tag-indicator {
                display: flex;
                align-items: center;
                gap: 0.35rem;
                margin-bottom: 0.25rem;
                min-height: 24px;
            }

            .memory-tag-square {
                width: 18px;
                height: 18px;
                border-radius: 0.25rem;
                border: 1px solid rgba(0, 0, 0, 0.25);
                box-shadow: 0 1px 2px rgba(0, 0, 0, 0.16);
                flex: 0 0 auto;
            }

            .memory-tag-name {
                font-size: 0.78rem;
                color: #374151;
                line-height: 1.0;
                white-space: nowrap;
            }



            /* Manual memory feed button */
            div[data-testid="stButton"] > button[kind="primary"] {
                background-color: #3F48CC !important;
                border-color: #3F48CC !important;
                color: white !important;
            }

            div[data-testid="stButton"] > button[kind="primary"]:hover {
                background-color: #3F48CC !important;
                border-color: #3F48CC !important;
                color: white !important;
            }

            div[data-testid="stButton"] > button[kind="primary"]:focus {
                background-color: #3F48CC !important;
                border-color: #3F48CC !important;
                color: white !important;
            }

            div[data-testid="stButton"] > button[kind="primary"] p {
                color: white !important;
            }

            /* Manual memory feed edit box */
            textarea[aria-label="Manual Memory Feed (hidden)"] {
                background-color: #EAF7FF !important;
            }



            /* TextForge GUI log box */
            .textforge-log-box {
                background-color: #EAFBEA;
                border: 1px solid #B7E4B7;
                border-radius: 0.45rem;
                padding: 0.55rem 0.70rem;
                min-height: 140px;
                max-height: 180px;
                overflow-y: auto;
                white-space: normal;
                word-break: break-word;
                font-family: monospace;
                font-size: 0.88rem;
                line-height: 1.35;
            }

            /* Make small select boxes look compact */
            div[data-baseweb="select"] > div {
                min-height: 34px;
            }

            /* Direct Recall Key field: special red border */
            div[data-testid="stTextInput"]:has(input[aria-label="Direct Recall Key"]) div[data-baseweb="input"] {
                border: 2px solid #D11A2A !important;
                border-radius: 0.45rem !important;
                box-shadow: none !important;
            }

            div[data-testid="stTextInput"]:has(input[aria-label="Direct Recall Key"]) div[data-baseweb="input"]:focus-within {
                border: 2px solid #D11A2A !important;
                box-shadow: 0 0 0 1px rgba(209, 26, 42, 0.25) !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page() -> None:
    """
    Two-column layout:

    LEFT:
      Prompt
      Super-Prompt

    RIGHT:
      Memory
      Buttons / Top-K / project controls / status
    """
    # Main 2-column layout
    gutter_l, col_left, spacer, col_right, gutter_r = st.columns([0.6, 4, 0.25, 4, 0.6], gap="small")

    with gutter_l:  # left gutter
        st.empty()

    with col_right:
        render_right_panel()

    with spacer:
        st.empty()

    with col_left:
        render_left_panel()

    with gutter_r:  # right gutter
        st.empty()


def render_left_panel() -> None:
    """Left panel: Prompt at top, Super-Prompt below."""
    # Prompt section
    st.markdown('<div class="field-title">Prompt</div>', unsafe_allow_html=True)
    st.text_area(
        label="Prompt (hidden)",
        key="prompt_text",
        height=240,
        label_visibility="collapsed",
    )

    st.markdown("<div style='height:0.45rem'></div>", unsafe_allow_html=True)

    # Super-Prompt section
    st.markdown('<div class="field-title">Super-Prompt</div>', unsafe_allow_html=True)
    st.text_area(
        label="Super-Prompt (hidden)",
        key="super_prompt_text",
        height=780,
        label_visibility="collapsed",
    )


def render_right_panel() -> None:
    """Right panel: Memory at top, all controls below."""
    ctrl: AppController = st.session_state.controller
    retrieval_ready = getattr(ctrl, "retriever", None) is not None
    reranker_ready = getattr(ctrl, "reranker", None) is not None

    # Memory section
    render_memory_records(height=420)

    st.markdown("<div style='height:0.45rem'></div>", unsafe_allow_html=True)

    # Manual memory feed row
    manual_feed_c1, manual_feed_c2 = st.columns([1, 3], gap="small")

    with manual_feed_c1:  # Manual memory feed button
        if st.button(
            "Feed Memory Manually",
            key="btn_feed_memory_manually",
            use_container_width=True,
            type="primary",
        ):
            do_feed_memory_manually()

    with manual_feed_c2:  # Manual memory feed edit box
        st.text_area(
            label="Manual Memory Feed (hidden)",
            key="manual_memory_feed_text",
            height=68,
            label_visibility="collapsed",
            placeholder="Paste LLM reply here for manual memory feed.",
        )

    st.markdown("<div style='height:0.45rem'></div>", unsafe_allow_html=True)

    # Row 1: 4 pipeline buttons
    b1c1, b1c2, b1c3, b1c4 = st.columns(4, gap="small")

    with b1c1:  # Pre-Processing button
        if st.button("Pre-Processing", key="btn_preproc", use_container_width=True):
            do_preprocess()

    with b1c2:  # A2-PromptShaper button
        if st.button("A2-PromptShaper", key="btn_a2", use_container_width=True):
            do_a2_promptshaper()

    with b1c3:  # Retrieval button
        if st.button(
            "Retrieval",
            key="btn_retrieval",
            use_container_width=True,
            disabled=not retrieval_ready,
        ):
            do_retrieval()

    with b1c4:  # ReRanker button
        if st.button(
            "ReRanker",
            key="btn_reranker",
            use_container_width=True,
            disabled=not reranker_ready,
        ):
            do_reranker()

    # Row 2: 4 pipeline buttons
    b2c1, b2c2, b2c3, b2c4 = st.columns(4, gap="small")

    with b2c1:  # A3 NLI Gate button
        if st.button("A3 NLI Gate", key="btn_a3", use_container_width=True):
            do_a3_nli_gate()

    with b2c2:  # A4 button
        if st.button("A4 Condenser", key="btn_a4", use_container_width=True):
            do_a4_condenser()

    with b2c3:  # A5 button
        st.button("A5 Format Enforcer", key="btn_a5", use_container_width=True)

    with b2c4:  # Prompt Builder button
        st.button("Prompt Builder", key="btn_builder", use_container_width=True)

    topk_c, gap_c, opt_c1, opt_c2 = st.columns([0.5, 1, 1, 1],
                                               gap="small")  # row: Top-K + spacer + 2 checkboxes

    with topk_c:  # number input: Retrieval Top-K
        st.number_input(
            "Retrieval Top-K",
            min_value=1,
            max_value=1000,
            step=1,
            key="retrieval_top_k",
        )

    with gap_c:  # empty spacer between Top-K and first checkbox
        st.empty()

    with opt_c1:  # checkbox: use Retrieval Splade
        st.checkbox(
            "use Retrieval Splade",
            key="use_retrieval_splade",
        )

    with opt_c2:  # checkbox: use Reranking Colbert
        st.checkbox(
            "use Reranking Colbert",
            key="use_reranking_colbert",
        )

    st.markdown("<div style='height:0.45rem'></div>", unsafe_allow_html=True)

    # TextForge GUI log / status log
    render_textforge_gui_log(height=150)

    st.markdown("<div style='height:0.45rem'></div>", unsafe_allow_html=True)

    # Project controls / file ingestion
    render_project_area(ctrl)


def render_textforge_gui_log(height: int = 150) -> None:
    """Render the TextForge GUI log box."""
    st.markdown(
        '<div class="field-title" style="font-size:1.05rem;">Runtime Log</div>',
        unsafe_allow_html=True,
    )

    log_text = st.session_state.get("textforge_gui_log", "")
    if not log_text:
        log_text = "(no log messages yet)"

    lines = log_text.splitlines()
    if lines:
        first_line = html.escape(lines[0])
        older_lines = "<br>".join(
            f"<i>{html.escape(line)}</i>"
            for line in lines[1:]
        )
        if older_lines:
            log_html = f"{first_line}<br>{older_lines}"
        else:
            log_html = first_line
    else:
        log_html = ""

    flash_active = time.time() < st.session_state.get("runtime_log_flash_until", 0)

    if flash_active:
        log_box_style = (
            f"min-height:{height}px; max-height:{height}px;"
            "background-color:#FFE5E5; border-color:#FF9A9A;"
        )
    else:
        log_box_style = f"min-height:{height}px; max-height:{height}px;"

    st.markdown(
        f'<div class="textforge-log-box" style="{log_box_style}">{log_html}</div>',
        unsafe_allow_html=True,
    )


def render_memory_records(height: int = 420) -> None:
    """Memory record list."""
    memory_manager = st.session_state.memory_manager

    if memory_manager.filename_ragmem:
        memory_title = f"Memory — {memory_manager.filename_ragmem}"
    else:
        memory_title = "Memory"

    st.markdown(
        f'<div class="field-title">{html.escape(memory_title)}</div>',
        unsafe_allow_html=True,
    )

    if st.session_state.get("memory_title_required"):
        render_memory_title_form()

    memory_entries = memory_manager.records

    try:
        memory_container = st.container(height=height)
    except TypeError:
        memory_container = st.container()

    with memory_container:  # Memory container
        if not memory_entries:
            st.info("No memory records yet.")
        else:
            for record in memory_entries:
                tag_key = f"memory_tag_{record.record_id}"
                source_mode_key = f"memory_retrieval_source_mode_{record.record_id}"
                keywords_key = f"memory_user_keywords_{record.record_id}"
                direct_recall_key = f"memory_direct_recall_key_{record.record_id}"

                tag_options = list(memory_manager.tag_catalog)
                record_tag = record.tag if record.tag in tag_options else "Green"

                if tag_key not in st.session_state:
                    st.session_state[tag_key] = record_tag
                elif st.session_state[tag_key] not in tag_options:
                    st.session_state[tag_key] = "Green"

                if source_mode_key not in st.session_state:
                    st.session_state[source_mode_key] = getattr(record, "retrieval_source_mode", "QA")
                elif st.session_state[source_mode_key] not in {"QA", "Q", "A"}:
                    st.session_state[source_mode_key] = "QA"

                if keywords_key not in st.session_state:
                    st.session_state[keywords_key] = ", ".join(record.user_keywords)

                if direct_recall_key not in st.session_state:
                    st.session_state[direct_recall_key] = getattr(record, "direct_recall_key", "")

                selected_tag = st.session_state.get(tag_key, record_tag)
                tag_color = TAG_COLORS.get(selected_tag, "#6B7280")

                input_col, meta_col = st.columns([7.8, 2.0], gap="small")

                with input_col:  # Memory INPUT box
                    input_html = html.escape(record.input_text).replace("\n", "<br>")
                    st.markdown(
                        f"""
                        <div class="memory-box memory-input-box">
                            <div class="memory-label">INPUT</div>
                            <div class="memory-plain-text">{input_html}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                with meta_col:  # Memory metadata controls
                    tag_square_col, tag_select_col = st.columns([0.22, 1.0], gap="small")

                    with tag_square_col:
                        st.markdown(
                            f"""
                            <div class="memory-tag-indicator">
                                <span class="memory-tag-square" style="background-color:{tag_color};"></span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    with tag_select_col:
                        st.selectbox(
                            "Tag",
                            options=tag_options,
                            key=tag_key,
                            label_visibility="collapsed",
                        )

                    st.selectbox(
                        "Retrieval Source Mode",
                        options=["QA", "Q", "A"],
                        key=source_mode_key,
                        format_func={
                            "QA": "Retrieve Q+A",
                            "Q": "Retrieve only Q",
                            "A": "Retrieve only A",
                        }.get,
                        label_visibility="collapsed",
                    )

                   # st.text_input(
                    #    "User Keywords",
                     #   key=keywords_key,
                      #  label_visibility="collapsed",
                       # placeholder="keywords",
                    #)

                    st.text_input(
                        "Direct Recall Key",
                        key=direct_recall_key,
                        placeholder="Direct Recall Key",
                     #   label_visibility="collapsed",
                    )

                output_html = html.escape(record.output_text).replace("\n", "<br>")
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


def render_memory_title_form() -> None:
    """Ask for first memory title before creating the first .ragmem file."""
    with st.form("memory_title_form", clear_on_submit=False):
        st.text_input(
            "Memory Title",
            key="memory_title_input",
            placeholder="Example: Memory Design",
        )
        submitted = st.form_submit_button("Create Memory File", use_container_width=True)

        if submitted:
            do_confirm_memory_title_and_save()


def render_project_area(ctrl: AppController) -> None:
    """Project selector, embedded files, Create Project and Add Files forms."""
    projects = ctrl.list_projects()

    # Apply pending project switch before widget creation
    pending_project = st.session_state.get("pending_active_project")
    if pending_project is not None:
        if projects and pending_project in projects:
            st.session_state["active_project"] = pending_project
        st.session_state["pending_active_project"] = None

    # Active project selectbox
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

    # Embedded Files view
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

    # Project forms row
    create_col, add_col = st.columns(2, gap="small")

    with create_col:  # Create Project form
        with st.form("create_project_form", clear_on_submit=False):  # form: create project
            st.text_input("Project Name", key="new_project_name")
            create_clicked = st.form_submit_button("Create Project", use_container_width=True)

            if create_clicked:
                do_create_project()

    with add_col:  # Add Files form
        with st.form("add_files_form", clear_on_submit=False):  # form: add files
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

                st.file_uploader(
                    "Select .txt / .md files from your local machine",
                    type=["txt", "md"],
                    accept_multiple_files=True,
                    key="ingestion_uploaded_files",
                )

                add_clicked = st.form_submit_button("Add Files", use_container_width=True)

                if add_clicked:
                    do_add_files()
            else:
                st.info("Create a project first, then add files.")

    # Status area
    status = st.session_state.get("ingestion_status")
    if status:
        if status.get("type") == "success":
            st.success(status.get("message", ""))
        else:
            st.error(status.get("message", ""))
        for detail in status.get("details", []):
            st.caption(detail)
```

### ~\ragstream\app\ui_streamlit.py
```python
# ragstream/app/ui_streamlit.py
# -*- coding: utf-8 -*-
"""
Run on a free port, e.g.:
  /home/rusbeh_ab/venvs/ragstream/bin/python -m streamlit run /home/rusbeh_ab/project/RAGstream/ragstream/app/ui_streamlit.py --server.port 8503
"""

from __future__ import annotations

import threading

from pathlib import Path

import streamlit as st

from ragstream.app.controller import AppController
from ragstream.app.ui_layout import inject_base_css, render_page
from ragstream.ingestion.embedder import Embedder
from ragstream.memory.memory_chunker import MemoryChunker
from ragstream.memory.memory_ingestion_manager import MemoryIngestionManager
from ragstream.memory.memory_manager import MemoryManager
from ragstream.memory.memory_vector_store import MemoryVectorStore
from ragstream.orchestration.super_prompt import SuperPrompt
from ragstream.textforge.RagLog import LogALL as logger


def init_session_state() -> None:
    """Create one controller + one SuperPrompt set per user session."""
    if "controller" not in st.session_state:
        ctrl = AppController()
        st.session_state.controller = ctrl

    if "textforge_gui_log" not in st.session_state:
        st.session_state["textforge_gui_log"] = ""

    if "memory_manager" not in st.session_state:
        project_root = Path(__file__).resolve().parents[2]
        memory_root = project_root / "data" / "memory"
        sqlite_path = memory_root / "memory_index.sqlite3"

        st.session_state.memory_manager = MemoryManager(
            memory_root=memory_root,
            sqlite_path=sqlite_path,
            title="",
        )

    if "memory_ingestion_manager" not in st.session_state:
        project_root = Path(__file__).resolve().parents[2]
        memory_root = project_root / "data" / "memory"
        memory_vector_root = memory_root / "vector_db"

        memory_chunker = MemoryChunker()

        memory_embedder = Embedder(model="text-embedding-3-large")

        memory_vector_store = MemoryVectorStore(
            persist_dir=str(memory_vector_root),
            collection_name="memory_vectors",
            embedder=memory_embedder,
        )

        st.session_state.memory_ingestion_manager = MemoryIngestionManager(
            memory_manager=st.session_state.memory_manager,
            memory_chunker=memory_chunker,
            memory_vector_store=memory_vector_store,
        )

        logger(
            "Memory ingestion layer ready: data/memory/vector_db/ | collection=memory_vectors",
            "INFO",
            "PUBLIC",
        )

    if "heavy_init_started" not in st.session_state:
        st.session_state["heavy_init_started"] = False

    if not st.session_state["heavy_init_started"]:
        ctrl: AppController = st.session_state.controller

        t = threading.Thread(
            target=ctrl.initialize_heavy_components,
            daemon=True,
        )
        t.start()

        st.session_state["heavy_init_started"] = True

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
    if "sp_a3" not in st.session_state:
        st.session_state.sp_a3 = SuperPrompt()
    if "sp_a4" not in st.session_state:
        st.session_state.sp_a4 = SuperPrompt()

    if "super_prompt_text" not in st.session_state:
        st.session_state["super_prompt_text"] = ""

    if "ingestion_status" not in st.session_state:
        st.session_state["ingestion_status"] = None

    if "new_project_name" not in st.session_state:
        st.session_state["new_project_name"] = ""

    if "pending_active_project" not in st.session_state:
        # Temporary project switch key
        st.session_state["pending_active_project"] = None

    if "retrieval_top_k" not in st.session_state:
        st.session_state["retrieval_top_k"] = 30

    if "use_retrieval_splade" not in st.session_state:
        st.session_state["use_retrieval_splade"] = False

    if "use_reranking_colbert" not in st.session_state:
        st.session_state["use_reranking_colbert"] = False

    if "manual_memory_feed_text" not in st.session_state:
        st.session_state["manual_memory_feed_text"] = ""

    if "memory_title_required" not in st.session_state:
        st.session_state["memory_title_required"] = False

    if "pending_manual_memory_pair" not in st.session_state:
        st.session_state["pending_manual_memory_pair"] = None

    if "memory_title_input" not in st.session_state:
        st.session_state["memory_title_input"] = ""


def main() -> None:
    st.set_page_config(page_title="RAGstream", layout="wide")

    # Base CSS / compact styles
    inject_base_css()

    # Page title
    st.title("RAGstream")

    # Session bootstrap / background heavy init
    init_session_state()

    # Page layout
    render_page()


if __name__ == "__main__":
    main()
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

    def split(self, file_path: str, text: str, chunk_size: int = 1200, overlap: int = 120) -> List[Tuple[str, str]]:
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
    • Also supports an optional parallel SPLADE sparse-ingestion branch.

Notes:
    • We compute file hashes from bytes on disk (compute_sha256), NOT from text.
    • Chunk IDs are stable: f"{rel_path}::{sha256}::{idx}" (matches your store helpers).
    • We only publish a new manifest after all target files in this run succeed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

# Local imports: existing dense components
from .loader import DocumentLoader
from .chunker import Chunker
from .embedder import Embedder
from .vector_store_chroma import VectorStoreChroma

# Added on 13.04.2026:
# Optional sparse SPLADE ingestion components.
from .splade_embedder import SpladeEmbedder
from .vector_store_splade import VectorStoreSplade

# Manifest utilities
from .file_manifest import (
    compute_sha256,
    load_manifest,
    diff as manifest_diff,
    publish_atomic,
    Record,
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
    embedded_bytes: int

    # Added on 13.04.2026:
    # Split counters for the parallel dense + sparse branches.
    dense_vectors_upserted: int
    sparse_vectors_upserted: int
    dense_embedded_bytes: int
    sparse_embedded_bytes: int


class IngestionManager:
    """
    Coordinates the full ingestion pipeline for a given doc root.
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

    def run(
        self,
        subfolder: str,
        store: VectorStoreChroma,
        chunker: Chunker,
        embedder: Embedder,
        manifest_path: str,
        *,
        sparse_store: VectorStoreSplade | None = None,
        sparse_embedder: SpladeEmbedder | None = None,
        chunk_size: int = 1200,
        overlap: int = 120,
        delete_old_versions: bool = True,
        delete_tombstones: bool = False,
    ) -> IngestionStats:
        """
        Execute a full ingestion cycle for one subfolder under doc_root.

        Dense branch is always active.
        Sparse SPLADE branch is active only if both sparse_store and sparse_embedder are provided.

        Returns:
            IngestionStats with useful counters.
        """
        manifest_path = str(Path(manifest_path).resolve())

        use_sparse = (sparse_store is not None) or (sparse_embedder is not None)
        if use_sparse and (sparse_store is None or sparse_embedder is None):
            raise ValueError(
                "Sparse ingestion requires both sparse_store and sparse_embedder."
            )

        # 1) Load documents (absolute path + raw text) from the subfolder.
        docs = self.loader.load_documents(subfolder)
        text_by_abs: Dict[str, str] = {abs_path: text for abs_path, text in docs}

        # 2) Build current Records by hashing files on disk (bytes).
        records_now: List[Record] = []
        for abs_path, _text in docs:
            ap = Path(abs_path)
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

        prev_by_path: Dict[str, Record] = {
            rec["path"]: rec for rec in manifest_prev.get("files", [])
        }

        # 4) Process changed/new files (shared chunking pass → dense and optional sparse upsert).
        total_chunks = 0
        total_deleted_old = 0

        dense_upserts = 0
        sparse_upserts = 0

        dense_embedded_bytes = 0
        sparse_embedded_bytes = 0

        for rec in to_process:
            rel_path = rec["path"]
            sha_new = rec["sha256"]

            abs_path = (self.doc_root / rel_path).as_posix()
            text = text_by_abs.get(abs_path)
            if text is None:
                text = Path(abs_path).read_text(encoding="utf-8", errors="ignore")

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
                continue

            if delete_old_versions and rel_path in prev_by_path:
                sha_old = prev_by_path[rel_path]["sha256"]
                if sha_old != sha_new:
                    total_deleted_old += self._delete_file_version(store, rel_path, sha_old)
                    if use_sparse and sparse_store is not None:
                        total_deleted_old += self._delete_file_version(sparse_store, rel_path, sha_old)

            file_embedded_bytes = sum(len(s.encode("utf-8")) for s in chunk_texts)

            # Dense branch
            dense_vecs = embedder.embed(chunk_texts)
            store.add(ids=ids, vectors=dense_vecs, metadatas=metas)
            dense_upserts += len(ids)
            dense_embedded_bytes += file_embedded_bytes

            # Optional sparse branch
            if use_sparse and sparse_store is not None and sparse_embedder is not None:
                sparse_vecs = sparse_embedder.embed(chunk_texts)
                sparse_store.add(ids=ids, vectors=sparse_vecs, metadatas=metas)
                sparse_upserts += len(ids)
                sparse_embedded_bytes += file_embedded_bytes

            total_chunks += len(chunk_texts)

        # 5) Optionally delete tombstones (files that disappeared from disk).
        total_deleted_tombs = 0
        if delete_tombstones and tombstones:
            for prev_rec in tombstones:
                rel_path = prev_rec["path"]
                sha_prev = prev_rec["sha256"]

                total_deleted_tombs += self._delete_file_version(store, rel_path, sha_prev)
                if use_sparse and sparse_store is not None:
                    total_deleted_tombs += self._delete_file_version(sparse_store, rel_path, sha_prev)

        # 6) Publish a fresh manifest that reflects the CURRENT disk state.
        manifest_new = {
            "version": "1",
            "generated_at": "",
            "files": records_now,
        }
        publish_atomic(manifest_new, manifest_path)

        return IngestionStats(
            files_scanned=len(records_now),
            to_process=len(to_process),
            unchanged=len(unchanged),
            tombstones=len(tombstones),
            chunks_added=total_chunks,
            vectors_upserted=dense_upserts + sparse_upserts,
            deleted_old_versions=total_deleted_old,
            deleted_tombstones=total_deleted_tombs,
            published_manifest_path=manifest_path,
            embedded_bytes=dense_embedded_bytes + sparse_embedded_bytes,
            dense_vectors_upserted=dense_upserts,
            sparse_vectors_upserted=sparse_upserts,
            dense_embedded_bytes=dense_embedded_bytes,
            sparse_embedded_bytes=sparse_embedded_bytes,
        )

    @staticmethod
    def _delete_file_version(store: Any, rel_path: str, sha256: str) -> int:
        """
        Remove all chunks belonging to one specific file version.

        Uses the store's native delete_file_version(...) when available.
        Falls back to metadata-filter delete_where(...) if needed.
        """
        if hasattr(store, "delete_file_version"):
            return int(store.delete_file_version(rel_path, sha256))

        before = IngestionManager._count_ids(store, rel_path, sha256)
        store.delete_where({"$and": [{"path": rel_path}, {"sha256": sha256}]})
        after = IngestionManager._count_ids(store, rel_path, sha256)
        return max(0, before - after)

    @staticmethod
    def _count_ids(store: Any, rel_path: str, sha256: str) -> int:
        """
        Return how many IDs exist for a given (path, sha256) pair.
        """
        # Dense Chroma store
        if hasattr(store, "collection"):
            res = store.collection.get(
                where={"$and": [{"path": rel_path}, {"sha256": sha256}]},
                include=[],
            )
            ids = res.get("ids", []) if res else []
            return len(ids)

        # Local sparse SPLADE store
        meta_store = getattr(store, "_meta_store", None)
        if isinstance(meta_store, dict):
            return sum(
                1
                for meta in meta_store.values()
                if meta.get("path") == rel_path and meta.get("sha256") == sha256
            )

        return 0
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

### ~\ragstream\ingestion\splade_embedder.py
```python
# -*- coding: utf-8 -*-
"""
splade_embedder.py

Purpose:
    SPLADE-side counterpart of embedder.py for RAGstream ingestion.

Role in architecture:
    - Dense side:
        Embedder.embed(texts) -> List[List[float]]
    - Sparse SPLADE side:
        SpladeEmbedder.embed(texts) -> List[Dict[str, float]]

Design goals:
    - Keep the public ingestion-facing API parallel to Embedder:
        embed(texts) -> one sparse representation per text
    - Add query-specific helpers for the later retrieval phase:
        embed_queries(...)
        embed_query(...)
    - Persist nothing here; this module is encoder-only.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

try:
    import torch
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "splade_embedder.py requires PyTorch. Please install torch first."
    ) from exc

try:
    from sentence_transformers import SparseEncoder
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "splade_embedder.py requires sentence-transformers with SparseEncoder support."
    ) from exc


SparseVector = Dict[str, float]


class SpladeEmbedder:
    """
    High-level SPLADE sparse encoder.

    Public API is intentionally parallel to dense Embedder where possible:
        - embed(texts)         : document-side sparse encoding for ingestion
        - embed_queries(texts) : query-side sparse encoding for retrieval
        - embed_query(text)    : single-query convenience wrapper

    Internal sparse representation:
        Dict[str, float]
            key   = vocabulary dimension id as string
            value = SPLADE weight for that active dimension
    """

    def __init__(
        self,
        model: str = "naver/splade-cocondenser-ensembledistil",
        *,
        device: str = "cpu",
        backend: str = "torch",
        batch_size: int = 16,
        max_active_dims: int | None = 256,
        show_progress_bar: bool = False,
    ) -> None:
        """
        Args:
            model:
                SPLADE model name or local path.
            device:
                Usually "cpu" on your laptop for now.
            backend:
                SparseEncoder backend, e.g. "torch", "onnx", "openvino".
            batch_size:
                Default batch size for encoding.
            max_active_dims:
                Optional cap on active dimensions to keep sparse output bounded.
            show_progress_bar:
                Whether Sentence Transformers should show progress bars.
        """
        self.model = model
        self.device = device
        self.backend = backend
        self.batch_size = int(batch_size)
        self.max_active_dims = max_active_dims
        self.show_progress_bar = bool(show_progress_bar)

        self.encoder = SparseEncoder(
            model,
            device=device,
            backend=backend,
            max_active_dims=max_active_dims,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(self, texts: List[str]) -> List[SparseVector]:
        """
        Document-side sparse encoding for ingestion.

        This is the ingestion-parallel counterpart of dense Embedder.embed(...).

        Args:
            texts:
                List of chunk texts.

        Returns:
            List[Dict[str, float]]:
                One sparse representation per input text.
        """
        return self._encode_documents(texts)

    def embed_queries(self, texts: List[str]) -> List[SparseVector]:
        """
        Query-side sparse encoding for retrieval.

        Kept here already so retriever_splade.py can later use the same class.
        """
        if not texts:
            return []

        raw = self.encoder.encode_query(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=self.show_progress_bar,
            convert_to_tensor=False,
            convert_to_sparse_tensor=True,
            save_to_cpu=True,
            max_active_dims=self.max_active_dims,
        )
        return [self._tensor_to_sparse_dict(t) for t in self._ensure_list(raw)]

    def embed_query(self, text: str) -> SparseVector:
        """
        Convenience wrapper for one retrieval query.
        """
        text = (text or "").strip()
        if not text:
            return {}
        return self.embed_queries([text])[0]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _encode_documents(self, texts: Sequence[str]) -> List[SparseVector]:
        if not texts:
            return []

        raw = self.encoder.encode_document(
            list(texts),
            batch_size=self.batch_size,
            show_progress_bar=self.show_progress_bar,
            convert_to_tensor=False,
            convert_to_sparse_tensor=True,
            save_to_cpu=True,
            max_active_dims=self.max_active_dims,
        )
        return [self._tensor_to_sparse_dict(t) for t in self._ensure_list(raw)]

    @staticmethod
    def _ensure_list(raw: object) -> List[torch.Tensor]:
        """
        Sentence Transformers may return a single tensor or a list of tensors,
        depending on input shape and conversion settings.
        """
        if isinstance(raw, list):
            return raw
        if isinstance(raw, torch.Tensor):
            return [raw]
        raise TypeError(f"Unsupported sparse encoder output type: {type(raw)!r}")

    @staticmethod
    def _tensor_to_sparse_dict(tensor: torch.Tensor) -> SparseVector:
        """
        Convert one sparse tensor into Dict[str, float].

        Expected common case:
            sparse COO tensor, shape [vocab_size]

        Fallback:
            dense tensor -> convert non-zero entries only
        """
        if tensor.is_sparse:
            t = tensor.coalesce()
            indices = t.indices()
            values = t.values()

            if indices.numel() == 0:
                return {}

            # 1D sparse vector: indices shape [1, nnz]
            # Defensive fallback: use last row if shape differs.
            if indices.dim() == 2:
                dim_ids = indices[-1].tolist()
            else:
                dim_ids = indices.tolist()

            return {
                str(int(dim_id)): float(value)
                for dim_id, value in zip(dim_ids, values.tolist())
                if float(value) != 0.0
            }

        # Dense fallback
        nonzero = torch.nonzero(tensor, as_tuple=False).flatten().tolist()
        if not nonzero:
            return {}

        return {
            str(int(idx)): float(tensor[idx].item())
            for idx in nonzero
            if float(tensor[idx].item()) != 0.0
        }
```

### ~\ragstream\ingestion\splade_vector_store_base.py
```python
# -*- coding: utf-8 -*-
"""
splade_vector_store_base.py

Shared, production-grade base class for a local SPLADE-backed sparse store.

Purpose:
    Provide the sparse-store analogue of chroma_vector_store_base.py, with the
    same public culture wherever possible:

        add(ids, vectors, metadatas) -> None
        query(vector, k=10, where=None) -> List[str]
        delete_where(where) -> None
        snapshot(timestamp=None) -> Path

Storage model:
    Local filesystem persistence under one project folder.
    The store persists:
        - sparse vectors by id
        - metadatas by id

Why local and simple:
    For your current architecture, SPLADE ingestion is the first step.
    Later retrieval can rescore a bounded set of chunk_ids efficiently from this
    store without requiring a full external search engine.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import os
import pickle
import shutil


SparseVector = Dict[str, float]


class SpladeVectorStoreBase:
    """
    Base implementation of a local persistent sparse store.

    Responsibilities:
      - Own one filesystem-backed sparse index bundle.
      - Provide deterministic add/query/delete/snapshot methods.
      - Offer policy hooks for subclasses, matching the Chroma base style.
    """

    def __init__(self, persist_dir: str, index_name: str) -> None:
        self.persist_path = Path(persist_dir)
        self.persist_path.mkdir(parents=True, exist_ok=True)

        self.index_name = index_name
        self._bundle_path = self.persist_path / f"{self.index_name}.pkl"

        self._index: Dict[str, SparseVector] = {}
        self._meta_store: Dict[str, Dict[str, Any]] = {}

        self._load()

    # ------------------------------------------------------------------
    # Public API (parallel to Chroma base)
    # ------------------------------------------------------------------

    def add(
        self,
        ids: List[str],
        vectors: List[SparseVector],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Upsert sparse vectors and metadatas into the local store.
        """
        if not ids or not vectors:
            return
        if len(ids) != len(vectors):
            raise ValueError("ids and vectors length mismatch")
        if metadatas is not None and len(metadatas) != len(ids):
            raise ValueError("metadatas length must match ids (or be None)")

        ids, vectors, metadatas = self._pre_add(ids, vectors, metadatas)

        metas = metadatas or [{} for _ in ids]

        for chunk_id, vector, meta in zip(ids, vectors, metas):
            self._index[chunk_id] = self._normalize_sparse_vector(vector)
            self._meta_store[chunk_id] = dict(meta)

        self._persist()
        self._post_add(ids, vectors, metadatas)

    def query(
        self,
        vector: SparseVector,
        k: int = 10,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Query the sparse store by sparse-vector dot product.

        Args:
            vector:
                Query sparse vector, same representation as stored doc vectors.
            k:
                Number of top results to return.
            where:
                Optional metadata filter, supporting:
                    - {"path": "...", "sha256": "..."}
                    - {"$and": [ ... ]}
                    - {"$or":  [ ... ]}
        """
        if not isinstance(vector, dict):
            raise ValueError("query vector must be a Dict[str, float]")

        k = max(1, int(k))
        vector, k, where = self._pre_query(vector, k, where)

        scored: List[tuple[str, float]] = []
        for chunk_id, doc_vec in self._index.items():
            meta = self._meta_store.get(chunk_id, {})

            if where and not self._metadata_matches(meta, where):
                continue

            score = self._dot_sparse(vector, doc_vec)
            scored.append((chunk_id, score))

        scored.sort(key=lambda row: (-row[1], row[0]))
        ids = [chunk_id for chunk_id, _score in scored[:k]]
        return self._post_query(ids, {"scored": scored})

    def delete_where(self, where: Dict[str, Any]) -> None:
        """
        Delete records by metadata filter.
        """
        if not where:
            return

        ids_to_delete = [
            chunk_id
            for chunk_id, meta in self._meta_store.items()
            if self._metadata_matches(meta, where)
        ]
        self._delete_ids(ids_to_delete)

    def snapshot(self, timestamp: Optional[str] = None) -> Path:
        """
        Create a filesystem snapshot of the persistent sparse store directory.
        """
        ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshots_dir = self.persist_path.parent / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        dst = snapshots_dir / f"{self.persist_path.name}_{ts}"

        shutil.copytree(self.persist_path, dst, dirs_exist_ok=False)
        return dst

    @property
    def index(self) -> Dict[str, SparseVector]:
        """
        Expose the underlying sparse vector mapping for advanced ops/debugging.
        """
        return self._index

    # ------------------------------------------------------------------
    # Hook methods (parallel to Chroma base)
    # ------------------------------------------------------------------

    def _pre_add(
        self,
        ids: List[str],
        vectors: List[SparseVector],
        metadatas: Optional[List[Dict[str, Any]]],
    ) -> tuple[List[str], List[SparseVector], Optional[List[Dict[str, Any]]]]:
        return ids, vectors, metadatas

    def _post_add(
        self,
        ids: List[str],
        vectors: List[SparseVector],
        metadatas: Optional[List[Dict[str, Any]]],
    ) -> None:
        return None

    def _pre_query(
        self,
        vector: SparseVector,
        k: int,
        where: Optional[Dict[str, Any]],
    ) -> tuple[SparseVector, int, Optional[Dict[str, Any]]]:
        return vector, k, where

    def _post_query(self, ids: List[str], raw_result: Dict[str, Any]) -> List[str]:
        return ids

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._bundle_path.exists():
            return

        with self._bundle_path.open("rb") as f:
            payload = pickle.load(f)

        self._index = dict(payload.get("index", {}))
        self._meta_store = dict(payload.get("metadatas", {}))

    def _persist(self) -> None:
        payload = {
            "version": "1",
            "index_name": self.index_name,
            "index": self._index,
            "metadatas": self._meta_store,
        }

        tmp_path = self._bundle_path.with_suffix(self._bundle_path.suffix + ".tmp")
        with tmp_path.open("wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)

        os.replace(str(tmp_path), str(self._bundle_path))

    def _delete_ids(self, ids: Iterable[str]) -> None:
        changed = False
        for chunk_id in ids:
            if chunk_id in self._index:
                del self._index[chunk_id]
                changed = True
            if chunk_id in self._meta_store:
                del self._meta_store[chunk_id]
                changed = True

        if changed:
            self._persist()

    @staticmethod
    def _normalize_sparse_vector(vector: SparseVector) -> SparseVector:
        """
        Remove zero entries and normalize key/value types.
        """
        normalized: SparseVector = {}
        for key, value in vector.items():
            fval = float(value)
            if fval != 0.0:
                normalized[str(key)] = fval
        return normalized

    @staticmethod
    def _dot_sparse(left: SparseVector, right: SparseVector) -> float:
        """
        Dot product over sparse dicts.

        Iterate over the smaller dict for efficiency.
        """
        if len(left) > len(right):
            left, right = right, left

        score = 0.0
        for key, value in left.items():
            score += float(value) * float(right.get(key, 0.0))
        return score

    @classmethod
    def _metadata_matches(cls, metadata: Dict[str, Any], where: Dict[str, Any]) -> bool:
        """
        Minimal local filter engine compatible with the current ingestion needs.

        Supported:
            {"path": "..."}
            {"sha256": "..."}
            {"$and": [cond1, cond2, ...]}
            {"$or":  [cond1, cond2, ...]}
        """
        if not where:
            return True

        if "$and" in where:
            conditions = where["$and"]
            if not isinstance(conditions, list):
                raise ValueError("$and value must be a list")
            return all(cls._metadata_matches(metadata, cond) for cond in conditions)

        if "$or" in where:
            conditions = where["$or"]
            if not isinstance(conditions, list):
                raise ValueError("$or value must be a list")
            return any(cls._metadata_matches(metadata, cond) for cond in conditions)

        for key, expected in where.items():
            if key.startswith("$"):
                raise ValueError(f"Unsupported filter operator: {key}")
            if metadata.get(key) != expected:
                return False

        return True
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

### ~\ragstream\ingestion\vector_store_splade.py
```python
# -*- coding: utf-8 -*-
"""
vector_store_splade.py

Concrete sparse document store for RAGstream, backed by SpladeVectorStoreBase.

This is the sparse-side counterpart of vector_store_chroma.py.

Usage:
    store = VectorStoreSplade(persist_dir=".../data/splade_db/project1")
    store.add(ids=[...], vectors=[...], metadatas=[...])
    top_ids = store.query(vector=q_sparse, k=5)
    snap_dir = store.snapshot()
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .splade_vector_store_base import SpladeVectorStoreBase


class VectorStoreSplade(SpladeVectorStoreBase):
    """
    Local persistent sparse store for document chunks.

    Responsibilities:
      - Provide a ready-to-use sparse project store (default: "docs_sparse").
      - Reuse base add/query/snapshot/delete_where without policy overrides.
      - Offer the same tiny convenience helpers as VectorStoreChroma wherever
        possible, so both branches stay structurally parallel.
    """

    def __init__(self, persist_dir: str, index_name: str = "docs_sparse") -> None:
        super().__init__(persist_dir=persist_dir, index_name=index_name)

    @staticmethod
    def make_chunk_id(rel_path: str, sha256: str, chunk_idx: int) -> str:
        """
        Deterministic chunk id format shared with the dense branch.
        Example: "docs/Req.md::a1b2c3...::12"
        """
        return f"{rel_path}::{sha256}::{chunk_idx}"

    def delete_file_version(self, rel_path: str, sha256: str) -> int:
        """
        Remove all chunks belonging to one specific file content version.

        This mirrors VectorStoreChroma.delete_file_version(...).
        """
        ids = [
            chunk_id
            for chunk_id, meta in self._meta_store.items()
            if meta.get("path") == rel_path and meta.get("sha256") == sha256
        ]
        self._delete_ids(ids)
        return len(ids)

    @property
    def name(self) -> str:
        """
        Return the logical sparse index name.
        """
        return self.index_name

    @property
    def persist_root(self) -> Path:
        """
        Return the directory containing the on-disk sparse store.
        """
        return self.persist_path

    def count(self) -> int:
        """
        Return total number of stored sparse vectors.
        """
        return len(self._index)
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
    factory.get_agent("a2_promptshaper", "003")
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
        if agents_root is None:
            repo_root = Path(__file__).resolve().parents[2]
            agents_root = repo_root / "data" / "agents"

        self.agents_root: Path = agents_root
        self._cache: Dict[Tuple[str, str], AgentPrompt] = {}

        SimpleLogger.info(f"AgentFactory initialized with agents_root={self.agents_root}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_config_path(self, agent_id: str, version: str) -> Path:
        return self.agents_root / agent_id / f"{version}.json"

    def _load_json_file(self, path: Path) -> Dict[str, Any]:
        if not path.is_file():
            msg = f"AgentFactory: JSON file not found at {path}"
            SimpleLogger.error(msg)
            raise FileNotFoundError(msg)

        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            msg = f"AgentFactory: failed to load JSON from {path}: {exc}"
            SimpleLogger.error(msg)
            raise RuntimeError(msg) from exc

        if not isinstance(data, dict):
            msg = f"AgentFactory: top-level JSON in {path} must be an object/dict"
            SimpleLogger.error(msg)
            raise ValueError(msg)

        return data

    def _extract_catalog_block(
        self,
        *,
        catalog: Dict[str, Any],
        target_id: str,
        catalog_path: Path,
    ) -> Dict[str, Any]:
        """
        Extract one decision-target block from an external catalog.

        Supported neutral shapes:

        1) Wrapped-by-target_id
           {
             "system": {
               "options": [...],
               "default": ...
             }
           }

        2) Direct/root block
           {
             "options": [...],
             "default": ...
           }

        3) Single-valid-block fallback
           {
             "<some_other_name>": {
               "options": [...],
               "default": ...
             }
           }

        Shape (3) remains neutral and is accepted only when there is exactly
        one valid block in the catalog, so no agent-specific logic is needed.
        """
        exact_block = catalog.get(target_id)
        if isinstance(exact_block, dict):
            return exact_block

        root_options = catalog.get("options")
        if isinstance(root_options, list):
            return catalog

        valid_blocks: Dict[str, Dict[str, Any]] = {}
        for key, value in catalog.items():
            if isinstance(value, dict) and isinstance(value.get("options"), list):
                valid_blocks[key] = value

        if len(valid_blocks) == 1:
            block_name, block = next(iter(valid_blocks.items()))
            SimpleLogger.info(
                "AgentFactory: catalog fallback accepted single valid block "
                f"'{block_name}' for decision_target id='{target_id}' from {catalog_path}"
            )
            return block

        msg = (
            f"AgentFactory: catalog {catalog_path} does not contain a valid block "
            f"for decision_target id='{target_id}'"
        )
        SimpleLogger.error(msg)
        raise KeyError(msg)

    def _resolve_decision_targets(
        self,
        *,
        config: Dict[str, Any],
        cfg_path: Path,
    ) -> Dict[str, Any]:
        """
        Resolve external catalog references inside decision_targets.

        Neutral convention:
        - main config contains decision_targets
        - each target may point to an external catalog file via:
              "options": "a2_catalogs/003_option_catalogs_system.json"
        - supported external catalog shapes are handled by _extract_catalog_block()

        Result:
        - options path string is replaced by the real inline options list
        - default from the catalog is copied into the decision target
        """
        targets = config.get("decision_targets")
        if not isinstance(targets, list):
            return config

        resolved_targets = []
        base_dir = cfg_path.parent

        for target in targets:
            if not isinstance(target, dict):
                continue

            target_id = target.get("id")
            if not target_id:
                continue

            resolved = dict(target)
            options_ref = resolved.get("options")

            if isinstance(options_ref, str):
                catalog_path = base_dir / options_ref
                catalog = self._load_json_file(catalog_path)
                block = self._extract_catalog_block(
                    catalog=catalog,
                    target_id=str(target_id),
                    catalog_path=catalog_path,
                )

                options_list = block.get("options", [])
                if not isinstance(options_list, list):
                    msg = (
                        f"AgentFactory: catalog block for '{target_id}' in {catalog_path} "
                        f"has invalid 'options' (expected list)"
                    )
                    SimpleLogger.error(msg)
                    raise ValueError(msg)

                resolved["options"] = options_list

                if "default" in block:
                    resolved["default"] = block["default"]

            resolved_targets.append(resolved)

        config["decision_targets"] = resolved_targets
        return config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_config(self, agent_id: str, version: str) -> Dict[str, Any]:
        cfg_path = self._build_config_path(agent_id, version)
        config = self._load_json_file(cfg_path)
        config = self._resolve_decision_targets(config=config, cfg_path=cfg_path)
        return config

    def get_agent(self, agent_id: str, version: str = "001") -> AgentPrompt:
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
        self._cache.clear()
        SimpleLogger.info("AgentFactory: cache cleared")
```

### ~\ragstream\orchestration\agent_prompt.py
```python
# ragstream/orchestration/agent_prompt.py
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

Neutrality rule:
- No agent-specific visible wording is invented here.
- Visible prompt wording must come from JSON or from the agent runtime payload.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

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
    build_user_text_for_selector,
    build_user_text_for_classifier,
    build_user_text_for_synthesizer,
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
        static_prompt: Dict[str, Any],
        dynamic_bindings: List[Dict[str, Any]],
        decision_targets: List[Dict[str, Any]],
        output_schema: Dict[str, Any],
        enums: Dict[str, List[str]],
        defaults: Dict[str, Any],
        cardinality: Dict[str, str],
        option_descriptions: Dict[str, Dict[str, str]],
        option_labels: Dict[str, Dict[str, str]],
        model_name: str,
        temperature: float,
        max_output_tokens: int,
        elements_order: Optional[List[str]] = None,
    ) -> None:
        self.agent_name: str = agent_name
        self.version: str = version
        self.mode: str = mode  # "selector" | "classifier" | "synthesizer" | "writer" | "extractor" | "scorer"

        self.static_prompt: Dict[str, Any] = static_prompt
        self.dynamic_bindings: List[Dict[str, Any]] = dynamic_bindings
        self.decision_targets: List[Dict[str, Any]] = decision_targets
        self.output_schema: Dict[str, Any] = output_schema
        self.elements_order: List[str] = list(elements_order or [])

        self.enums: Dict[str, List[str]] = enums
        self.defaults: Dict[str, Any] = defaults
        self.cardinality: Dict[str, str] = cardinality
        self.option_descriptions: Dict[str, Dict[str, str]] = option_descriptions
        self.option_labels: Dict[str, Dict[str, str]] = option_labels

        self.model_name: str = model_name
        self.temperature: float = temperature
        self.max_output_tokens: int = max_output_tokens

        self._result_keys: Dict[str, str] = build_result_key_map(output_schema)
        self._top_level_result_keys: Dict[str, str] = self._build_field_map(
            output_schema.get("top_level_fields", []) or output_schema.get("fields", []) or []
        )
        self._item_result_keys: Dict[str, str] = self._build_field_map(
            output_schema.get("item_fields", []) or []
        )

        if self.mode not in ("selector", "classifier", "synthesizer", "writer", "extractor", "scorer"):
            SimpleLogger.error(f"AgentPrompt[{self.agent_name}] unknown mode: {self.mode}")

    @staticmethod
    def _build_field_map(fields_cfg: List[Dict[str, Any]]) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for field in fields_cfg:
            field_id = field.get("field_id")
            if not field_id:
                continue
            result[field_id] = field.get("result_key", field_id)
        return result

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "AgentPrompt":
        agent_meta = config.get("agent_meta", {}) or {}
        llm_cfg = config.get("llm_config", {}) or {}
        output_schema = config.get("output_schema", {}) or {}

        static_prompt = config.get("static_prompt", {}) or {}
        dynamic_bindings = config.get("dynamic_bindings", []) or []
        decision_targets = config.get("decision_targets", []) or []
        elements_order = config.get("elements_order", []) or []

        if not static_prompt:
            prompt_profile = config.get("prompt_profile", {}) or {}
            static_prompt = {
                "system_role": prompt_profile.get("system_role", ""),
                "agent_purpose": prompt_profile.get("agent_purpose", ""),
                "notes": prompt_profile.get("notes", ""),
            }

        if not decision_targets:
            decision_targets = config.get("fields", []) or []

        agent_name = agent_meta.get("agent_id") or agent_meta.get("agent_name") or "unknown_agent"
        version = str(agent_meta.get("version", "000"))

        raw_mode = str(agent_meta.get("agent_type", "selector")).strip().lower()
        mode_aliases = {
            "chooser": "selector",
            "multi-chooser": "classifier",
            "multi_chooser": "classifier",
        }
        mode = mode_aliases.get(raw_mode, raw_mode)

        model_name = llm_cfg.get("model_name", "gpt-4.1-mini")
        temperature = float(llm_cfg.get("temperature", 0.0))
        max_tokens = int(llm_cfg.get("max_tokens", 256))

        enums, defaults, cardinality, opt_desc, opt_labels = extract_field_config(decision_targets)

        return cls(
            agent_name=agent_name,
            version=version,
            mode=mode,
            static_prompt=static_prompt,
            dynamic_bindings=dynamic_bindings,
            decision_targets=decision_targets,
            output_schema=output_schema,
            enums=enums,
            defaults=defaults,
            cardinality=cardinality,
            option_descriptions=opt_desc,
            option_labels=opt_labels,
            model_name=model_name,
            temperature=temperature,
            max_output_tokens=max_tokens,
            elements_order=elements_order,
        )

    @property
    def model(self) -> str:
        return self.model_name

    @property
    def max_tokens(self) -> int:
        return self.max_output_tokens

    def compose(
        self,
        input_payload: Dict[str, Any],
        active_fields: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        """
        Build SYSTEM + USER messages and the response_format for the LLM.

        Neutrality rule:
        - SYSTEM text comes from JSON-owned config sections handled by AgentPrompt.
        - USER text comes only from dynamic_bindings + runtime payload.
        """
        for binding in self.dynamic_bindings:
            binding_id = binding.get("id")
            if not binding_id:
                continue
            if binding.get("required", False) and binding_id not in input_payload:
                raise AgentPromptValidationError(
                    f"AgentPrompt[{self.agent_name}] missing required input binding: '{binding_id}'"
                )

        if self.mode == "selector":
            if active_fields is None:
                active_list: List[str] = list(self.enums.keys())
            else:
                active_list = [field_id for field_id in active_fields if field_id in self.enums]
        elif self.mode == "classifier":
            if active_fields is None:
                active_list = list(self.enums.keys())
            else:
                active_list = [field_id for field_id in active_fields if field_id in self.enums]
        else:
            active_list = []

        system_text, system_consumed_binding_ids = build_system_text(
            static_prompt=self.static_prompt,
            agent_name=self.agent_name,
            version=self.version,
            decision_targets=self.decision_targets,
            result_keys=self._result_keys,
            enums=self.enums,
            option_labels=self.option_labels,
            option_descriptions=self.option_descriptions,
            active_fields=active_list,
            input_payload=input_payload,
            dynamic_bindings=self.dynamic_bindings,
            elements_order=self.elements_order,
        )

        if self.mode == "selector":
            user_text = build_user_text_for_selector(
                input_payload=input_payload,
                dynamic_bindings=self.dynamic_bindings,
                consumed_binding_ids=system_consumed_binding_ids,
            )
        elif self.mode == "classifier":
            user_text = build_user_text_for_classifier(
                input_payload=input_payload,
                dynamic_bindings=self.dynamic_bindings,
                consumed_binding_ids=system_consumed_binding_ids,
            )
        elif self.mode == "synthesizer":
            user_text = build_user_text_for_synthesizer(
                input_payload=input_payload,
                dynamic_bindings=self.dynamic_bindings,
                consumed_binding_ids=system_consumed_binding_ids,
            )
        else:
            raise AgentPromptValidationError(
                f"AgentPrompt[{self.agent_name}] compose() currently only supports "
                f"mode='selector', mode='classifier', or mode='synthesizer'"
            )

        messages = [{"role": "system", "content": system_text}]
        if user_text.strip():
            messages.append({"role": "user", "content": user_text})

        response_format = {"type": "json_object"}

        SimpleLogger.info(f"AgentPrompt[{self.agent_name}] SYSTEM prompt:")
        SimpleLogger.info(system_text)
        SimpleLogger.info(f"AgentPrompt[{self.agent_name}] USER prompt:")
        SimpleLogger.info(user_text)

        return messages, response_format

    def parse(
        self,
        raw_output: Any,
        active_fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Parse and validate the LLM raw output into a clean Python dict.
        """
        json_obj = extract_json_object(raw_output)

        if self.mode == "selector":
            if active_fields is None:
                active_list: List[str] = list(self.enums.keys())
            else:
                active_list = [field_id for field_id in active_fields if field_id in self.enums]

            active_set = set(active_list)
            result: Dict[str, Any] = {}

            for field_id, allowed in self.enums.items():
                if field_id not in active_set:
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

        if self.mode == "classifier":
            result: Dict[str, Any] = {}

            for field_id, result_key in self._top_level_result_keys.items():
                raw_value = json_obj.get(result_key, "")
                if isinstance(raw_value, str):
                    result[field_id] = raw_value.strip().lower()
                elif raw_value is None:
                    result[field_id] = ""
                else:
                    result[field_id] = str(raw_value).strip()

            root_key = self.output_schema.get("root_key", "item_decisions")
            item_id_key = self.output_schema.get("item_id_key", "chunk_id")

            raw_items = json_obj.get(root_key, []) or []
            if not isinstance(raw_items, list):
                raw_items = []

            normalized_items: List[Dict[str, Any]] = []

            for raw_item in raw_items:
                if not isinstance(raw_item, dict):
                    continue

                raw_chunk_id = raw_item.get(item_id_key)
                if raw_chunk_id is None:
                    continue

                chunk_id = str(raw_chunk_id).strip()
                if not chunk_id:
                    continue

                item_result: Dict[str, Any] = {item_id_key: chunk_id}

                for field_id, allowed in self.enums.items():
                    result_key = self._item_result_keys.get(field_id, field_id)
                    default_value = self.defaults.get(field_id)
                    raw_value = raw_item.get(result_key, None)

                    normalized = normalize_one(
                        field_id=field_id,
                        raw_value=raw_value,
                        allowed=allowed,
                        default_value=default_value,
                    )
                    item_result[field_id] = normalized

                normalized_items.append(item_result)

            result[root_key] = normalized_items
            return result

        if self.mode == "synthesizer":
            result: Dict[str, Any] = {}

            root_key = self.output_schema.get("root_key", "")
            item_id_key = self.output_schema.get("item_id_key", "")

            if root_key and self._item_result_keys:
                raw_items = json_obj.get(root_key, []) or []
                if not isinstance(raw_items, list):
                    raw_items = []

                normalized_items: List[Dict[str, Any]] = []
                for raw_item in raw_items:
                    if not isinstance(raw_item, dict):
                        continue

                    item_result: Dict[str, Any] = {}
                    if item_id_key:
                        raw_item_id = raw_item.get(item_id_key)
                        if raw_item_id is None:
                            continue
                        item_result[item_id_key] = str(raw_item_id).strip()

                    for field_id, result_key in self._item_result_keys.items():
                        raw_value = raw_item.get(result_key, "")
                        if raw_value is None:
                            item_result[field_id] = ""
                        elif isinstance(raw_value, str):
                            item_result[field_id] = raw_value.strip()
                        else:
                            item_result[field_id] = str(raw_value).strip()

                    normalized_items.append(item_result)

                result[root_key] = normalized_items
                return result

            for field_id, result_key in self._top_level_result_keys.items():
                raw_value = json_obj.get(result_key, "")
                if raw_value is None:
                    result[field_id] = ""
                elif isinstance(raw_value, str):
                    result[field_id] = raw_value.strip()
                else:
                    result[field_id] = str(raw_value).strip()

            return result

        raise AgentPromptValidationError(
            f"AgentPrompt[{self.agent_name}] parse() currently only supports "
            f"mode='selector', mode='classifier', or mode='synthesizer'"
        )
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
- Keeps backward compatibility for old callers:
    * default return = raw content string
- Supports optional metadata return for cache/token inspection:
    * return_metadata=True -> {"content": "...", "usage": {...}}

Added:
- Responses API path for A4 / reasoning-model calls.
- Metadata extraction for:
    * model name
    * status
    * incomplete reason
    * input tokens
    * cached input tokens
    * output tokens
    * reasoning tokens

CLI logging:
- Always logs model name, total input tokens, cached input tokens, and output tokens
  for both chat() and responses().
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
import os

from ragstream.utils.logging import SimpleLogger

try:
    from openai import OpenAI  # type: ignore[import]
except ImportError:  # pragma: no cover - import guard
    OpenAI = None  # type: ignore[assignment]

JsonDict = Dict[str, Any]


class LLMClient:
    """
    Neutral LLM gateway.

    Default behavior stays backward compatible:
    - chat() returns raw content string

    Optional metadata:
    - chat(..., return_metadata=True)
    - responses(..., return_metadata=True)
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
            self._client = OpenAI(api_key=key)
            SimpleLogger.info("LLMClient: OpenAI client initialised (v1 API).")
        except Exception as exc:
            SimpleLogger.error(f"LLMClient: failed to initialise OpenAI client: {exc!r}")
            self._client = None

    def chat(
        self,
        *,
        messages: List[Dict[str, str]],
        model_name: str,
        temperature: float,
        max_output_tokens: int,
        response_format: Dict[str, Any] | None = None,
        return_metadata: bool = False,
        prompt_cache_key: Optional[str] = None,
        prompt_cache_retention: Optional[str] = None,
    ) -> Union[str, JsonDict]:
        """
        Thin wrapper over OpenAI chat.completions.

        Notes:
        - Uses max_completion_tokens (new API) instead of max_tokens.
        - For gpt-5* reasoning models, temperature is omitted.
        - Prompt caching for recent models is automatic on the provider side.
        """
        if self._client is None:
            raise RuntimeError("LLMClient: OpenAI client is not initialised")

        kwargs: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "max_completion_tokens": int(max_output_tokens),
        }

        if response_format is not None:
            kwargs["response_format"] = response_format

        if temperature is not None and not str(model_name).startswith("gpt-5"):
            kwargs["temperature"] = float(temperature)

        if prompt_cache_key:
            kwargs["prompt_cache_key"] = prompt_cache_key  # Added: stable cache-routing key per prompt family.

      # if prompt_cache_retention:
           # kwargs["prompt_cache_retention"] = prompt_cache_retention  # Added: explicit retention policy for prompt cache.

        resp = self._client.chat.completions.create(**kwargs)

        content = resp.choices[0].message.content
        content_text = content if isinstance(content, str) else str(content or "")

        usage = self._extract_chat_usage(resp)
        actual_model_name = str(getattr(resp, "model", "") or model_name)
        self._log_chat_usage(actual_model_name, usage)

        if not return_metadata:
            return content_text

        return {
            "content": content_text,
            "usage": usage,
            "model_name": actual_model_name,
            "status": "",
            "incomplete_reason": "",
        }

    def responses(
        self,
        *,
        messages: List[Dict[str, str]],
        model_name: str,
        max_output_tokens: int,
        reasoning_effort: Optional[str] = None,
        return_metadata: bool = False,
        prompt_cache_key: Optional[str] = None,
        prompt_cache_retention: Optional[str] = None,
    ) -> Union[str, JsonDict]:
        """
        Responses API path used for A4 / reasoning-style calls.

        Design:
        - First SYSTEM message becomes `instructions`.
        - Remaining messages are collapsed into one text input string.
        - reasoning_effort is explicitly controlled here.

        Important fix:
        - If the composed prompt has no non-system message, Responses API still
          requires `input`.
        - In that case we move the instructions text into `input` and clear
          `instructions`.
        """
        if self._client is None:
            raise RuntimeError("LLMClient: OpenAI client is not initialised")

        instructions = ""
        input_parts: List[str] = []

        for message in messages:
            role = str(message.get("role", "") or "").strip().lower()
            content = str(message.get("content", "") or "")

            if role == "system" and not instructions:
                instructions = content
            else:
                if content:
                    input_parts.append(content)

        input_text = "\n\n".join(part for part in input_parts if part).strip()

        # Fix for "missing_required_parameter":
        # if everything is inside the system message, move it into input.
        if not input_text and instructions:
            input_text = instructions
            instructions = ""

        kwargs: Dict[str, Any] = {
            "model": model_name,
            "input": input_text,
            "max_output_tokens": int(max_output_tokens),
        }

        if reasoning_effort is not None:
            kwargs["reasoning"] = {"effort": reasoning_effort}

        if instructions:
            kwargs["instructions"] = instructions

        if prompt_cache_key:
            kwargs["prompt_cache_key"] = prompt_cache_key  # Added: stable cache-routing key per prompt family.

       # if prompt_cache_retention:
         #   kwargs["prompt_cache_retention"] = prompt_cache_retention  # Added: explicit retention policy for prompt cache.

        resp = self._client.responses.create(**kwargs)

        content_text = self._extract_response_text(resp)
        usage = self._extract_response_usage(resp)
        status = self._extract_response_status(resp)
        incomplete_reason = self._extract_response_incomplete_reason(resp)
        actual_model_name = str(getattr(resp, "model", "") or model_name)

        self._log_response_usage(
            actual_model_name=actual_model_name,
            usage=usage,
            status=status,
            incomplete_reason=incomplete_reason,
        )

        if not return_metadata:
            return content_text

        return {
            "content": content_text,
            "usage": usage,
            "model_name": actual_model_name,
            "status": status,
            "incomplete_reason": incomplete_reason,
        }

    @staticmethod
    def _extract_chat_usage(resp: Any) -> JsonDict:
        """
        Extract token usage including cached tokens when the provider returns it.
        """
        usage_obj = getattr(resp, "usage", None)
        if usage_obj is None:
            return {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cached_tokens": 0,
            }

        prompt_tokens = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage_obj, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage_obj, "total_tokens", 0) or 0)

        prompt_tokens_details = getattr(usage_obj, "prompt_tokens_details", None)
        cached_tokens = 0
        if prompt_tokens_details is not None:
            cached_tokens = int(getattr(prompt_tokens_details, "cached_tokens", 0) or 0)

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cached_tokens": cached_tokens,
        }

    @staticmethod
    def _extract_response_text(resp: Any) -> str:
        """
        Extract visible text from a Responses API object.
        """
        output_text = getattr(resp, "output_text", None)
        if isinstance(output_text, str) and output_text:
            return output_text

        output = getattr(resp, "output", None)
        if not isinstance(output, list):
            return ""

        parts: List[str] = []

        for item in output:
            item_type = str(getattr(item, "type", "") or "")
            if item_type != "message":
                continue

            content_list = getattr(item, "content", None)
            if not isinstance(content_list, list):
                continue

            for content_item in content_list:
                content_type = str(getattr(content_item, "type", "") or "")
                if content_type in ("output_text", "text"):
                    text = getattr(content_item, "text", None)
                    if isinstance(text, str) and text:
                        parts.append(text)

        return "\n".join(parts).strip()

    @staticmethod
    def _extract_response_usage(resp: Any) -> JsonDict:
        """
        Extract token usage from a Responses API object.
        """
        usage_obj = getattr(resp, "usage", None)
        if usage_obj is None:
            return {
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": 0,
            }

        input_tokens = int(getattr(usage_obj, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage_obj, "output_tokens", 0) or 0)
        total_tokens = int(getattr(usage_obj, "total_tokens", 0) or 0)

        input_tokens_details = getattr(usage_obj, "input_tokens_details", None)
        cached_input_tokens = 0
        if input_tokens_details is not None:
            cached_input_tokens = int(getattr(input_tokens_details, "cached_tokens", 0) or 0)

        output_tokens_details = getattr(usage_obj, "output_tokens_details", None)
        reasoning_tokens = 0
        if output_tokens_details is not None:
            reasoning_tokens = int(getattr(output_tokens_details, "reasoning_tokens", 0) or 0)

        return {
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "total_tokens": total_tokens,
        }

    @staticmethod
    def _extract_response_status(resp: Any) -> str:
        return str(getattr(resp, "status", "") or "")

    @staticmethod
    def _extract_response_incomplete_reason(resp: Any) -> str:
        incomplete_details = getattr(resp, "incomplete_details", None)
        if incomplete_details is None:
            return ""
        return str(getattr(incomplete_details, "reason", "") or "")

    @staticmethod
    def _log_chat_usage(actual_model_name: str, usage: JsonDict) -> None:
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        cached_tokens = int(usage.get("cached_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)

        SimpleLogger.info(
            f"LLMClient.chat | model={actual_model_name} | "
            f"input={prompt_tokens} | cached_input={cached_tokens} | output={completion_tokens}"
        )

    @staticmethod
    def _log_response_usage(
        *,
        actual_model_name: str,
        usage: JsonDict,
        status: str,
        incomplete_reason: str,
    ) -> None:
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        cached_input_tokens = int(usage.get("cached_input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)

        SimpleLogger.info(
            f"LLMClient.responses | model={actual_model_name} | "
            f"input={input_tokens} | cached_input={cached_input_tokens} | output={output_tokens}"
        )

        if status:
            SimpleLogger.info(f"LLMClient.responses | status={status}")

        if incomplete_reason:
            SimpleLogger.warning(f"LLMClient.responses | incomplete_reason={incomplete_reason}")
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
# super_prompt.py
# -*- coding: utf-8 -*-
"""
SuperPrompt (v1) — central prompt object (manual __init__, no dataclass).
Place at: ragstream/orchestration/super_prompt.py

Notes (agreed pipeline choices; for reference only):
- Retrieval aggregation: LogAvgExp (length-normalized LogSumExp) with τ = 9 over per-piece cosine sims.
- Re-ranker: cross-encoder/ms-marco-MiniLM-L-6-v2 on (Prompt_MD, chunk_text).

Stage refactor note:
- SuperPrompt remains the authoritative shared state object.
- Projection / render / text-extraction support logic has been moved to
  superprompt_projector.py.
- compose_prompt_ready() remains here as the stable public wrapper so that
  external call sites do not need to change.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from ragstream.orchestration.superprompt_projector import SuperPromptProjector

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
        Stable public wrapper for the central SuperPrompt render path.

        Important compatibility rule:
        - External code may continue to call sp.compose_prompt_ready() exactly
          as before.
        - The real render / projection logic lives in SuperPromptProjector.
        """
        return SuperPromptProjector(self).compose_prompt_ready()

    def __repr__(self) -> str:
        return f"SuperPrompt(stage={self.stage!r})"
```

### ~\ragstream\orchestration\superprompt_projector.py
```python
# superprompt_projector.py
# -*- coding: utf-8 -*-
"""
superprompt_projector.py

Purpose:
    Companion projection / render / text-extraction support for SuperPrompt.

Design:
    - SuperPrompt remains the authoritative shared state object.
    - This module owns derived render logic and text-oriented support logic.
    - compose_prompt_ready() remains publicly callable through the wrapper
      method on SuperPrompt for compatibility.
    - build_query_text(sp) also lives here, because it is a projection of
      SuperPrompt state into a retrieval-oriented text representation.
"""

from __future__ import annotations

from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ragstream.orchestration.super_prompt import SuperPrompt


class SuperPromptProjector:
    """
    Projection / render helper around one SuperPrompt instance.
    """

    def __init__(self, sp: "SuperPrompt") -> None:
        if sp is None:
            raise ValueError("SuperPromptProjector.__init__: 'sp' must not be None")
        self.sp = sp

    @staticmethod
    def build_query_text(sp: "SuperPrompt") -> str:
        if sp is None:
            raise ValueError("SuperPromptProjector.build_query_text: 'sp' must not be None")

        if not hasattr(sp, "body") or sp.body is None:
            raise ValueError("SuperPromptProjector.build_query_text: SuperPrompt has no usable 'body'")

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

        query_text = "\n".join(blocks).strip()

        if not query_text:
            raise ValueError(
                "SuperPromptProjector.build_query_text: retrieval query is empty. "
                "At least one of TASK / PURPOSE / CONTEXT must be present."
            )

        return query_text

    def compose_prompt_ready(self) -> str:
        self.sp.System_MD = self._render_system_md()
        self.sp.Prompt_MD = self._render_prompt_md()

        parts: List[str] = []

        if self.sp.System_MD:
            parts.append(self.sp.System_MD)

        if self.sp.Prompt_MD:
            parts.append(self.sp.Prompt_MD)

        retrieved_context_md = self._render_retrieved_context_md()
        if retrieved_context_md:
            parts.append(retrieved_context_md)

        if self.sp.Attachments_MD:
            parts.append(self.sp.Attachments_MD)

        self.sp.prompt_ready = "\n\n".join(parts).strip()
        return self.sp.prompt_ready

    def _render_system_md(self) -> str:
        lines: List[str] = []

        system_value = (self.sp.body.get("system") or "").strip()
        role_value = (self.sp.body.get("role") or "").strip()
        audience_value = (self.sp.body.get("audience") or "").strip()
        tone_value = (self.sp.body.get("tone") or "").strip()
        depth_value = (self.sp.body.get("depth") or "").strip()
        confidence_value = (self.sp.body.get("confidence") or "").strip()

        lines.append("## System")
        if system_value:
            lines.append(system_value)
        else:
            lines.append("")

        config_lines: List[str] = []

        if role_value:
            config_lines.append(f"- Role: {role_value}")
        if audience_value:
            config_lines.append(f"- Audience: {audience_value}")
        if tone_value:
            config_lines.append(f"- Tone: {tone_value}")
        if depth_value:
            config_lines.append(f"- Depth: {depth_value}")
        if confidence_value:
            config_lines.append(f"- Confidence: {confidence_value}")

        lines.append("")
        lines.append("## Configuration")
        lines.extend(config_lines)

        return "\n".join(lines).strip()

    def _render_prompt_md(self) -> str:
        lines: List[str] = []

        task_value = (self.sp.body.get("task") or "").strip()
        purpose_value = (self.sp.body.get("purpose") or "").strip()
        context_value = (self.sp.body.get("context") or "").strip()
        format_value = (self.sp.body.get("format") or "").strip()
        text_value = (self.sp.body.get("text") or "").strip()

        lines.append("## User")
        lines.append("")

        lines.append("### Task")
        lines.append(task_value)
        lines.append("")

        if purpose_value:
            lines.append("### Purpose")
            lines.append(purpose_value)
            lines.append("")

        if context_value:
            lines.append("### Context")
            lines.append(context_value)
            lines.append("")

        if format_value:
            lines.append("### Format")
            lines.append(format_value)
            lines.append("")

        if text_value:
            lines.append("### Text")
            lines.append(text_value)
            lines.append("")

        return "\n".join(lines).strip()

    def _render_retrieved_context_md(self) -> str:
        """
        Render retrieved/condensed context for GUI-visible SuperPrompt preview.

        This is intentionally neutral and reusable:
        - A4 only produces S_CTX_MD.
        - This projector decides how S_CTX_MD is displayed.
        - Later PromptBuilder can reuse the same structure.
        """
        lines: List[str] = []

        lines.append("## Retrieved Context")
        lines.append("")

        lines.append("### Retrieved Context Summary")
        lines.append(
            "The following summary is retrieved from selected project files or memory. "
            "It is supporting context for the task, not part of the task itself."
        )
        lines.append("")

        summary_text = (self.sp.S_CTX_MD or "").strip()
        if summary_text:
            lines.append(summary_text)
        lines.append("")

        lines.append("### Raw Retrieved Evidence")
        raw_evidence_md = self._render_raw_retrieved_evidence_md()
        if raw_evidence_md:
            lines.append(raw_evidence_md)

        return "\n".join(lines).strip()

    def _render_raw_retrieved_evidence_md(self) -> str:
        """
        Render raw retrieved chunks as nested evidence.

        Important:
        Source Markdown headings inside chunks are converted to [H1]/[H2]/[H3]
        so they do not compete with the visible SuperPrompt structure.
        """
        ordered_chunks = self._get_ordered_context_chunks()
        if not ordered_chunks:
            return ""

        retrieval_score_map: Dict[str, float] = {
            chunk_id: float(score)
            for chunk_id, score, _status in self.sp.views_by_stage.get("retrieval", [])
        }

        reranked_score_map: Dict[str, float] = {
            chunk_id: float(score)
            for chunk_id, score, _status in self.sp.views_by_stage.get("reranked", [])
        }

        a3_decision_map: Dict[str, Dict[str, Any]] = {}
        raw_a3_decisions = self.sp.extras.get("a3_item_decisions", {})
        if isinstance(raw_a3_decisions, dict):
            a3_decision_map = raw_a3_decisions

        selection_band = str(self.sp.extras.get("a3_selection_band", "") or "").strip()

        lines: List[str] = []
        lines.append("<retrieved_chunks>")

        if self.sp.stage == "a3" and selection_band:
            lines.append(f'  <selection_band>{selection_band}</selection_band>')

        chunk_counter = 1
        for chunk_obj in ordered_chunks:
            attributes: List[str] = [
                f'index="{chunk_counter}"',
                f'chunk_id="{self._escape_attr(str(chunk_obj.id))}"',
            ]

            source_value = ""
            meta = getattr(chunk_obj, "meta", None)
            if isinstance(meta, dict):
                source_value = str(meta.get("source") or meta.get("path") or meta.get("file") or "").strip()
            if source_value:
                attributes.append(f'source="{self._escape_attr(source_value)}"')

            score_label = self._build_chunk_score_label(
                chunk_obj=chunk_obj,
                retrieval_score_map=retrieval_score_map,
                reranked_score_map=reranked_score_map,
                a3_decision_map=a3_decision_map,
            )
            if score_label:
                attributes.append(f'info="{self._escape_attr(score_label)}"')

            lines.append(f"  <chunk {' '.join(attributes)}>")
            lines.append("    <chunk_text>")

            snippet = self._sanitize_chunk_text(chunk_obj.snippet.strip())
            if snippet:
                for snippet_line in snippet.splitlines():
                    lines.append(f"      {snippet_line}")

            lines.append("    </chunk_text>")
            lines.append("  </chunk>")
            chunk_counter += 1

        lines.append("</retrieved_chunks>")

        return "\n".join(lines).strip()

    def _build_chunk_score_label(
        self,
        *,
        chunk_obj: Any,
        retrieval_score_map: Dict[str, float],
        reranked_score_map: Dict[str, float],
        a3_decision_map: Dict[str, Dict[str, Any]],
    ) -> str:
        score_parts: List[str] = []

        emb_score = self._get_meta_float(chunk_obj.meta, "emb_score")
        splade_score = self._get_meta_float(chunk_obj.meta, "splade_score")

        if self.sp.stage == "retrieval":
            rt_score = retrieval_score_map.get(chunk_obj.id)
            if rt_score is not None:
                score_parts.append(f"Rt={self._format_score(rt_score)}")
            if emb_score is not None:
                score_parts.append(f"Emb={self._format_score(emb_score)}")
            if splade_score is not None:
                score_parts.append(f"Splade={self._format_score(splade_score)}")

        elif self.sp.stage == "reranked":
            rnk_score = reranked_score_map.get(chunk_obj.id)
            if rnk_score is None:
                rnk_score = self._get_meta_float(chunk_obj.meta, "rerank_rrf_score")

            rcolb_score = self._get_meta_float(chunk_obj.meta, "colbert_score")

            rt_score = self._get_meta_float(chunk_obj.meta, "retrieval_rrf_score")
            if rt_score is None:
                rt_score = self._get_meta_float(chunk_obj.meta, "retrieval_score")
            if rt_score is None:
                rt_score = retrieval_score_map.get(chunk_obj.id)

            if rnk_score is not None:
                score_parts.append(f"Rnk={self._format_score(rnk_score)}")
            if rcolb_score is not None:
                score_parts.append(f"RcolB={self._format_score(rcolb_score)}")
            if rt_score is not None:
                score_parts.append(f"Rt={self._format_score(rt_score)}")

        elif self.sp.stage == "a3":
            decision = a3_decision_map.get(chunk_obj.id, {})
            usefulness = str(decision.get("usefulness_label", "") or "").strip()
            if usefulness:
                score_parts.append(f"Use={usefulness}")

        return ", ".join(score_parts).strip()

    @staticmethod
    def _sanitize_chunk_text(text: str) -> str:
        """
        Prevent source Markdown headings from becoming real prompt headings.
        """
        if not text:
            return ""

        sanitized_lines: List[str] = []

        for line in text.splitlines():
            stripped = line.lstrip()
            indent = line[: len(line) - len(stripped)]

            if stripped.startswith("### "):
                sanitized_lines.append(f"{indent}[H3] {stripped[4:].strip()}")
            elif stripped.startswith("## "):
                sanitized_lines.append(f"{indent}[H2] {stripped[3:].strip()}")
            elif stripped.startswith("# "):
                sanitized_lines.append(f"{indent}[H1] {stripped[2:].strip()}")
            else:
                sanitized_lines.append(line)

        return "\n".join(sanitized_lines).strip()

    @staticmethod
    def _escape_attr(value: str) -> str:
        return (
            str(value or "")
            .replace("&", "&amp;")
            .replace('"', "&quot;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def _format_score(self, score: float) -> str:
        return f"{float(score):.8f}".rstrip("0").rstrip(".")

    def _render_related_context_md(self) -> str:
        """
        Backward-compatible wrapper.

        Older callers may still refer to _render_related_context_md().
        The visible GUI format now uses Raw Retrieved Evidence instead of
        the older Related Context block.
        """
        return self._render_raw_retrieved_evidence_md()

    @staticmethod
    def _get_meta_float(meta: Dict[str, Any] | None, key: str) -> float | None:
        if not isinstance(meta, dict):
            return None
        value = meta.get(key)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _get_ordered_context_chunks(self) -> List["Chunk"]:
        if not self.sp.base_context_chunks:
            return []

        chunk_by_id: Dict[str, "Chunk"] = {}
        for chunk_obj in self.sp.base_context_chunks:
            chunk_by_id[chunk_obj.id] = chunk_obj

        ordered_chunks: List["Chunk"] = []

        if self.sp.stage == "a3" and "a3" in self.sp.views_by_stage:
            stage_rows = self.sp.views_by_stage["a3"]
            for row in stage_rows:
                chunk_id = row[0]
                if chunk_id in chunk_by_id:
                    ordered_chunks.append(chunk_by_id[chunk_id])
            return ordered_chunks

        if self.sp.final_selection_ids:
            for chunk_id in self.sp.final_selection_ids:
                if chunk_id in chunk_by_id:
                    ordered_chunks.append(chunk_by_id[chunk_id])
            return ordered_chunks

        if self.sp.stage in self.sp.views_by_stage:
            stage_rows = self.sp.views_by_stage[self.sp.stage]
            for row in stage_rows:
                chunk_id = row[0]
                if chunk_id in chunk_by_id:
                    ordered_chunks.append(chunk_by_id[chunk_id])
            return ordered_chunks

        for chunk_obj in self.sp.base_context_chunks:
            ordered_chunks.append(chunk_obj)

        return ordered_chunks
```

### ~\ragstream\orchestration\agent_prompt_helpers\compose_texts.py
```python
# ragstream/orchestration/agent_prompt_helpers/compose_texts.py
# -*- coding: utf-8 -*-
"""
compose_texts
=============

Neutral text render helpers for AgentPrompt.

Rule:
- No agent-specific visible wording is invented here.
- Visible prompt wording must come from JSON or from agent-prepared runtime text.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple


def _stringify_for_prompt(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)

    return str(value)


def _build_decision_targets_system_text(
    decision_targets: List[Dict[str, Any]],
    result_keys: Dict[str, str],
    enums: Dict[str, List[str]],
    option_labels: Dict[str, Dict[str, str]],
    option_descriptions: Dict[str, Dict[str, str]],
    active_fields: Optional[List[str]] = None,
) -> str:
    lines: List[str] = []

    if active_fields is None:
        active_set = None
    else:
        active_set = set(active_fields)

    for target in decision_targets or []:
        field_id = target.get("id")
        if not field_id:
            continue
        if active_set is not None and field_id not in active_set:
            continue

        label = target.get("label", field_id)
        result_key = result_keys.get(field_id, field_id)

        min_selected = int(target.get("min_selected", 1))
        max_selected = int(target.get("max_selected", 1))

        lines.append(f"Field '{label}' (JSON key: '{result_key}')")

        if max_selected > 1:
            lines.append(f"- Select between {min_selected} and {max_selected} option ids.")
        else:
            lines.append("- Select exactly one option id.")

        for opt_id in enums.get(field_id, []):
            opt_label = (option_labels.get(field_id, {}).get(opt_id) or "").strip()
            opt_desc = (option_descriptions.get(field_id, {}).get(opt_id) or "").strip()

            if opt_label and opt_desc:
                lines.append(f"  * {opt_id}: {opt_label} — {opt_desc}")
            elif opt_label:
                lines.append(f"  * {opt_id}: {opt_label}")
            elif opt_desc:
                lines.append(f"  * {opt_id}: {opt_desc}")
            else:
                lines.append(f"  * {opt_id}")

        lines.append("")

    return "\n".join(lines).strip()


def build_system_text(
    static_prompt: Dict[str, Any],
    agent_name: str,
    version: str,
    decision_targets: Optional[List[Dict[str, Any]]] = None,
    result_keys: Optional[Dict[str, str]] = None,
    enums: Optional[Dict[str, List[str]]] = None,
    option_labels: Optional[Dict[str, Dict[str, str]]] = None,
    option_descriptions: Optional[Dict[str, Dict[str, str]]] = None,
    active_fields: Optional[List[str]] = None,
    input_payload: Optional[Dict[str, Any]] = None,
    dynamic_bindings: Optional[List[Dict[str, Any]]] = None,
    elements_order: Optional[List[str]] = None,
) -> Tuple[str, Set[str]]:
    """
    Build the SYSTEM message content for the LLM.

    Important A4-compatible rule:
    - preamble is always first if present,
    - elements_order may then inject selected dynamic bindings directly into SYSTEM,
    - any dynamic binding moved into SYSTEM is removed from USER,
    - old behavior remains when elements_order is absent.
    """
    input_payload = input_payload or {}
    dynamic_bindings = dynamic_bindings or []
    elements_order = elements_order or []

    lines: List[str] = []
    consumed_binding_ids: Set[str] = set()

    preamble_text = _stringify_for_prompt(static_prompt.get("preamble", ""))
    if preamble_text:
        lines.append(preamble_text)
        lines.append("")

    remaining_static_keys = [key for key in static_prompt.keys() if str(key).strip().lower() != "preamble"]
    binding_by_id: Dict[str, Dict[str, Any]] = {
        str(binding.get("id", "")).strip(): binding
        for binding in dynamic_bindings
        if str(binding.get("id", "")).strip()
    }

    decision_targets_text = _build_decision_targets_system_text(
        decision_targets=decision_targets or [],
        result_keys=result_keys or {},
        enums=enums or {},
        option_labels=option_labels or {},
        option_descriptions=option_descriptions or {},
        active_fields=active_fields,
    )

    rendered_static_keys: Set[str] = set()
    rendered_config_decision_targets = False

    # New optional ordered render path.
    for raw_item in elements_order:
        item = str(raw_item or "").strip()
        if not item:
            continue

        normalized_item = item[3:] if item.lower().startswith("id:") else item

        if normalized_item in binding_by_id:
            binding = binding_by_id[normalized_item]
            if binding.get("visible_in_prompt", True):
                prompt_text = (binding.get("prompt_text") or "").strip()
                if prompt_text:
                    lines.append(prompt_text)

                rendered = _stringify_for_prompt(input_payload.get(normalized_item, ""))
                if rendered:
                    lines.append(rendered)

                lines.append("")
            consumed_binding_ids.add(normalized_item)
            continue

        if normalized_item == "decision_targets":
            runtime_rendered = _stringify_for_prompt(input_payload.get("decision_targets", ""))
            if runtime_rendered:
                lines.append("## Decision Targets")
                lines.append(runtime_rendered)
                lines.append("")
                consumed_binding_ids.add("decision_targets")
            elif decision_targets_text and not rendered_config_decision_targets:
                lines.append("## Decision Targets")
                lines.append(decision_targets_text)
                lines.append("")
                rendered_config_decision_targets = True
            continue

        for static_key in remaining_static_keys:
            if static_key == normalized_item and static_key not in rendered_static_keys:
                text = _stringify_for_prompt(static_prompt.get(static_key, ""))
                if text:
                    lines.append(f"## {static_key}")
                    lines.append(text)
                    lines.append("")
                rendered_static_keys.add(static_key)
                break

    # Backward-compatible default remainder for static prompt keys.
    for static_key in remaining_static_keys:
        if static_key in rendered_static_keys:
            continue
        text = _stringify_for_prompt(static_prompt.get(static_key, ""))
        if not text:
            continue
        lines.append(f"## {static_key}")
        lines.append(text)
        lines.append("")

    # Backward-compatible default remainder for config-owned decision targets.
    if decision_targets_text and not rendered_config_decision_targets:
        lines.append("## Decision Targets")
        lines.append(decision_targets_text)
        lines.append("")

    return "\n".join(lines).strip(), consumed_binding_ids


def _build_user_text_from_dynamic_bindings(
    input_payload: Dict[str, Any],
    dynamic_bindings: List[Dict[str, Any]],
    consumed_binding_ids: Optional[Set[str]] = None,
) -> str:
    lines: List[str] = []
    consumed_binding_ids = consumed_binding_ids or set()

    for binding in dynamic_bindings:
        if not binding.get("visible_in_prompt", True):
            continue

        binding_id = str(binding.get("id", "") or "").strip()
        if not binding_id:
            continue
        if binding_id in consumed_binding_ids:
            continue

        prompt_text = (binding.get("prompt_text") or "").strip()
        value = input_payload.get(binding_id, "")

        if prompt_text:
            lines.append(prompt_text)

        rendered = _stringify_for_prompt(value)
        if rendered:
            lines.append(rendered)

        lines.append("")

    return "\n".join(lines).strip()


def build_user_text_for_selector(
    input_payload: Dict[str, Any],
    dynamic_bindings: List[Dict[str, Any]],
    consumed_binding_ids: Optional[Set[str]] = None,
) -> str:
    return _build_user_text_from_dynamic_bindings(
        input_payload=input_payload,
        dynamic_bindings=dynamic_bindings,
        consumed_binding_ids=consumed_binding_ids,
    )


def build_user_text_for_classifier(
    input_payload: Dict[str, Any],
    dynamic_bindings: List[Dict[str, Any]],
    consumed_binding_ids: Optional[Set[str]] = None,
) -> str:
    return _build_user_text_from_dynamic_bindings(
        input_payload=input_payload,
        dynamic_bindings=dynamic_bindings,
        consumed_binding_ids=consumed_binding_ids,
    )


def build_user_text_for_synthesizer(
    input_payload: Dict[str, Any],
    dynamic_bindings: List[Dict[str, Any]],
    consumed_binding_ids: Optional[Set[str]] = None,
) -> str:
    return _build_user_text_from_dynamic_bindings(
        input_payload=input_payload,
        dynamic_bindings=dynamic_bindings,
        consumed_binding_ids=consumed_binding_ids,
    )
```

### ~\ragstream\orchestration\agent_prompt_helpers\config_loader.py
```python
# -*- coding: utf-8 -*-
"""
config_loader
=============

Why this helper exists:
- Agent JSON configs define decision targets with enums, defaults and selection counts.
- Converting these targets into clean Python dictionaries is generic logic and should
  not clutter AgentPrompt.

What it does:
- Provides a single function `extract_field_config(fields_cfg)` that returns:
  - enums[field_id] = list of allowed option ids
  - defaults[field_id] = default value from config (may be str or list)
  - cardinality[field_id] = "one" or "many"
  - option_labels[field_id][opt_id] = human-readable label (optional)
  - option_descriptions[field_id][opt_id] = human-readable description (optional)

Compatibility:
- Works with the new `decision_targets` structure.
- Also tolerates older inline `fields` configs, as long as they use the same
  basic keys (`id`, `type`, `options`, `default`, `cardinality`).
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
    Convert decision targets / fields into:
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
            # For v1 implementation, AgentPrompt only supports enum-based Selector behaviour.
            continue

        options = field.get("options", []) or []
        if not isinstance(options, list):
            options = []

        allowed_ids: List[str] = []
        descs: Dict[str, str] = {}
        labels: Dict[str, str] = {}

        for opt in options:
            if not isinstance(opt, dict):
                continue

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

        if "cardinality" in field:
            cardinality[field_id] = field.get("cardinality", "one")
        else:
            try:
                max_selected = int(field.get("max_selected", 1))
            except Exception:
                max_selected = 1
            cardinality[field_id] = "many" if max_selected > 1 else "one"

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
    - Build reranking query pieces from TASK / PURPOSE / CONTEXT.
    - Clean chunk text dynamically before ColBERT scoring.
    - Score each Retrieval candidate with ColBERT over the split query pieces.
    - Fuse Retrieval ranking and ColBERT ranking with deterministic weighted RRF.
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
from typing import Any, Dict, List, Tuple

from pylate import models, rank

from ragstream.ingestion.chunker import Chunker
from ragstream.orchestration.super_prompt import A3ChunkStatus, SuperPrompt
from ragstream.orchestration.superprompt_projector import SuperPromptProjector
from ragstream.retrieval.chunk import Chunk
from ragstream.retrieval.rrf_merger import rrf_merge
from ragstream.retrieval.smart_query_splitter import split_query_into_pieces


# ---------------------------------------------------------------------
# Shared row contract
# ---------------------------------------------------------------------

RankedRow = Tuple[str, float, Dict[str, Any]]

# ---------------------------------------------------------------------
# Module-level reranker defaults
# ---------------------------------------------------------------------

# Agreed current reranker model direction.
DEFAULT_RERANK_MODEL = "lightonai/GTE-ModernColBERT-v1"

# Conceptual cap from the current requirement set for how many Retrieval
# candidates should be passed into ReRanker.
DEFAULT_RERANK_TOP_K = 50

# Agreed current runtime direction: CPU-only deterministic stage.
DEFAULT_DEVICE = "cpu"

# Keep query splitting aligned with Retrieval.
DEFAULT_QUERY_CHUNK_SIZE = 1200
DEFAULT_QUERY_OVERLAP = 120

# Equal-weight fusion between Retrieval and ColBERT.
DEFAULT_RETRIEVAL_WEIGHT = 0.75
DEFAULT_COLBERT_WEIGHT = 0.25


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
        Initialize ReRanker with the agreed ColBERT model.

        Args:
            model_name:
                Hugging Face / PyLate-compatible model id for the reranker.
            top_k:
                Maximum number of Retrieval candidates to rerank.
            device:
                Runtime device. Current agreed direction is CPU.
                Kept as part of the stable ReRanker interface.
        """
        self._model_name = model_name
        self._top_k = int(top_k) if int(top_k) > 0 else DEFAULT_RERANK_TOP_K
        self._device = device
        self._chunker = Chunker()
        self._colbert_model = models.ColBERT(model_name_or_path=self._model_name)

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def run(
        self,
        sp: SuperPrompt,
        *,
        use_reranking_colbert: bool = True,
    ) -> SuperPrompt:
        """
        Execute the ReRanker stage and update the same SuperPrompt in place.

        Inputs:
            sp:
                The current evolving SuperPrompt, typically after Retrieval.
            use_reranking_colbert:
                If False, bypass real ColBERT scoring and copy the Retrieval
                order directly into the reranked stage.

        Returns:
            The same SuperPrompt instance, mutated in place.

        Effects on SuperPrompt:
            - Writes the reranked stage snapshot into sp.views_by_stage["reranked"]
            - Writes reranked chunk IDs into sp.final_selection_ids
            - Appends "reranked" to sp.history_of_stages
            - Sets sp.stage = "reranked"
        """
        if not use_reranking_colbert:
            reranked_view, reranked_ids = self._build_passthrough_from_retrieval(sp)
            sp.views_by_stage["reranked"] = reranked_view
            sp.final_selection_ids = reranked_ids
            sp.stage = "reranked"
            sp.history_of_stages.append("reranked")
            return sp

        query_pieces, retrieval_rows, chunk_lookup = self._prepare_inputs(sp)
        colbert_rows = self._score_with_colbert(query_pieces, retrieval_rows, chunk_lookup)
        fused_rows = self._fuse_with_retrieval(retrieval_rows, colbert_rows, chunk_lookup)
        fused_rows = self._project_fused_metadata_to_reranker_contract(fused_rows)
        self._write_scores_back_to_chunks(fused_rows, chunk_lookup)
        reranked_view, reranked_ids = self._build_reranked_view(fused_rows)

        sp.views_by_stage["reranked"] = reranked_view
        sp.final_selection_ids = reranked_ids
        sp.stage = "reranked"
        sp.history_of_stages.append("reranked")

        return sp

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _build_passthrough_from_retrieval(
        self,
        sp: SuperPrompt,
    ) -> tuple[List[tuple[str, float, A3ChunkStatus]], List[str]]:
        """
        Bypass real ColBERT and copy the Retrieval order directly into the
        reranked stage so downstream A3 can run unchanged.
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

        candidate_rows = list(retrieval_rows)[: self._top_k]
        chunk_lookup = {chunk_obj.id: chunk_obj for chunk_obj in sp.base_context_chunks}

        reranked_view: List[tuple[str, float, A3ChunkStatus]] = []
        reranked_ids: List[str] = []

        for position, (chunk_id, retrieval_score, _status) in enumerate(candidate_rows, start=1):
            chunk_id_str = str(chunk_id)
            score = float(retrieval_score)

            reranked_view.append((chunk_id_str, score, A3ChunkStatus.SELECTED))
            reranked_ids.append(chunk_id_str)

            chunk_obj = chunk_lookup.get(chunk_id_str)
            if chunk_obj is None:
                continue

            merged_meta = dict(chunk_obj.meta or {})
            base_retrieval_rrf = float(merged_meta.get("rrf_score", score))

            merged_meta["retrieval_rrf_score"] = float(
                merged_meta.get("retrieval_rrf_score", base_retrieval_rrf)
            )
            merged_meta["retrieval_score"] = score
            merged_meta["colbert_score"] = score
            merged_meta["retrieval_rank"] = int(position)
            merged_meta["colbert_rank"] = int(position)
            merged_meta["rerank_rrf_score"] = score

            chunk_obj.meta = merged_meta

        return reranked_view, reranked_ids

    def _prepare_inputs(
        self,
        sp: SuperPrompt,
    ) -> tuple[List[str], List[tuple[str, float, A3ChunkStatus]], Dict[str, Chunk]]:
        """
        Prepare the reranking job from the current SuperPrompt.

        Responsibilities grouped here on purpose:
        - validate stage and Retrieval availability,
        - build reranking query pieces from TASK / PURPOSE / CONTEXT,
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

        query_text = SuperPromptProjector.build_query_text(sp)

        query_pieces = split_query_into_pieces(
            query_text=query_text,
            chunker=self._chunker,
            chunk_size=DEFAULT_QUERY_CHUNK_SIZE,
            overlap=DEFAULT_QUERY_OVERLAP,
        )

        if not query_pieces:
            raise ValueError(
                "Reranker.run: no reranking query pieces could be built from SuperPrompt."
            )

        candidate_rows = list(retrieval_rows)[: self._top_k]
        chunk_lookup = {chunk_obj.id: chunk_obj for chunk_obj in sp.base_context_chunks}

        return query_pieces, candidate_rows, chunk_lookup

    def _clean_chunk_text(self, text: str) -> str:
        """
        Clean one chunk dynamically before ColBERT scoring.

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

    def _score_with_colbert(
        self,
        query_pieces: List[str],
        retrieval_rows: List[tuple[str, float, A3ChunkStatus]],
        chunk_lookup: Dict[str, Chunk],
    ) -> List[RankedRow]:
        """
        Score the Retrieval candidates with ColBERT over the reranking query pieces.

        Returns:
            List[(chunk_id, aggregated_colbert_score, metadata)]

        Aggregation rule:
        - Each query piece produces one ColBERT reranked list.
        - For each chunk, aggregate piece-level scores by arithmetic mean.
        - The final ColBERT ranked list is then sorted deterministically.
        """
        valid_ids: List[str] = []
        cleaned_snippets: List[str] = []

        for row in retrieval_rows:
            chunk_id = str(row[0])
            chunk_obj = chunk_lookup.get(chunk_id)
            if chunk_obj is None:
                continue

            cleaned_snippet = self._clean_chunk_text(chunk_obj.snippet or "")
            if not cleaned_snippet:
                continue

            valid_ids.append(chunk_id)
            cleaned_snippets.append(cleaned_snippet)

        if not valid_ids:
            raise ValueError(
                "Reranker.run: no valid Retrieval candidates could be prepared for ColBERT."
            )

        documents_per_query: List[List[str]] = [list(cleaned_snippets) for _ in query_pieces]
        document_ids_per_query: List[List[str]] = [list(valid_ids) for _ in query_pieces]

        queries_embeddings = self._colbert_model.encode(
            query_pieces,
            is_query=True,
            show_progress_bar=False,
        )

        documents_embeddings = self._colbert_model.encode(
            documents_per_query,
            is_query=False,
            show_progress_bar=False,
        )

        reranked_documents = rank.rerank(
            documents_ids=document_ids_per_query,
            queries_embeddings=queries_embeddings,
            documents_embeddings=documents_embeddings,
        )

        score_sums: Dict[str, float] = {}
        score_counts: Dict[str, int] = {}

        for one_query_result in reranked_documents:
            for item in one_query_result:
                chunk_id = str(item["id"])
                score = float(item["score"])
                score_sums[chunk_id] = score_sums.get(chunk_id, 0.0) + score
                score_counts[chunk_id] = score_counts.get(chunk_id, 0) + 1

        scored_rows: List[RankedRow] = []

        for chunk_id in valid_ids:
            if chunk_id not in score_counts:
                continue

            mean_score = score_sums[chunk_id] / float(score_counts[chunk_id])
            base_meta = dict((chunk_lookup.get(chunk_id).meta or {}))
            meta_out = dict(base_meta)
            meta_out["colbert_score"] = float(mean_score)

            scored_rows.append((chunk_id, float(mean_score), meta_out))

        scored_rows.sort(key=lambda row: (-row[1], row[0]))
        return scored_rows

    def _fuse_with_retrieval(
        self,
        retrieval_rows: List[tuple[str, float, A3ChunkStatus]],
        colbert_rows: List[RankedRow],
        chunk_lookup: Dict[str, Chunk],
    ) -> List[RankedRow]:
        """
        Fuse Retrieval ranking and ColBERT ranking with equal-weight RRF.
        """
        retrieval_ranked_rows: List[RankedRow] = []

        for chunk_id, retrieval_score, _status in retrieval_rows:
            chunk_obj = chunk_lookup.get(str(chunk_id))
            if chunk_obj is None:
                continue

            meta_out = dict(chunk_obj.meta or {})

            # Preserve the old Retrieval fused score explicitly before the
            # second RRF merge overwrites the generic key "rrf_score".
            if "rrf_score" in meta_out and "retrieval_rrf_score" not in meta_out:
                meta_out["retrieval_rrf_score"] = float(meta_out["rrf_score"])

            retrieval_ranked_rows.append((str(chunk_id), float(retrieval_score), meta_out))

        return rrf_merge(
            retrieval_ranked_rows,
            colbert_rows,
            top_k=self._top_k,
            weight_a=DEFAULT_RETRIEVAL_WEIGHT,
            weight_b=DEFAULT_COLBERT_WEIGHT,
        )

    def _project_fused_metadata_to_reranker_contract(
        self,
        fused_rows: List[RankedRow],
    ) -> List[RankedRow]:
        """
        Translate neutral RRF merger metadata into reranker-specific metadata.

        Design rule:
        - Preserve existing Retrieval metadata in chunk.meta.
        - Preserve the old Retrieval fused score under:
            retrieval_rrf_score
        - Add reranker-specific aliases here:
            retrieval_score
            colbert_score
            retrieval_rank
            colbert_rank
            rerank_rrf_score
        """
        projected_rows: List[RankedRow] = []

        for chunk_id, fused_score, meta in fused_rows:
            meta_in = dict(meta or {})
            meta_out = dict(meta_in)

            if "score_a" in meta_in and "retrieval_score" not in meta_out:
                meta_out["retrieval_score"] = float(meta_in["score_a"])

            if "score_b" in meta_in and "colbert_score" not in meta_out:
                meta_out["colbert_score"] = float(meta_in["score_b"])

            if "rank_a" in meta_in and "retrieval_rank" not in meta_out:
                meta_out["retrieval_rank"] = int(meta_in["rank_a"])

            if "rank_b" in meta_in and "colbert_rank" not in meta_out:
                meta_out["colbert_rank"] = int(meta_in["rank_b"])

            if "retrieval_rrf_score" not in meta_out and "score_a" in meta_in:
                meta_out["retrieval_rrf_score"] = float(meta_in["score_a"])

            meta_out["rerank_rrf_score"] = float(fused_score)

            projected_rows.append((str(chunk_id), float(fused_score), meta_out))

        return projected_rows

    def _write_scores_back_to_chunks(
        self,
        fused_rows: List[RankedRow],
        chunk_lookup: Dict[str, Chunk],
    ) -> None:
        """
        Persist the reranker metadata into the hydrated chunk objects so that
        SuperPromptProjector can render the score text directly from chunk.meta.
        """
        for chunk_id, _score, meta in fused_rows:
            chunk_obj = chunk_lookup.get(str(chunk_id))
            if chunk_obj is None:
                continue

            merged_meta = dict(chunk_obj.meta or {})
            for key, value in dict(meta or {}).items():
                merged_meta[key] = value

            chunk_obj.meta = merged_meta

    def _build_reranked_view(
        self,
        fused_rows: List[RankedRow],
    ) -> tuple[List[tuple[str, float, A3ChunkStatus]], List[str]]:
        """
        Build the ordered ReRanker stage snapshot.

        Deterministic sort:
        1) higher final fused rerank score first
        2) stable fallback by chunk_id
        """
        fused_rows.sort(key=lambda row: (-row[1], row[0]))

        reranked_view: List[tuple[str, float, A3ChunkStatus]] = []
        reranked_ids: List[str] = []

        for chunk_id, score, _meta in fused_rows:
            reranked_view.append((str(chunk_id), float(score), A3ChunkStatus.SELECTED))
            reranked_ids.append(str(chunk_id))

        return reranked_view, reranked_ids
```

### ~\ragstream\retrieval\retriever.py
```python
# retriever.py
# -*- coding: utf-8 -*-
"""
retriever.py

Purpose:
    Deterministic Retrieval stage orchestrator for RAGstream.

Design:
    - Keep Retriever as the top-level stage class used by the controller.
    - Keep query-building / query-splitting support logic outside this file.
    - Keep the dense retrieval backend in RetrieverEmb.
    - Add a parallel SPLADE retrieval backend in RetrieverSplade.
    - Merge both branches with deterministic RRF.
    - Keep hydration and SuperPrompt write-back in this file.
    - Preserve the current external Retriever.run(...) contract.

Current flow inside Retriever.run(...):
    1) PreProcessing
       - build retrieval query text from SuperPrompt
       - split the query into overlapping query pieces
    2) Retriever_EMB
       - run the dense embedding-based retrieval backend
    3) Retriever_SPLADE
       - score exactly the dense-selected candidate IDs
    4) RRF_Merger
       - fuse both ranked lists deterministically
    5) PostProcessing
       - hydrate ranked rows into real Chunk objects
       - write the retrieval result into SuperPrompt
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from ragstream.ingestion.chunker import Chunker
from ragstream.ingestion.embedder import Embedder
from ragstream.ingestion.splade_embedder import SpladeEmbedder
from ragstream.orchestration.super_prompt import A3ChunkStatus, SuperPrompt
from ragstream.orchestration.superprompt_projector import SuperPromptProjector
from ragstream.retrieval.chunk import Chunk
from ragstream.retrieval.doc_score import DocScore  # compatibility re-export
from ragstream.retrieval.retriever_emb import RetrieverEmb
from ragstream.retrieval.retriever_splade import RetrieverSplade
from ragstream.retrieval.rrf_merger import rrf_merge
from ragstream.retrieval.smart_query_splitter import split_query_into_pieces


# Keep old import compatibility:
# from ragstream.retrieval.retriever import DocScore
DocScore = DocScore

# Ranked row returned by RetrieverEmb / RetrieverSplade / RRF merger:
# (chunk_id, retrieval_score, metadata)
RankedRow = Tuple[str, float, Dict[str, Any]]

# Retrieval query splitting defaults.
# These MUST stay aligned with the current behavior so that the refactor
# preserves the same practical output as before.
DEFAULT_QUERY_CHUNK_SIZE = 1200
DEFAULT_QUERY_OVERLAP = 120


class Retriever:
    """
    Deterministic Retrieval stage orchestrator for document chunks.

    Design:
    - Keep this class focused on stage orchestration.
    - Keep low-level retrieval engine logic outside this file.
    - Keep hydration + SuperPrompt write-back here.
    - The evolving pipeline state still lives in SuperPrompt.
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
            chroma_root:
                Absolute path to the chroma_db root folder.
            embedder:
                Optional shared Embedder instance.
            chunker:
                Optional shared Chunker instance.
        """
        self.doc_root = Path(doc_root).resolve()
        self.chroma_root = Path(chroma_root).resolve()

        # SPLADE DB is kept parallel to chroma_db under the same data root.
        self.splade_root = self.chroma_root.parent / "splade_db"

        self.embedder = embedder if embedder is not None else Embedder(model="text-embedding-3-large")
        self.chunker = chunker if chunker is not None else Chunker()

        # Keep the chunk class explicit so hydration remains readable and testable.
        self.chunk_cls = Chunk

        # Dense backend remains unchanged and independent.
        self.retriever_emb = RetrieverEmb(
            chroma_root=str(self.chroma_root),
            embedder=self.embedder,
        )

        # Lazy init for SPLADE so app startup does not immediately load the sparse model.
        self._splade_embedder: SpladeEmbedder | None = None
        self._retriever_splade: RetrieverSplade | None = None

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def run(
        self,
        sp: SuperPrompt,
        project_name: str,
        top_k: int,
        *,
        use_retrieval_splade: bool = True,
    ) -> SuperPrompt:
        """
        Execute the Retrieval stage and update the same SuperPrompt in place.

        Visible flow:
            1) PreProcessing
            2) Retriever_EMB
            3) Retriever_SPLADE or dense passthrough clone
            4) RRF_Merger
            5) PostProcessing

        Returns:
            The same SuperPrompt instance, mutated in place.
        """
        query_pieces = self._preprocess(sp)

        ranked_rows_emb = self.retriever_emb.run(
            project_name=project_name,
            query_pieces=query_pieces,
            top_k=top_k,
        )

        ranked_rows_splade: List[RankedRow]

        if use_retrieval_splade:
            candidate_ids = [str(chunk_id) for chunk_id, _score, _meta in ranked_rows_emb]

            try:
                ranked_rows_splade = self._get_retriever_splade().run(
                    project_name=project_name,
                    query_pieces=query_pieces,
                    top_k=top_k,
                    candidate_ids=candidate_ids,
                )
            except FileNotFoundError:
                # Keep Retrieval usable even if an older project has no SPLADE store yet.
                ranked_rows_splade = []
        else:
            # Bypass real SPLADE and duplicate the dense branch into the second
            # RRF input slot so the downstream Retrieval contract stays unchanged.
            ranked_rows_splade = [
                (str(chunk_id), float(score), dict(meta or {}))
                for chunk_id, score, meta in ranked_rows_emb
            ]

        ranked_rows = rrf_merge(
            ranked_rows_emb,
            ranked_rows_splade,
            top_k=top_k,
            weight_a=0.75,
            weight_b=0.25,
        )

        ranked_rows = self._project_rrf_metadata_to_retrieval_contract(ranked_rows)

        sp = self._postprocess(sp, ranked_rows)
        return sp

    # -----------------------------------------------------------------
    # Stage-level orchestration helpers
    # -----------------------------------------------------------------

    def _preprocess(self, sp: SuperPrompt) -> List[str]:
        """
        Build the retrieval query text from SuperPrompt and split it into
        overlapping query pieces.

        Query-building and query-splitting support logic lives outside this file.
        Retriever keeps only the stage-level orchestration.
        """
        query_text = SuperPromptProjector.build_query_text(sp)

        query_pieces = split_query_into_pieces(
            query_text=query_text,
            chunker=self.chunker,
            chunk_size=DEFAULT_QUERY_CHUNK_SIZE,
            overlap=DEFAULT_QUERY_OVERLAP,
        )

        return query_pieces

    def _postprocess(self, sp: SuperPrompt, ranked_rows: List[RankedRow]) -> SuperPrompt:
        """
        Complete the Retrieval stage after the backend retrievers have finished.

        Responsibilities:
        - hydrate ranked rows into real Chunk objects
        - write the fused retrieval result into SuperPrompt
        """
        valid_ranked_rows, hydrated_chunks = self._hydrate_ranked_chunks(ranked_rows)
        self._write_stage_to_superprompt(sp, valid_ranked_rows, hydrated_chunks)
        return sp

    def _get_retriever_splade(self) -> RetrieverSplade:
        """
        Lazily initialize the SPLADE backend on first retrieval use.
        """
        if self._retriever_splade is None:
            if self._splade_embedder is None:
                self._splade_embedder = SpladeEmbedder(device="cpu")

            self._retriever_splade = RetrieverSplade(
                splade_root=str(self.splade_root),
                splade_embedder=self._splade_embedder,
            )

        return self._retriever_splade

    # -----------------------------------------------------------------
    # Internal helpers kept in retriever.py
    # -----------------------------------------------------------------

    def _project_rrf_metadata_to_retrieval_contract(
        self,
        ranked_rows: List[RankedRow],
    ) -> List[RankedRow]:
        """
        Translate neutral RRF merger metadata into retrieval-specific metadata.

        Why this exists:
        - rrf_merger.py is intentionally neutral and uses generic names:
            score_a, score_b, rank_a, rank_b
        - Retriever is the correct higher-level place that knows:
            a = dense embedding branch
            b = SPLADE branch
        - SuperPrompt projector and other retrieval-facing code can therefore
          keep reading the retrieval-specific names:
            emb_score, splade_score, emb_rank, splade_rank, rrf_score

        Design rule:
        - Preserve the neutral keys if they already exist.
        - Add the retrieval-specific aliases here.
        """
        projected_rows: List[RankedRow] = []

        for chunk_id, fused_score, meta in ranked_rows:
            meta_in = dict(meta or {})
            meta_out = dict(meta_in)

            if "score_a" in meta_in and "emb_score" not in meta_out:
                meta_out["emb_score"] = float(meta_in["score_a"])

            if "score_b" in meta_in and "splade_score" not in meta_out:
                meta_out["splade_score"] = float(meta_in["score_b"])

            if "rank_a" in meta_in and "emb_rank" not in meta_out:
                meta_out["emb_rank"] = int(meta_in["rank_a"])

            if "rank_b" in meta_in and "splade_rank" not in meta_out:
                meta_out["splade_rank"] = int(meta_in["rank_b"])

            if "rrf_score" not in meta_out:
                meta_out["rrf_score"] = float(fused_score)

            projected_rows.append((str(chunk_id), float(fused_score), meta_out))

        return projected_rows

    def _hydrate_ranked_chunks(
        self,
        ranked_rows: List[RankedRow],
    ) -> tuple[List[RankedRow], List[Chunk]]:
        """
        Reconstruct real Chunk objects for the selected ranked rows.

        Why reconstruction is needed:
        - Vector stores keep vectors + metadata only.
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
        valid_ranked_rows: List[RankedRow] = []
        hydrated: List[Chunk] = []

        # Local caches avoid re-reading and re-splitting the same source file
        # when several retrieved chunks come from that file.
        text_cache: Dict[str, str] = {}
        split_cache: Dict[str, List[tuple[str, str]]] = {}

        step = DEFAULT_QUERY_CHUNK_SIZE - DEFAULT_QUERY_OVERLAP

        for chunk_id, score, meta in ranked_rows:
            meta = meta or {}

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

            valid_ranked_rows.append((chunk_id, float(score), dict(meta)))
            hydrated.append(chunk_obj)

        return valid_ranked_rows, hydrated

    def _write_stage_to_superprompt(
        self,
        sp: SuperPrompt,
        ranked_rows: List[RankedRow],
        hydrated_chunks: List[Chunk],
    ) -> None:
        """
        Persist the Retrieval result into the evolving SuperPrompt.

        Write-back contract for this stage:
        - base_context_chunks:
            the hydrated Chunk objects in retrieval order
        - views_by_stage["retrieval"]:
            ordered triples (chunk_id, retrieval_score, SELECTED)
            where retrieval_score is now the final fused RRF score
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

        for chunk_id, score, _meta in ranked_rows:
            retrieval_view.append((str(chunk_id), float(score), A3ChunkStatus.SELECTED))
            final_ids.append(str(chunk_id))

        sp.views_by_stage["retrieval"] = retrieval_view
        sp.final_selection_ids = final_ids
        sp.stage = "retrieval"
        sp.history_of_stages.append("retrieval")
```

### ~\ragstream\retrieval\retriever_emb.py
```python
# retriever_emb.py
# -*- coding: utf-8 -*-
"""
retriever_emb.py

Purpose:
    Current embedding-based retrieval backend extracted out of retriever.py.

Scope of this file:
    - Receive neutral retrieval inputs only:
        * project_name
        * query_pieces
        * top_k
    - Open the active project's Chroma document store.
    - Compare every stored chunk embedding against all query-piece embeddings.
    - Aggregate per-chunk similarities with p-norm averaging.
    - Return ranked retrieval rows to the top-level Retriever stage.

Important design rule:
    - This class does NOT know SuperPrompt.
    - This class does NOT hydrate chunk text from doc_raw.
    - This class does NOT write anything back into the pipeline state.
    - It only performs the current embedding-based ranking backend.

Stage-1 refactor goal:
    Preserve the current embedding-based retrieval behavior while moving the
    backend ranking logic out of retriever.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from ragstream.ingestion.embedder import Embedder
from ragstream.ingestion.vector_store_chroma import VectorStoreChroma

# Ranked row returned to Retriever:
# (chunk_id, retrieval_score, metadata)
RankedRow = Tuple[str, float, Dict[str, Any]]

# Fallback number of chunks to keep if the caller gives no valid top-k.
DEFAULT_TOP_K = 100

# Agreed retrieval aggregation constant:
# p-value for p-norm averaging across query pieces.
DEFAULT_P_NORM = 10


class RetrieverEmb:
    """
    Current embedding-based retrieval backend.

    Design:
    - Receive neutral retrieval inputs only.
    - Perform current dense retrieval ranking.
    - Return ranked rows to the top-level Retriever.
    """

    def __init__(self, *, chroma_root: str, embedder: Embedder) -> None:
        """
        Initialize the embedding-based retrieval backend.

        Args:
            chroma_root:
                Absolute path to the chroma_db root folder.
            embedder:
                Shared Embedder instance used to embed the query pieces.
        """
        self.chroma_root = Path(chroma_root).resolve()
        self.embedder = embedder

    def run(self, *, project_name: str, query_pieces: List[str], top_k: int) -> List[RankedRow]:
        """
        Execute the current embedding-based retrieval backend.

        Inputs:
            project_name:
                Active project selected in the GUI.
            query_pieces:
                Pre-split retrieval query pieces.
            top_k:
                Number of chunks to keep after ranking.

        Returns:
            Ranked retrieval rows in this format:
                [
                    (chunk_id, retrieval_score, metadata),
                    ...
                ]

        Error-handling rule:
        - Local validation belongs here, at the lower level.
        - The top-level Retriever.run(...) stays visually simple.
        """
        project_name = (project_name or "").strip()
        if not project_name:
            raise ValueError("RetrieverEmb.run: project_name must not be empty")

        if not self.chroma_root.exists():
            raise FileNotFoundError(
                f"RetrieverEmb.run: chroma_root does not exist: {self.chroma_root}"
            )

        project_db_dir = self.chroma_root / project_name
        if not project_db_dir.exists():
            raise FileNotFoundError(
                f"RetrieverEmb.run: active project Chroma DB does not exist: {project_db_dir}"
            )

        if not query_pieces:
            return []

        k = int(top_k) if int(top_k) > 0 else DEFAULT_TOP_K

        store = VectorStoreChroma(persist_dir=str(project_db_dir))
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
                "RetrieverEmb.run: Chroma returned mismatched ids/embeddings lengths"
            )

        if len(metadatas) > 0 and len(metadatas) != len(ids):
            raise RuntimeError(
                "RetrieverEmb.run: Chroma returned mismatched ids/metadatas lengths"
            )

        query_vectors = self.embedder.embed(query_pieces)

        if len(query_vectors) == 0:
            return []

        A = np.asarray(embeddings, dtype=np.float32)    # stored chunks: [N, D]
        Q = np.asarray(query_vectors, dtype=np.float32) # query pieces:  [M, D]

        if A.ndim != 2 or Q.ndim != 2:
            raise RuntimeError(
                "RetrieverEmb.run: unexpected embedding dimensions returned by Chroma/OpenAI"
            )

        if A.shape[1] != Q.shape[1]:
            raise RuntimeError(
                "RetrieverEmb.run: stored vectors and query vectors have different dimensions"
            )

        # Normalize rows to compute cosine similarity as a matrix product.
        # Similarities shape: [N_chunks, M_query_pieces]
        A_norm = A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-12)
        Q_norm = Q / (np.linalg.norm(Q, axis=1, keepdims=True) + 1e-12)
        sims = A_norm @ Q_norm.T

        # p-mean aggregation over the query-piece axis.
        # Strongly favors the best match, but is still not pure max.
        p = DEFAULT_P_NORM
        sims_pos = np.clip(sims, 0.0, None)
        aggregated_scores = np.power(np.mean(np.power(sims_pos, p), axis=1), 1.0 / p)

        rows: List[RankedRow] = []
        for idx, chunk_id in enumerate(ids):
            meta = metadatas[idx] if (len(metadatas) > 0 and metadatas[idx] is not None) else {}
            rows.append(
                (
                    str(chunk_id),
                    float(aggregated_scores[idx]),
                    dict(meta),
                )
            )

        # Deterministic sort:
        # 1) higher score first
        # 2) stable fallback by chunk_id
        rows.sort(key=lambda row: (-row[1], row[0]))

        return rows[: min(k, len(rows))]
```

### ~\ragstream\retrieval\retriever_splade.py
```python
# retriever_splade.py
# -*- coding: utf-8 -*-
"""
retriever_splade.py

Purpose:
    SPLADE-based retrieval backend extracted out of retriever.py.

Scope of this file:
    - Receive neutral retrieval inputs only:
        * project_name
        * query_pieces
        * top_k
        * optional candidate_ids
    - Open the active project's SPLADE document store.
    - Compare stored sparse chunk representations against all query-piece
      sparse representations.
    - Aggregate per-chunk similarities with p-norm averaging.
    - Return ranked retrieval rows to the top-level Retriever stage.

Important design rule:
    - This class does NOT know SuperPrompt.
    - This class does NOT hydrate chunk text from doc_raw.
    - This class does NOT write anything back into the pipeline state.
    - It only performs the SPLADE-based ranking backend.

Design goal:
    Keep the same programming culture and return contract as RetrieverEmb
    wherever possible.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from ragstream.ingestion.splade_embedder import SpladeEmbedder
from ragstream.ingestion.vector_store_splade import VectorStoreSplade

# Ranked row returned to Retriever:
# (chunk_id, retrieval_score, metadata)
RankedRow = Tuple[str, float, Dict[str, Any]]

# Fallback number of chunks to keep if the caller gives no valid top-k.
DEFAULT_TOP_K = 100

# Agreed retrieval aggregation constant:
# p-value for p-norm averaging across query pieces.
DEFAULT_P_NORM = 10


class RetrieverSplade:
    """
    SPLADE-based retrieval backend.

    Design:
    - Receive neutral retrieval inputs only.
    - Perform sparse retrieval ranking.
    - Return ranked rows to the top-level Retriever.
    """

    def __init__(self, *, splade_root: str, splade_embedder: SpladeEmbedder) -> None:
        """
        Initialize the SPLADE retrieval backend.

        Args:
            splade_root:
                Absolute path to the splade_db root folder.
            splade_embedder:
                Shared SpladeEmbedder instance used to encode the query pieces.
        """
        self.splade_root = Path(splade_root).resolve()
        self.splade_embedder = splade_embedder

    def run(
        self,
        *,
        project_name: str,
        query_pieces: List[str],
        top_k: int,
        candidate_ids: List[str] | None = None,
    ) -> List[RankedRow]:
        """
        Execute the SPLADE-based retrieval backend.

        Args:
            project_name:
                Active project name selected in the GUI.
            query_pieces:
                Overlapping retrieval query pieces prepared by the top-level Retriever.
            top_k:
                Number of rows to keep after ranking when running in global-search mode.
            candidate_ids:
                Optional fixed candidate set. When provided, SPLADE scores exactly
                these IDs and does not perform its own independent top-k search.

        Returns:
            Ranked retrieval rows in this format:
                [
                    (chunk_id, retrieval_score, metadata),
                    ...
                ]

        Error-handling rule:
        - Local validation belongs here, at the lower level.
        - The top-level Retriever.run(...) stays visually simple.
        """
        project_name = (project_name or "").strip()
        if not project_name:
            raise ValueError("RetrieverSplade.run: project_name must not be empty")

        if not self.splade_root.exists():
            raise FileNotFoundError(
                f"RetrieverSplade.run: splade_root does not exist: {self.splade_root}"
            )

        project_db_dir = self.splade_root / project_name
        if not project_db_dir.exists():
            raise FileNotFoundError(
                f"RetrieverSplade.run: active project SPLADE DB does not exist: {project_db_dir}"
            )

        if not query_pieces:
            return []

        k = int(top_k) if int(top_k) > 0 else DEFAULT_TOP_K

        store = VectorStoreSplade(persist_dir=str(project_db_dir))

        doc_vectors: Dict[str, Dict[str, float]] = store.index
        meta_store: Dict[str, Dict[str, Any]] = getattr(store, "_meta_store", {})

        if len(doc_vectors) == 0:
            return []

        query_vectors = self.splade_embedder.embed_queries(query_pieces)
        if len(query_vectors) == 0:
            return []

        target_ids: List[str]
        use_fixed_candidates = candidate_ids is not None

        if use_fixed_candidates:
            seen: set[str] = set()
            target_ids = []

            for chunk_id in candidate_ids or []:
                cid = str(chunk_id).strip()
                if not cid:
                    continue
                if cid in seen:
                    continue
                seen.add(cid)
                target_ids.append(cid)

            if len(target_ids) == 0:
                return []

            missing_ids = [cid for cid in target_ids if cid not in doc_vectors]
            if missing_ids:
                preview = ", ".join(missing_ids[:10])
                suffix = " ..." if len(missing_ids) > 10 else ""
                raise RuntimeError(
                    "RetrieverSplade.run: candidate_ids are missing in the active SPLADE store. "
                    f"Missing {len(missing_ids)} id(s): {preview}{suffix}"
                )
        else:
            target_ids = list(doc_vectors.keys())

        rows: List[RankedRow] = []

        p = DEFAULT_P_NORM

        for chunk_id in target_ids:
            doc_vec = doc_vectors[chunk_id]
            per_piece_scores: List[float] = []

            for query_vec in query_vectors:
                sim = self._dot_sparse(doc_vec, query_vec)
                per_piece_scores.append(float(sim))

            if len(per_piece_scores) == 0:
                aggregated_score = 0.0
            else:
                sims_pos = [max(0.0, float(s)) for s in per_piece_scores]
                aggregated_score = (
                    sum(pow(s, p) for s in sims_pos) / float(len(sims_pos))
                ) ** (1.0 / p)

            meta = meta_store.get(chunk_id, {})
            rows.append(
                (
                    str(chunk_id),
                    float(aggregated_score),
                    dict(meta),
                )
            )

        # Deterministic sort:
        # 1) higher score first
        # 2) stable fallback by chunk_id
        rows.sort(key=lambda row: (-row[1], row[0]))

        if use_fixed_candidates:
            return rows

        return rows[: min(k, len(rows))]

    @staticmethod
    def _dot_sparse(left: Dict[str, float], right: Dict[str, float]) -> float:
        """
        Dot product over sparse dicts.

        Iterate over the smaller dict for efficiency.
        """
        if len(left) > len(right):
            left, right = right, left

        score = 0.0
        for key, value in left.items():
            score += float(value) * float(right.get(key, 0.0))
        return score
```

### ~\ragstream\retrieval\rrf_merger.py
```python
# rrf_merger.py
# -*- coding: utf-8 -*-
"""
rrf_merger.py

Purpose:
    Deterministic weighted Reciprocal Rank Fusion (RRF) helper.

Role:
    - Merge two ranked result lists in a neutral way.
    - Produce one fused ranked list.
    - Preserve metadata and attach neutral rank/score fields.

Important design rule:
    - This module is purely deterministic.
    - It does not know SuperPrompt.
    - It does not know dense / SPLADE semantics.
    - It does not hydrate chunk text.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# Ranked row contract shared with retriever.py / retriever_emb.py / retriever_splade.py
RankedRow = Tuple[str, float, Dict[str, Any]]

# Common practical default for RRF.
DEFAULT_RRF_K = 60


def rrf_merge(
    rows_a: List[RankedRow],
    rows_b: List[RankedRow],
    *,
    top_k: int | None = None,
    rrf_k: int = DEFAULT_RRF_K,
    weight_a: float = 1.0,
    weight_b: float = 1.0,
) -> List[RankedRow]:
    """
    Merge two ranked lists with weighted Reciprocal Rank Fusion.

    Args:
        rows_a:
            First ranked row list.
        rows_b:
            Second ranked row list.
        top_k:
            Optional final cutoff.
        rrf_k:
            RRF constant. Larger values flatten rank differences more.
        weight_a:
            Weight for the first ranked list.
        weight_b:
            Weight for the second ranked list.

    Returns:
        One fused ranked row list:
            [
                (chunk_id, fused_rrf_score, metadata_with_neutral_scores),
                ...
            ]
    """
    by_id: Dict[str, Dict[str, Any]] = {}

    for rank, (chunk_id, score, meta) in enumerate(rows_a, start=1):
        row = by_id.setdefault(str(chunk_id), {})
        row["meta"] = _merge_meta(row.get("meta"), meta)
        row["rank_a"] = int(rank)
        row["score_a"] = float(score)

    for rank, (chunk_id, score, meta) in enumerate(rows_b, start=1):
        row = by_id.setdefault(str(chunk_id), {})
        row["meta"] = _merge_meta(row.get("meta"), meta)
        row["rank_b"] = int(rank)
        row["score_b"] = float(score)

    fused_rows: List[RankedRow] = []

    for chunk_id, row in by_id.items():
        rank_a = row.get("rank_a")
        rank_b = row.get("rank_b")

        fused_score = 0.0
        if rank_a is not None:
            fused_score += float(weight_a) / float(rrf_k + int(rank_a))
        if rank_b is not None:
            fused_score += float(weight_b) / float(rrf_k + int(rank_b))

        meta = dict(row.get("meta") or {})

        if row.get("score_a") is not None:
            meta["score_a"] = float(row["score_a"])
        if row.get("score_b") is not None:
            meta["score_b"] = float(row["score_b"])

        if rank_a is not None:
            meta["rank_a"] = int(rank_a)
        if rank_b is not None:
            meta["rank_b"] = int(rank_b)

        meta["rrf_score"] = float(fused_score)

        fused_rows.append((str(chunk_id), float(fused_score), meta))

    # Deterministic sort:
    # 1) higher fused score first
    # 2) stable fallback by chunk_id
    fused_rows.sort(key=lambda row: (-row[1], row[0]))

    if top_k is None:
        return fused_rows

    k = int(top_k)
    if k <= 0:
        return fused_rows

    return fused_rows[: min(k, len(fused_rows))]


def _merge_meta(
    base_meta: Dict[str, Any] | None,
    new_meta: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """
    Merge metadata conservatively.

    Rule:
    - keep existing keys
    - add missing keys from the new metadata
    - do not silently overwrite existing values
    """
    merged = dict(base_meta or {})
    for key, value in dict(new_meta or {}).items():
        if key not in merged:
            merged[key] = value
    return merged
```

### ~\ragstream\retrieval\smart_query_splitter.py
```python
# smart_query_splitter.py
# -*- coding: utf-8 -*-
"""
smart_query_splitter.py

Purpose:
    External query-splitting support functions for Retrieval.

Stage-1 refactor scope:
    - Keep the current linear overlapping query-splitting logic outside retriever.py.
    - Preserve the current behavior exactly as closely as possible.

Important note:
    The current splitting logic is still the existing deterministic linear
    windowing logic. Later, this file can be upgraded internally to a smarter
    query-splitting implementation (for example wtpsplit) without changing the
    top-level Retriever stage contract.
"""

from __future__ import annotations

from typing import List

from ragstream.ingestion.chunker import Chunker


def split_query_into_pieces(
    *,
    query_text: str,
    chunker: Chunker,
    chunk_size: int,
    overlap: int,
) -> List[str]:
    """
    Split the retrieval query into overlapping query pieces.

    Current Stage-1 behavior:
    - Reuse the same deterministic chunking idea as ingestion.
    - Preserve the current retrieval splitter behavior.
    - Return only the text pieces.

    Later upgrade path:
    - This function body can be replaced by a smarter splitter implementation
      without changing the top-level Retriever stage contract.
    """
    query_text = (query_text or "").strip()
    if not query_text:
        return []

    if chunker is None:
        raise ValueError("split_query_into_pieces: 'chunker' must not be None")

    if chunk_size <= 0:
        raise ValueError("split_query_into_pieces: chunk_size must be positive")

    if overlap < 0:
        raise ValueError("split_query_into_pieces: overlap must be non-negative")

    if overlap >= chunk_size:
        raise ValueError(
            "split_query_into_pieces: overlap must be smaller than chunk_size"
        )

    pieces = chunker.split(
        file_path="__prompt__",
        text=query_text,
        chunk_size=chunk_size,
        overlap=overlap,
    )

    return [chunk_text for _fp, chunk_text in pieces if (chunk_text or "").strip()]
```


## /home/rusbeh_ab/project/RAGstream/ragstream/memory

### ~\ragstream\memory\memory_actions.py
```python
# ragstream/memory/memory_actions.py
# -*- coding: utf-8 -*-
"""
Memory actions
==============
Reusable workflow functions for memory capture.

GUI buttons, future LLM calls, Copilot calls, or tool results should call
these functions instead of embedding memory logic directly in UI callbacks.
"""

from __future__ import annotations

from typing import Any

from ragstream.memory.memory_manager import MemoryManager
from ragstream.textforge.RagLog import LogALL as logger


def capture_memory_pair(
    memory_manager: MemoryManager,
    input_text: str,
    output_text: str,
    source: str,
    active_project_name: str | None = None,
    embedded_files_snapshot: list[str] | None = None,
    parent_id: str | None = None,
    user_keywords: list[str] | None = None,
    gui_records_state: list[dict[str, Any]] | None = None,
    memory_ingestion_manager: Any | None = None,
) -> dict[str, Any]:
    clean_input = (input_text or "").strip()
    clean_output = (output_text or "").strip()

    if not clean_input:
        return {
            "success": False,
            "message": "Prompt is empty. No memory record was created.",
            "record": None,
        }

    if not clean_output:
        return {
            "success": False,
            "message": "Manual memory response is empty. No memory record was created.",
            "record": None,
        }

    memory_manager.sync_gui_edits(gui_records_state or [])

    record = memory_manager.capture_pair(
        input_text=clean_input,
        output_text=clean_output,
        source=source,
        parent_id=parent_id,
        user_keywords=user_keywords,
        active_project_name=active_project_name,
        embedded_files_snapshot=embedded_files_snapshot or [],
    )

    logger(
        f"Memory record saved: {record.record_id}",
        "INFO",
        "PUBLIC",
    )

    logger(
        (
            "MemoryRecord captured: "
            f"record={record.record_id[:8]} | "
            f"file={memory_manager.filename_ragmem} | "
            f"tag={record.tag}"
        ),
        "INFO",
        "INTERNAL",
    )

    if memory_ingestion_manager is not None:
        try:
            memory_ingestion_manager.ingest_record_async(record.record_id)
        except Exception as e:
            logger(
                f"MemoryRecord was saved, but vector ingestion could not be scheduled: {e}",
                "WARN",
                "PUBLIC",
            )

    return {
        "success": True,
        "message": f"Memory record saved: {record.record_id}",
        "record": record,
        "record_id": record.record_id,
        "file_id": memory_manager.file_id,
        "filename_ragmem": memory_manager.filename_ragmem,
    }
```

### ~\ragstream\memory\memory_chunker.py
```python
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
             #   f"TAG: {record.tag or ''}",
            #    f"USER_KEYWORDS: {self._join_list(record.user_keywords)}",
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
```

### ~\ragstream\memory\memory_ingestion_manager.py
```python
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
```

### ~\ragstream\memory\memory_manager.py
```python
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
```

### ~\ragstream\memory\memory_record.py
```python
# ragstream/memory/memory_record.py
# -*- coding: utf-8 -*-
"""
MemoryRecord
============
One accepted input/output memory unit.

Authority split:
- .ragmem stores only the stable append-only memory body.
- .ragmeta.json stores current metadata.
- SQLite mirrors .ragmeta.json for fast lookup/indexing.

A MemoryRecord in RAM contains both:
- stable body fields
- current metadata fields

Only stable body fields are serialized into .ragmem.
"""

from __future__ import annotations

import hashlib
import json
import uuid

from datetime import datetime, timezone
from typing import Any


RECORD_START = "----- MEMORY RECORD START -----"
RECORD_END = "----- MEMORY RECORD END -----"


RETRIEVAL_SOURCE_MODES = {"QA", "Q", "A"}


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


def _clean_retrieval_source_mode(value: str | None) -> str:
    mode = str(value or "QA").strip().upper()
    return mode if mode in RETRIEVAL_SOURCE_MODES else "QA"


def _clean_direct_recall_key(value: str | None) -> str:
    return str(value or "").strip()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text if text else None


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
        retrieval_source_mode: str = "QA",
        direct_recall_key: str = "",
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
        self.retrieval_source_mode: str = _clean_retrieval_source_mode(retrieval_source_mode)
        self.direct_recall_key: str = _clean_direct_recall_key(direct_recall_key)

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
        retrieval_source_mode: str | None = None,
        direct_recall_key: str | None = None,
    ) -> None:
        if tag is not None:
            clean_tag = str(tag).strip()
            if clean_tag:
                self.tag = clean_tag

        if user_keywords is not None:
            self.user_keywords = _clean_list(user_keywords)

        if retrieval_source_mode is not None:
            self.retrieval_source_mode = _clean_retrieval_source_mode(retrieval_source_mode)

        if direct_recall_key is not None:
            self.direct_recall_key = _clean_direct_recall_key(direct_recall_key)

    def update_metadata_overlay(
        self,
        metadata: dict[str, Any],
    ) -> None:
        """
        Apply current metadata loaded from .ragmeta.json.

        This method deliberately does not modify stable .ragmem body fields:
        - record_id
        - parent_id
        - created_at_utc
        - input_text
        - output_text
        - source
        - input_hash
        - output_hash
        """
        if not isinstance(metadata, dict):
            return

        self.update_editable_metadata(
            tag=metadata.get("tag"),
            user_keywords=list(metadata.get("user_keywords") or []),
            retrieval_source_mode=metadata.get("retrieval_source_mode"),
            direct_recall_key=metadata.get("direct_recall_key"),
        )

        if "auto_keywords" in metadata:
            self.auto_keywords = _clean_list(list(metadata.get("auto_keywords") or []))

        if "active_project_name" in metadata:
            self.active_project_name = _optional_str(metadata.get("active_project_name"))

        if "embedded_files_snapshot" in metadata:
            self.embedded_files_snapshot = list(metadata.get("embedded_files_snapshot") or [])

    def to_ragmem_dict(self) -> dict[str, Any]:
        """
        Stable append-only .ragmem body.

        Editable GUI metadata is intentionally excluded from this dictionary.
        """
        return {
            "record_id": self.record_id,
            "parent_id": self.parent_id,
            "created_at_utc": self.created_at_utc,
            "input_text": self.input_text,
            "output_text": self.output_text,
            "source": self.source,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
        }

    def to_ragmem_block(self) -> str:
        body = json.dumps(self.to_ragmem_dict(), ensure_ascii=False, indent=2)
        return f"{RECORD_START}\n{body}\n{RECORD_END}\n"

    def to_index_dict(self) -> dict[str, Any]:
        """
        Current metadata/index view.

        This dictionary is used for:
        - .ragmeta.json per-record metadata
        - SQLite mirror rows

        It does not duplicate full input_text or output_text.
        """
        return {
            "record_id": self.record_id,
            "parent_id": self.parent_id,
            "created_at_utc": self.created_at_utc,
            "source": self.source,
            "tag": self.tag,
            "retrieval_source_mode": self.retrieval_source_mode,
            "direct_recall_key": self.direct_recall_key,
            "auto_keywords": self.auto_keywords,
            "user_keywords": self.user_keywords,
            "active_project_name": self.active_project_name,
            "embedded_files_snapshot": self.embedded_files_snapshot,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
        }

    def to_full_dict(self) -> dict[str, Any]:
        """
        Full in-RAM diagnostic/export view.

        This is not used for .ragmem serialization.
        """
        data = self.to_ragmem_dict()
        data.update(
            {
                "tag": self.tag,
                "retrieval_source_mode": self.retrieval_source_mode,
                "direct_recall_key": self.direct_recall_key,
                "auto_keywords": self.auto_keywords,
                "user_keywords": self.user_keywords,
                "active_project_name": self.active_project_name,
                "embedded_files_snapshot": self.embedded_files_snapshot,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryRecord":
        """
        Load one MemoryRecord from a .ragmem block.

        Supports both:
        - new body-only .ragmem blocks
        - older full .ragmem blocks that still contain metadata

        Current metadata from .ragmeta.json is applied later by MemoryManager.
        """
        auto_keywords_raw = data.get("auto_keywords")

        return cls(
            input_text=str(data.get("input_text", "")),
            output_text=str(data.get("output_text", "")),
            source=str(data.get("source", "")),
            parent_id=_optional_str(data.get("parent_id")),
            tag=str(data.get("tag", "Green")),
            user_keywords=list(data.get("user_keywords") or []),
            active_project_name=_optional_str(data.get("active_project_name")),
            embedded_files_snapshot=list(data.get("embedded_files_snapshot") or []),
            retrieval_source_mode=str(data.get("retrieval_source_mode", "QA")),
            direct_recall_key=str(data.get("direct_recall_key", "")),
            record_id=str(data.get("record_id") or uuid.uuid4().hex),
            created_at_utc=str(data.get("created_at_utc") or _utc_now()),
            auto_keywords=(
                list(auto_keywords_raw)
                if isinstance(auto_keywords_raw, list)
                else None
            ),
            input_hash=data.get("input_hash"),
            output_hash=data.get("output_hash"),
        )
```

### ~\ragstream\memory\memory_vector_store.py
```python
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

