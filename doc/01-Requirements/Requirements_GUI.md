## Requirements_GUI.md

1. Scope and assumptions

---

1. The GUI is the human-facing front-end for RAGstream. Its main job is:

   * to let the user write and inspect prompts,
   * to step through or trigger the 8-stage RAG pipeline,
   * to manage ingestion and active DB selection,
   * and, in later versions, to manage history, tags, and model calls.

2. There will be three GUI “generations”:

   * Generation 1: Intermediate GUI (current Streamlit view, manual, pipeline-centric).
   * Generation 2: Main GUI with history, tags, model selection, cost view, manual answer capture.
   * Generation 3: Advanced GUI (multi-history, attention controls, tools, etc.) – ideas only.

3. The implementation technology for Generation 1 and 2 is currently Streamlit (`ui_streamlit.py` in `ragstream/app`), but the requirements are written so that the GUI could later be reimplemented in another framework without changing behavior.

4. All pipeline logic and state live in the controller + `SuperPrompt`. The GUI is a thin layer that:

   * sends user actions to the controller, and
   * renders the current `SuperPrompt.prompt_ready` and relevant debug information.

5. Core concepts used by the GUI

---

1. `SuperPrompt` is the canonical object that represents the current prompt and context. It has fields like:

   * `body`, `System_MD`, `Prompt_MD`, `S_CTX_MD`, `Attachments_MD`,
   * `prompt_ready` (final composed prompt),
   * `stage`, `history_of_stages`,
   * retrieval views and selection ids.

2. The 8 RAG pipeline stages are:

   * A0_PreProcessing
   * A2_PromptShaper
   * Retrieval
   * ReRanker
   * A3_NLI_Gate
   * A4_Condenser
   * A5_Format_Enforcer
   * Prompt_Builder

   Their behavior is defined in `Requirements_RAG_Pipeline.md`. GUI requirements here only describe their *invocation* and *visualization*.

3. The GUI must always operate on a single active `SuperPrompt` instance per session. After each stage, the controller updates that instance, and the GUI re-renders the current `prompt_ready` and any stage-specific info.

4. Generation 1 – Intermediate GUI (pipeline tester)

---

3.1 Objectives

1. Let the user:

   * type or paste a raw prompt (plain text or markdown with `##` headers),
   * manually run each of the 8 pipeline stages in order,
   * inspect how `SuperPrompt` changes after each stage,
   * run ingestion and choose the active Chroma DB.

2. This GUI is primarily for **development and debugging**, not for end users:

   * it exposes all stages,
   * everything is triggered manually with buttons,
   * there is no history or tagging yet,
   * no API call to external LLMs from this generation.

3.2 Layout

The intermediate GUI must provide at least the following UI elements:

1. Prompt input area

   * A large text area labeled “User Prompt” (or similar).
   * The user can:

     * paste a simple, naked text prompt, or
     * paste markdown with `##SYSTEM`, `##TASK`, etc.
   * When A0_PreProcessing runs, this text is the raw input.

2. SuperPrompt view

   * A large text area labeled “SuperPrompt (prompt_ready)”.
   * After each stage button is pressed, this area shows the **current** `SuperPrompt.prompt_ready` exactly as it would be sent to an LLM (for this generation, it is just visible, not sent).
   * This field can be read-only in the UI; editing is not required in Generation 1.

3. Pipeline control buttons (8 buttons)
   Each stage has its own button, in this order:

   * Button: “A0 – PreProcessing”
   * Button: “A2 – PromptShaper”
   * Button: “Retrieval”
   * Button: “ReRanker”
   * Button: “A3 – NLI Gate”
   * Button: “A4 – Condenser”
   * Button: “A5 – Format Enforcer”
   * Button: “Prompt Builder (Final Prompt)”

   Behavior:

   * When a button is pressed, the controller:

     * runs the corresponding stage on the active `SuperPrompt`,
     * returns the updated `SuperPrompt`.
   * The GUI then:

     * updates the SuperPrompt view,
     * updates any stage-specific debug area (see 3.3.2).

4. Ingestion controls

   * Text input / file-browser-like field “Raw folder under data/doc_raw” (e.g. `Project1`).
   * Button: “Ingest Folder”:

     * It must take a folder path under `data/doc_raw` (e.g. `myroot/data/doc_raw/Project1`),
     * run the ingestion pipeline on all text/markdown files in that folder,
     * create/update the corresponding Chroma DB in `data/chroma_db/Project1`.
   * A small status area shows:

     * success message (number of files, project name),
     * or clear error messages.

5. Active DB selection

   * A dropdown or radio button group labeled “Active DB / Project”.
   * Options correspond to directories under `data/chroma_db` (e.g. `Project1`, `Project2`, …).
   * The currently selected project name is passed to Retrieval/ReRanker so they know which DB to query.

6. Minimal debug/status info

   * A small area (or a few lines) showing:

     * the current stage (`SuperPrompt.stage`),
     * number of retrieval candidates and final selections (after Retrieval, ReRanker, A3, A4).
   * A status line at the bottom showing the result of the last action (OK, error, message).

