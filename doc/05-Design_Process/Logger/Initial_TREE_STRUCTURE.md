Updated baseline with sensitivity added, without changing the structure:

```text id="g7tnm8"
TextForge
│
├─ id: str
│    Last/current unique log id generated for one emitted log entry.
│
├─ text: str
│    Current/default text value; updated when new text is provided.
│
├─ type: str
│    Current/default log severity type, e.g. "INFO"; reused when no new type is provided.
│
├─ sensitivity: str
│    Current/default sensitivity flag, e.g. "PUBLIC"; reused when no new sensitivity is provided.
│
├─ sinks: list[TextSink]
│    All available sink objects; usually structurally identical across TextForge presets.
│
├─ b_enable: list[bool]
│    Enable map; b_enable[i] decides whether sinks[i] is called for this log.
│
└─ methods
   │
   ├─ __init__(
   │      text: str = "",
   │      type: str = "INFO",
   │      sensitivity: str = "PUBLIC",
   │      sinks: list[TextSink] | None = None,
   │      b_enable: list[bool] | None = None
   │   ) -> None
   │      Initializes current text/type/sensitivity, sink list, and enable map.
   │
   ├─ __call__(
   │      text: str | None = None,
   │      type: str | None = None,
   │      sensitivity: str | None = None
   │   ) -> None
   │      Shortcut so the object can be used like logger("text"), logger("text", "INFO"), or logger("text", "INFO", "CONFIDENTIAL").
   │
   ├─ log(
   │      text: str | None = None,
   │      type: str | None = None,
   │      sensitivity: str | None = None
   │   ) -> None
   │      Updates text/type/sensitivity, generates a new id, loops over enabled sinks, and calls sink.log(id, text, type, sensitivity).
   │
   └─ _generate_id() -> str
          Creates a long unique id, e.g. with uuid4().hex.


TextSink
│
├─ sink_kind: str | None
│    Defines which prefix/suffix group is used: "file", "gui", "cli"; set by subclasses.
│
├─ accept_types: list[str]
│    List of log severity types this sink accepts, e.g. ["INFO", "WARN", "ERROR"].
│
├─ accept_sensitivities: list[str]
│    List of sensitivity flags this sink accepts, e.g. ["PUBLIC", "INTERNAL"].
│
├─ LOG_TYPE_CATALOG: dict[str, dict[str, str]]
│    Central fixed catalog of all known severity types and their file/gui/cli prefixes and suffixes.
│
├─ SENSITIVITY_CATALOG: dict[str, dict[str, str]]
│    Central fixed catalog of known sensitivity flags and their meaning.
│
├─ b_timestamp: bool
│    If True, formatted output includes timestamp.
│
├─ b_prefix: bool
│    If True, formatted output includes the prefix for this type and sink_kind.
│
├─ b_suffix: bool
│    If True, formatted output includes the suffix for this type and sink_kind.
│
└─ methods
   │
   ├─ __init__(
   │      sink_kind: str | None,
   │      accept_types: list[str],
   │      accept_sensitivities: list[str],
   │      b_timestamp: bool = True,
   │      b_prefix: bool = True,
   │      b_suffix: bool = False
   │   ) -> None
   │      Initializes common sink filtering and formatting configuration.
   │
   ├─ accepts(
   │      type: str,
   │      sensitivity: str
   │   ) -> bool
   │      Returns True only if this sink accepts both the given log type and sensitivity.
   │
   ├─ _format_text(
   │      id: str,
   │      text: str,
   │      type: str,
   │      sensitivity: str
   │   ) -> str
   │      Builds the final output text using timestamp plus catalog prefix/suffix for this sink_kind.
   │
   └─ log(
          id: str,
          text: str,
          type: str,
          sensitivity: str
       ) -> None
          Common sink interface; concrete sinks implement the real output action.


FileSink(TextSink)
│
├─ path: str
│    Target log file path or log folder path, depending on final file policy.
│
├─ rotation_size: int
│    Maximum file size before rotation/splitting logic is used.
│
├─ split_flag: bool
│    If True, file rotation/splitting is active.
│
├─ b_sqlite: bool
│    If True, this FileSink writes SQLite metadata/index after file write.
│
├─ sqlite_path: str | None
│    SQLite database path used only when b_sqlite is True.
│
├─ b_async: bool
│    If True, this FileSink uses asynchronous writing instead of blocking the caller.
│
└─ methods
   │
   ├─ __init__(
   │      path: str,
   │      accept_types: list[str],
   │      accept_sensitivities: list[str],
   │      rotation_size: int,
   │      split_flag: bool,
   │      b_sqlite: bool = False,
   │      sqlite_path: str | None = None,
   │      b_async: bool = False,
   │      b_timestamp: bool = True,
   │      b_prefix: bool = True,
   │      b_suffix: bool = False
   │   ) -> None
   │      Initializes file output, sets sink_kind = "file", and stores file/sqlite/async options.
   │
   ├─ log(
   │      id: str,
   │      text: str,
   │      type: str,
   │      sensitivity: str
   │   ) -> None
   │      If accepted by type and sensitivity, formats final text, writes it to file, then writes SQLite metadata if enabled.
   │
   └─ close() -> None
          Flushes/closes file or async resources if they exist.


GuiSink(TextSink)
│
├─ session_state: object
│    Streamlit session_state or a small wrapper around it.
│
├─ key: str
│    session_state key where the GUI-visible text is written.
│
└─ methods
   │
   ├─ __init__(
   │      session_state: object,
   │      key: str,
   │      accept_types: list[str],
   │      accept_sensitivities: list[str],
   │      b_timestamp: bool = True,
   │      b_prefix: bool = True,
   │      b_suffix: bool = False
   │   ) -> None
   │      Initializes GUI target, sets sink_kind = "gui", and stores session_state/key.
   │
   └─ log(
          id: str,
          text: str,
          type: str,
          sensitivity: str
       ) -> None
          If accepted by type and sensitivity, formats final text and writes it into session_state[key].


CliSink(TextSink)
│
├─ stream: str
│    CLI output target, e.g. "stdout" or "stderr".
│
└─ methods
   │
   ├─ __init__(
   │      stream: str,
   │      accept_types: list[str],
   │      accept_sensitivities: list[str],
   │      b_timestamp: bool = True,
   │      b_prefix: bool = True,
   │      b_suffix: bool = False
   │   ) -> None
   │      Initializes CLI target, sets sink_kind = "cli", and stores stdout/stderr choice.
   │
   └─ log(
          id: str,
          text: str,
          type: str,
          sensitivity: str
       ) -> None
          If accepted by type and sensitivity, formats final text and writes it to the selected CLI stream.
```
