LOG_TYPE_CATALOG

TRACE
  Meaning:
    Very fine-grained internal flow information.
    Usually disabled in normal operation.
    Useful only when reconstructing exact internal execution paths.
  Standard mapping:
    OpenTelemetry TRACE
    Python has no exact built-in TRACE level; closest practical mapping is DEBUG or custom TRACE.
  Example:
    Entered Retriever._hydrate_ranked_chunks().
    Query part 3/7 was sent to dense retrieval.
    Sink 5 rejected type DEBUG because accept_types did not include it.
    A4 condenser loop processed chunk index 12.
  Sensitivity examples:
    PUBLIC:
      rarely used.
    INTERNAL:
      "Entered Retrieval stage hydration path."
      "GuiSink rejected TRACE record."
    CONFIDENTIAL:
      "Prompt segment 2/5 was attached to retrieval query." 
      without full prompt text, maybe INTERNAL; with full text, CONFIDENTIAL.
    HIGHLY_CONFIDENTIAL:
      normally avoid.
  Prefix:
    file_prefix = "[TRACE] "
    gui_prefix  = ""
    cli_prefix  = "[TRACE] "
  Suffix:
    normally empty


DEBUG
  Meaning:
    Developer-level diagnostic information.
    Less granular than TRACE, but still not usually interesting for normal users.
    Used to understand why the system made a certain internal decision.
  Standard mapping:
    OpenTelemetry DEBUG
    Python DEBUG
  Example:
    Retrieval top_k = 30.
    Dense candidates before RRF = 30.
    SPLADE branch disabled by GUI checkbox.
    A3 selected 18 useful chunks and 4 borderline chunks.
    FileSink b_async=True, queued record id abc123.
    Current active project resolved as AWS.
  Sensitivity examples:
    PUBLIC:
      usually not needed.
    INTERNAL:
      "Retrieval top_k = 30."
      "SPLADE branch disabled."
      "A3 useful count = 18."
    CONFIDENTIAL:
      "Retrieved chunk ids and scores for user prompt X."
      "Full scoring table for selected project documents."
    HIGHLY_CONFIDENTIAL:
      normally avoid.
  Prefix:
    file_prefix = "[DEBUG] "
    gui_prefix  = ""
    cli_prefix  = "[DEBUG] "
  Suffix:
    normally empty


INFO
  Meaning:
    Normal successful event.
    Something meaningful happened and the application continues normally.
    This is the main level for lifecycle events, user actions, and completed operations.
  Standard mapping:
    OpenTelemetry INFO
    Python INFO
  Example:
    Application started.
    User pressed Add Files button.
    File aws_notes.md was added to project AWS.
    Project AWS was created.
    Ingestion started for project AWS.
    Ingestion completed for project AWS.
    Retrieval completed for project AWS.
    A4 condenser completed and wrote S_CTX_MD.
    User selected active project AWS.
  Sensitivity examples:
    PUBLIC:
      "File aws_notes.md was added."
      "Ingestion completed."
      "Project AWS selected."
    INTERNAL:
      "Controller started run_retrieval()."
      "Prompt Builder button pressed."
    CONFIDENTIAL:
      "User prompt stored for developer analysis."
      "Full SuperPrompt sent to LLM."
      "LLM output captured for history."
    HIGHLY_CONFIDENTIAL:
      normally avoid.
  Prefix:
    file_prefix = "[INFO] "
    gui_prefix  = ""
    cli_prefix  = "[INFO] "
  Suffix:
    normally empty


WARN
  Meaning:
    Unusual or degraded situation, but not a failure.
    The system handled it or used a fallback.
    Important enough to notice, but the application continues.
  Standard mapping:
    OpenTelemetry WARN
    Python WARNING
  Example:
    ReRanker is still initializing; request skipped.
    No active project was selected; default project was used.
    SPLADE disabled, dense ranking duplicated into SPLADE slot.
    Uploaded file report.pdf rejected because only .txt/.md are supported.
    A2 returned invalid option id; sanitized output preserved old value.
    SQLite metadata write delayed because database was temporarily locked.
  Sensitivity examples:
    PUBLIC:
      "Uploaded file report.pdf rejected because only .txt/.md are supported."
      "ReRanker is still initializing."
    INTERNAL:
      "A2 invalid option id was removed during sanitization."
      "Dense fallback used because SPLADE was disabled."
    CONFIDENTIAL:
      "A prompt-related chunk was excluded by filtering rule."
      only if the text or document reference itself exposes private context.
    HIGHLY_CONFIDENTIAL:
      normally avoid.
  Prefix:
    file_prefix = "[WARN] "
    gui_prefix  = "Warning: "
    cli_prefix  = "[WARN] "
  Suffix:
    normally empty


ERROR
  Meaning:
    Operational failure.
    Something failed, but the application or session can continue after reporting or fallback.
    Often relevant for GUI, CLI, and file logs.
  Standard mapping:
    OpenTelemetry ERROR
    Python ERROR
  Example:
    File ingestion failed for project AWS.
    LLM call failed.
    Project delete failed.
    Chroma query failed.
    A4 condenser failed to parse LLM response.
    File write succeeded but SQLite metadata write failed.
    Uploaded file could not be copied to doc_raw.
  Sensitivity examples:
    PUBLIC:
      "Ingestion failed for project AWS."
      "Project delete failed."
    INTERNAL:
      "A4 JSON parse failed."
      "SQLite metadata write failed after file write."
    CONFIDENTIAL:
      "LLM call failed for full SuperPrompt id abc123."
      The ID is okay; full prompt text would be confidential.
    HIGHLY_CONFIDENTIAL:
      do not include secrets in the error message.
  Prefix:
    file_prefix = "[ERROR] "
    gui_prefix  = "Error: "
    cli_prefix  = "[ERROR] "
  Suffix:
    normally empty


FATAL
  Meaning:
    Critical unrecoverable failure.
    The application, session, or core subsystem cannot safely continue.
    Reserved for rare cases.
  Standard mapping:
    OpenTelemetry FATAL
    Python closest standard mapping: CRITICAL
  Example:
    Sink0 archive path is unavailable and mandatory archive logging cannot continue.
    Critical project state is corrupted.
    SuperPrompt state is inconsistent and cannot be safely repaired.
    Required data root is missing or not writable.
    Application startup failed because core configuration cannot be loaded.
  Sensitivity examples:
    PUBLIC:
      "Application cannot continue because required storage is unavailable."
    INTERNAL:
      "Mandatory Sink0 failed during startup."
      "SuperPrompt state invariant violated."
    CONFIDENTIAL:
      "Fatal failure while processing confidential prompt id abc123."
      Do not include the full confidential prompt unless deliberately routed to a protected sink.
    HIGHLY_CONFIDENTIAL:
      only exceptional; normally never log highly confidential raw content.
  Prefix:
    file_prefix = "[FATAL] "
    gui_prefix  = "Fatal error: "
    cli_prefix  = "[FATAL] "
  Suffix:
    normally empty