3.3 Stage-specific behavior and state machine

3.3.1 Global state machine

1. The GUI must enforce a **legal order** of stages using a simple state machine:

   * Precondition: A0_PreProcessing must be run at least once before any retrieval stage.
   * Normal forward order:

     * A0 → A2 → Retrieval → ReRanker → A3 → A4 → A5 → Prompt Builder.
   * A2 may be re-run any time **after** A0 (and before or after retrieval), as long as the pipeline is in a consistent state:

     * e.g. user can do A0 → A2 → A2 (refine meta labels) → Retrieval → …
   * Buttons for illegal transitions must either:

     * be disabled, or
     * show a clear error message (“Please run PreProcessing first”, “You must run Retrieval before ReRanker”, etc.).

2. The controller is the single authority for stage transitions:

   * It validates whether a stage can be run given the current `SuperPrompt.stage`.
   * If not, it returns an error that the GUI displays.

3. The GUI must not mutate `SuperPrompt` directly; only stages do so.

3.3.2 What is shown in SuperPrompt view per stage

The SuperPrompt view always shows the current `SuperPrompt.prompt_ready`. Internally, this is updated step by step as defined in `Requirements_RAG_Pipeline.md`. For the GUI, the behavior should feel like this:

1. After “A0 – PreProcessing”

   * `prompt_ready` shows the normalized prompt with canonical headers, MUST defaults, and any extras that A0 writes.
   * No retrieval context is shown yet.

2. After “A2 – PromptShaper”

   * `prompt_ready` still shows the whole prompt, but now with the updated `system`, `audience`, `tone`, `depth`, and `confidence`.
   * The GUI doesn’t need to highlight these specifically, but the text reflects the new meta labels.

3. After “Retrieval”

   * In addition to the prompt text, the resulting `prompt_ready` should include a simple textual list of **all retrieved raw chunks** (RAG context) at the bottom or in a clearly separated block.

   * For the intermediate GUI, this can be a minimal debug list, e.g.:

     ```
     --- RAG Context (Retrieval) ---
     [chunk_id_1] <snippet1...>
     [chunk_id_2] <snippet2...>
     ...
     ```

   * This is primarily for human inspection, not the final format.

4. After “ReRanker”

   * `prompt_ready` is updated so that the RAG context block now lists the reranked chunks in their new order, e.g.:

     ```
     --- RAG Context (ReRanked) ---
     [chunk_id_7] <snippet7...>
     [chunk_id_3] <snippet3...>
     ...
     ```

5. After “A3 – NLI Gate”

   * `prompt_ready` is updated so the RAG context block now only contains the chunks that A3 decided to keep (after irrelevant/duplicate/conflicting chunks are dropped).

6. After “A4 – Condenser”

   * `prompt_ready` is close to its final form:

     * It includes `S_CTX_MD` (the condensed context block) in the correct place.
     * The raw chunk list can remain visible as a debug block under S_CTX for the intermediate GUI, but S_CTX is the main thing.

7. After “A5 – Format Enforcer”

   * The prompt reflects normalized output format instructions (for JSON/markdown/etc.), but in Generation 1 it is still just a textual prompt shown in the SuperPrompt view.

8. After “Prompt Builder (Final Prompt)”

   * `prompt_ready` is the true final SuperPrompt as it would be sent to the answering LLM:

     * System block,
     * Prompt block,
     * S_CTX block,
     * Attachments block (raw chunks),
     * Optional recent conversation block.

3.4 Non-goals for Intermediate GUI

1. No history view (only current session).
2. No tagging (GOLD/SILVER/etc.).
3. No model selection or cost estimation.
4. No direct LLM call from this GUI generation.

All of these are reserved for Generation 2 and 3.

4. Generation 2 – Main product GUI (history, tags, LLM)

---

Generation 2 builds on the intermediate GUI and adds:

* chat history,
* tags,
* model selection and direct LLM call,
* cost estimation,
* manual answer capture.

Details are intentionally less strict than Generation 1 but must express the final goals.

4.1 Objectives

1. Provide a usable “product-level” GUI where:

   * the user can create prompts and run them through the pipeline (manual or controller-driven),
   * the final SuperPrompt can be sent directly to an LLM via API,
   * history and tags are visible and manageable,
   * costs are visible and not surprising,
   * manual answer capture is supported.

2. Generation 2 is the first version where you can say “the product is finished” for personal and internal use.

4.2 Chat history and tags

1. The GUI must display a conversation history, where each entry is a Q/A pair:

   * `user` – the prompt (ideally the final SuperPrompt or a simplified view),
   * `assistant` – the model’s answer (either from API or pasted manually),
   * metadata (timestamp, project, etc.).

2. Every conversation entry must support tags:

   * minimal structure example:

     ```json
     {
       "id": 1,
       "user": "...",
       "assistant": "...",
       "tags": ["GOLD"]
     }
     ```

   * The exact JSON shape is not fixed yet, but:

     * each entry can have 0–N tags,
     * tags are strings,
     * tags have user-editable meanings (descriptions) somewhere in the GUI.

