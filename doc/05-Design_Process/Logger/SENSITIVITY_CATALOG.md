SENSITIVITY_CATALOG

PUBLIC
  Meaning:
    Safe for normal GUI messages, ordinary CLI output, and general logs.
  Examples:
    "User pressed Add Files button."
    "Ingestion completed."
    "File aws_notes.md was added."
    "ReRanker is still initializing."
  Typical sinks:
    GuiSink
    CliSink
    normal FileSink


INTERNAL
  Meaning:
    Developer/team diagnostic information.
    Not secret, but not useful or appropriate for normal users.
  Examples:
    "Retrieval top_k = 30."
    "A3 useful count = 18."
    "SPLADE branch disabled."
    "A2 invalid option id sanitized."
  Typical sinks:
    developer FileSink
    CLI in dev mode
    Sink0 archive


CONFIDENTIAL
  Meaning:
    Legitimate developer-analysis material that may contain user/project content.
    Allowed only in deliberately configured protected sinks.
  Examples:
    full user prompt.
    full SuperPrompt sent to LLM.
    retrieved chunks attached to prompt.
    LLM response captured for history.
    retrieval score table if it exposes document content or private file names.
  Typical sinks:
    protected local FileSink
    mandatory archive only if configured for confidential content
    not normal GUI


HIGHLY_CONFIDENTIAL
  Meaning:
    Exceptional class.
    Normally should not be logged.
    Reserved for material that would be damaging if exposed.
  Examples:
    API keys.
    AWS credentials.
    session tokens.
    passwords.
    private legal/medical/raw personal data if ever present.
  Typical sinks:
    default policy: no sink accepts it.
    better rule: do not log it at all.



    TextForge severity types:
  TRACE
  DEBUG
  INFO
  WARN
  ERROR
  FATAL

TextForge sensitivity flags:
  PUBLIC
  INTERNAL
  CONFIDENTIAL
  HIGHLY_CONFIDENTIAL

Default sensitivity:
  PUBLIC

Normal rule:
  log events freely at PUBLIC/INTERNAL,
  log CONFIDENTIAL only to protected sinks,
  avoid HIGHLY_CONFIDENTIAL entirely.