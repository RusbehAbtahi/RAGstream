
# RAGstream — TODO (2025-10-21)

* [ ] Streamlit GUI V1 (manual pipeline view)

  * Decision: start with per-step buttons (manual) to observe each stage; later add “Auto” mode to run the full pipeline.
  * Buttons (8): A0 PreProcessing, A2 PromptShaper, Retrieval, Reranker, A3 NLI Gate, A4 Condenser, A5 Format Enforcer, Prompt Builder.

* [ ] Implement `PreProcessing.py` (new module; update Architecture/UML/Requirements accordingly)

  * Deterministic parse of the user prompt into required headers: SYSTEM, AUDIENCE, DEPTH, TASK, CONTEXT, PURPOSE.
  * If any required header is missing/uncertain, call a low-cost LLM to map user headers → standard schema; only accept high-confidence mappings; otherwise apply safe defaults.
  * Persist results to session state; render normalized prompt into Super-Prompt for transparency.

* [ ] Secrets: OPENAI_API_KEY on WSL

  * Add `export OPENAI_API_KEY=...` to `~/.bashrc` (or `~/.zshrc`); `source` the file to load.
  * Ensure secrets never enter Git (use `.gitignore`; avoid committing dotfiles with keys).
  * Verify access via `os.getenv("OPENAI_API_KEY")`.

* [ ] A4 Condenser policy

  * Replace the current “triad” with a “quad”: Facts, Assumptions, Constraints, Open Questions.
  * Update `Requirements.md` to reflect the quad everywhere.

* [ ] Retrieval policy

  * Build retrieval text strictly from TASK, CONTEXT, PURPOSE, and the raw USER PROMPT.
  * If the user provides extra headers that PreProcessing cannot map with confidence, exclude them by default.
  * (Future) Add a checkbox to opt-in “Include unmapped headers in retrieval.”

* [ ] Reranker choice

  * Use a cross-encoder reranker (e.g., BERT-based) for better ordering after initial cosine retrieval.
  * Keep both retriever_score and rerank_score; optionally blend for final ordering.

* [ ] GUI refactor plan

  * Move CSS and layout glue from `ui_streamlit_2.py` into a small helper later (e.g., `ui_styles.py`).
  * Keep button callbacks thin; centralize pipeline logic in dedicated modules (Controller later, but interim step functions are fine).
  * Goal: UI files remain clean; logic/testable functions live outside the view.

* [ ] Session state (“MATLAB handle” analogue)

  * Use `st.session_state["rag"]` (dict or dataclass) as the single shared state across all buttons.
  * Namespacing: `rag.prompt.raw`, `rag.preproc.headers`, `rag.superprompt.text`, `rag.retrieval.selected`, `rag.rerank.ordered`, etc.