3. The GUI must allow:

   * assigning tags to a single entry (e.g. via dropdown, checkbox, or text input),
   * editing or removing tags,
   * filtering history by tags (e.g. show only GOLD, or hide BLUE).

4. These tags will later drive retrieval/tag rules and cross-chat import, but for Generation 2 it is enough that:

   * tags are visible,
   * tags can be assigned and changed,
   * tags are persisted.

4.3 Model selection and sending SuperPrompt to LLM

1. The GUI must provide controls for selecting a model and calling it:

   * A dropdown (“Model”) listing available backends (e.g. OpenAI models).
   * A button “Send Final SuperPrompt” (or similar).

2. When the user presses “Send Final SuperPrompt”:

   * The controller must ensure that:

     * the full pipeline has been run (A0 → … → Prompt Builder),
     * or, at least, that a consistent `prompt_ready` exists.
   * The llm_client is invoked with:

     * the selected model,
     * the final `prompt_ready` contents.
   * The model’s output is stored as a new history entry, associated with:

     * the final SuperPrompt,
     * the model name,
     * any tags the user adds (e.g. GOLD for a very good answer).

3. The GUI must show the model’s answer in the history view and optionally in a “Current Response” pane.

4.4 Cost estimation

1. The GUI must provide a simple cost estimation view for each run:

   * For each agent call (A2, A3, A4, A5, and final answer call), show:

     * approximate prompt tokens,
     * approximate completion tokens,
     * approximate cost based on configured price per token.

   * For each session, show:

     * total estimated cost of all LLM calls in that session.

2. Cost data can be:

   * rough estimates (no need for perfect accuracy),
   * but they must be calculated in a consistent way, based on:

     * token length of `prompt_ready` and other calls,
     * model pricing from configuration.

3. The cost view must be clearly visible but not intrusive, e.g. a side panel or bottom bar.

4.5 Manual answer capture

1. The GUI must support a workflow where:

   * the user copies the final SuperPrompt,
   * pastes it into ChatGPT UI or another external client,
   * then copies the model’s answer back into RAGstream.

2. For this, the GUI must have:

   * a text field labeled e.g. “Paste external model answer here”,
   * a button like “Save as history entry”.

3. When the user presses “Save as history entry”:

   * the system creates a Q/A history entry that:

     * uses the current final SuperPrompt as `user`,
     * uses the pasted text as `assistant`,
     * allows the user to assign tags (e.g. GOLD),
     * stores all metadata as if the answer had come via API.

4. Manual and API answers should be indistinguishable in how history and tags operate.

4.6 Relationship between manual and automatic triggering

1. Generation 2 must allow **both**:

   * manual step-by-step runs (like Intermediate GUI), and
   * automatic “one click” run, where the controller executes the full pipeline and then calls the LLM.

2. The GUI may reuse the same 8 pipeline buttons or offer:

   * a “Run all stages + send to LLM” button,

   * while still exposing the individual stage buttons for debugging.

3. Generation 3 – Advanced GUI (vision)

---

Generation 3 collects ideas and directions; it is *not* a commitment. It describes one possible future advanced GUI beyond Generation 2.

5.1 Goals

1. Turn RAGstream into a full interactive workbench for:

   * complex RAG and agentic workflows,
   * multiple projects,
   * software development support (e.g. V-model activities).

2. Provide powerful but controlled tools for:

   * multi-history and multi-project management,
   * dynamic attention / context control,
   * agent orchestration and tool use.

5.2 Possible features (non-binding)

The following ideas are examples; they may change:

1. Multiple history control

   * View and manage many histories across projects.
   * Import/export histories by tag (e.g. import GOLD items from 10 chats).
   * Visualize which histories contribute to the current `SuperPrompt`.

2. Dynamic attention control

   * Sidebars or panels where the user can:

     * toggle which projects/DBs are active,
     * select which tags are considered (GOLD, SILVER, etc.),
     * adjust weights or priorities of different memory sources.

3. Sidebar controls for agents and tools

   * Controls to enable/disable certain agents or tools (e.g. code refactorer, test generator).
   * Configuration of agent roles and models without editing JSON by hand.

4. AI-Agency and orchestration view

   * Visual representation of the agent graph / flow (who calls whom, in what order).
   * Ability to trigger “sub-flows” (e.g. code generation, test design, documentation generation) as separate tasks.

5. V-Diagram aware tooling

   * Panels for requirements, design, implementation, testing, and validation, aligned with V-model stages.
   * Ability to track which requirements and tests relate to which agents and prompts.

6. Extended debug and analysis tools

   * Rich per-stage visualizations (retrieval, rerank, NLI decisions, condensation).
   * Token and cost heatmaps.
   * Comparison of different runs (e.g. “diff” between two S_CTX versions).

5.3 Status of Generation 3

1. Generation 3 is **visionary only** in this document.
2. No layout, technology, or fixed feature set is decided yet.
3. When Generation 2 is stable and in real use, selected ideas from Generation 3 can be promoted into their own detailed GUI requirements document.


