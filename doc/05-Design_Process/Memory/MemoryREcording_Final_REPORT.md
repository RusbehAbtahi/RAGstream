# RAGstream Memory Recording Design and Implementation Report

Date context: 28 April 2026
Purpose: handover report for a new chat
Scope: memory recording layer, manual memory feed, GUI integration, `.ragmem`, `.ragmeta.json`, SQLite, Runtime Log integration, tag/keyword handling

---

## 1. Communication / workflow context

This chat was about memory design and ingestion, but the work completed here is only Part 1: memory recording.

The user explicitly wants a precise, implementation-oriented discussion. Do not invent new architectural classes or abstractions unless they are clearly necessary and approved.

Important style rule from this chat:

* Do not use “V1”, “version 1”, “first implementation”, or similar wording unless the user explicitly calls something temporary.
* Treat the design as intended long-term architecture.
* Do not introduce speculative future restructuring language.
* Do not describe RAGstream as a toy, hobby, demo, or casual prototype.
* Do not add generic warnings or vague “limitations.”
* If something is uncertain, state the exact issue precisely.
* If suggesting a new design element, explain why it is necessary before adding it.

---

## 2. High-level accepted architecture

The accepted memory-recording architecture has exactly two core objects:

* `MemoryManager`
* `MemoryRecord`

Rejected / do not reintroduce:

* `MemorySession`
* `ActiveMemoryFileState`
* any third middle class between `MemoryManager` and `MemoryRecord`

Correct meaning:

* `MemoryManager` represents one active memory history file / active `.ragmem` memory file.
* `MemoryManager` owns the full list of `MemoryRecord` objects.
* `MemoryManager` owns `metainfo`.
* `MemoryRecord` represents one accepted input/output pair.
* `MemoryRecord` does not contain a list of records.
* `MemoryRecord` does not own MetaInfo.
* GUI is only a view/editor.
* `.ragmem` stores durable full records.
* `.ragmeta.json` stores current rewritten lightweight metadata.
* SQLite is the global searchable metadata index.

Final mental model:

```text
Streamlit GUI
  ↓
memory_actions.capture_memory_pair(...)
  ↓
MemoryManager
  ├─ records: list[MemoryRecord]
  ├─ metainfo: dict
  ├─ .ragmem append
  ├─ .ragmeta.json rewrite
  └─ SQLite refresh
```

---

## 3. File layout

The final memory code location is:

```text
ragstream/memory/
├─ __init__.py
├─ memory_record.py
├─ memory_manager.py
└─ memory_actions.py
```

Responsibilities:

```text
memory_record.py
  Contains MemoryRecord only.

memory_manager.py
  Contains MemoryManager only.

memory_actions.py
  Contains reusable workflow function capture_memory_pair(...).
```

App files touched:

```text
ragstream/app/ui_streamlit.py
ragstream/app/ui_actions.py
ragstream/app/ui_layout.py
```

Dependency update:

```text
requirements.txt
```

Add:

```text
yake>=0.4.8              # local automatic keyword extraction for MemoryRecord
```

---

## 4. Data layout

The final data root is:

```text
data/memory/
```

Not:

```text
data/history/memory/
```

Reason: the subsystem is not just raw chat history. It is structured, tagged, indexed, reusable memory.

Final layout:

```text
data/memory/
├─ files/
│  ├─ YYYY-MM-DD-HH-mm-TITLE.ragmem
│  └─ YYYY-MM-DD-HH-mm-TITLE.ragmeta.json
│
└─ memory_index.sqlite3
```

With project root:

```text
/home/rusbeh_ab/project/RAGstream
```

the full paths are:

```text
/home/rusbeh_ab/project/RAGstream/data/memory/files/*.ragmem
/home/rusbeh_ab/project/RAGstream/data/memory/files/*.ragmeta.json
/home/rusbeh_ab/project/RAGstream/data/memory/memory_index.sqlite3
```

---

## 5. Core class: MemoryManager

Final audited fields:

```text
MemoryManager
│
├─ file_id: str
│    Unique ID of the active .ragmem memory file/history.
│
├─ title: str
│    Human-readable memory title.
│
├─ filename_ragmem: str
│    Durable memory filename.
│    Pattern: YYYY-MM-DD-HH-mm-TITLE.ragmem
│
├─ filename_meta: str
│    Metadata sidecar filename.
│    Pattern: YYYY-MM-DD-HH-mm-TITLE.ragmeta.json
│
├─ memory_root: Path
│    data/memory/
│
├─ sqlite_path: Path
│    data/memory/memory_index.sqlite3
│
├─ records: list[MemoryRecord]
│    Full active list of memory records.
│
├─ metainfo: dict
│    Current lightweight metadata rebuilt from records.
│
├─ tag_catalog: list[str]
│    Current accepted tags.
│
└─ b_file_created: bool
     False until first MemoryRecord is physically saved.
```

Final audited methods:

```text
__init__(memory_root: Path, sqlite_path: Path, title: str = "") -> None
start_new_history(title: str) -> None
load_history(file_id: str) -> None
list_histories() -> list[dict]
capture_pair(...) -> MemoryRecord
sync_gui_edits(gui_records_state: list[dict]) -> None
save_metainfo() -> None
refresh_sqlite_index() -> None
_build_metainfo() -> dict
close() -> None
```

Removed as unnecessary from the audited design:

```text
manager_id
chroma_root
b_vector_update_async
schedule_chroma_update(...)
status
retrieval_eligible
embedded_files_count
project_context_timestamp_utc
```

Reason:

* Chroma belongs to memory ingestion, not memory recording.
* Retrieval behavior belongs to memory retrieval, not memory recording.
* `embedded_files_count` is derivable from `embedded_files_snapshot`.
* `project_context_timestamp_utc` duplicates `created_at_utc` for the current design.
* `status` and `retrieval_eligible` were not needed because tag state is enough at this layer.

---

## 6. Core class: MemoryRecord

Final audited fields:

```text
MemoryRecord
│
├─ record_id: str
│    Unique stable ID of this memory input/output pair.
│
├─ parent_id: str | None
│    Optional parent record ID for future correction/continuation relationships.
│
├─ created_at_utc: str
│    UTC timestamp when record was created.
│
├─ input_text: str
│    Raw Prompt text from the GUI.
│    Not SuperPrompt.
│
├─ output_text: str
│    Accepted response/output.
│
├─ source: str
│    Example: "manual_memory_feed".
│
├─ tag: str
│    User-facing tag.
│
├─ auto_keywords: list[str]
│    YAKE-generated keywords.
│
├─ user_keywords: list[str]
│    Manual user-entered keywords.
│
├─ active_project_name: str | None
│    Active DB / Project at capture time.
│
├─ embedded_files_snapshot: list[str]
│    Complete embedded files list at capture time.
│
├─ input_hash: str
│    Hash of input_text.
│
└─ output_hash: str
     Hash of output_text.
```

Final audited methods:

```text
__init__(...) -> None
generate_auto_keywords() -> list[str]
update_editable_metadata(tag: str | None = None, user_keywords: list[str] | None = None) -> None
to_ragmem_block() -> str
to_index_dict() -> dict
```

Additional implemented helper:

```text
from_dict(...)
```

used for loading records from `.ragmem`.

---

## 7. Tags

Original tag list was:

```text
["Platin", "GOLD", "SILVER", "Green", "Black"]
```

The user later decided to simplify and improve it.

Current desired tag list:

```text
["Gold", "Silver", "Red", "Green", "Black"]
```

Change in `ragstream/memory/memory_manager.py`:

```python
self.tag_catalog: list[str] = ["Gold", "Silver", "Red", "Green", "Black"]
```

No change is needed in `MemoryRecord`, because `tag` is just a string.

Development note:

* No normalization of old test files is needed.
* The project is still actively developing this feature.
* Existing test `.ragmem` / `.ragmeta.json` files can be disposable.

---

## 8. Tag color indicator in GUI

The user wanted a small color square / rectangle near the tag selector, not a full custom selectbox popup.

Correct approach:

* Do not try to style Streamlit selectbox popup.
* Add a small colored HTML badge in `render_memory_records()`.
* Badge color follows current selected tag.

File:

```text
ragstream/app/ui_layout.py
```

Add near top:

```python
TAG_COLORS: dict[str, str] = {
    "Gold": "#D4AF37",
    "Silver": "#C0C7D2",
    "Red": "#E0115F",
    "Green": "#00A86B",
    "Black": "#111111",
}
```

Important latest change:

The first green chosen was too dark:

```python
"Green": "#0D4C3C",
```

The user said it could be mistaken for black. Replace with jade green:

```python
"Green": "#00A86B",
```

CSS classes added in `inject_base_css()`:

```css
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
```

In `render_memory_records()`:

```python
selected_tag = st.session_state.get(tag_key, record.tag)
tag_color = TAG_COLORS.get(selected_tag, "#6B7280")
```

Then render badge before the selectbox:

```python
st.markdown(
    f"""
    <div class="memory-tag-indicator">
        <span class="memory-tag-square" style="background-color:{tag_color};"></span>
        <span class="memory-tag-name">{html.escape(selected_tag)}</span>
    </div>
    """,
    unsafe_allow_html=True,
)
```

---

## 9. Manual Memory Feed flow

Current capture trigger:

```text
Feed Memory Manually
```

GUI field:

```text
manual_memory_feed_text
```

Flow:

```text
User writes Prompt
User pastes response into Manual Memory Feed
User presses Feed Memory Manually
  ↓
do_feed_memory_manually()
  ↓
capture_memory_pair(...)
  ↓
MemoryManager.capture_pair(...)
  ↓
MemoryRecord created
  ↓
.ragmem appended
.ragmeta.json rewritten
SQLite refreshed
GUI memory display updated
```

Important rule:

`input_text` must be raw Prompt text:

```text
st.session_state["prompt_text"]
```

Not:

```text
SuperPrompt
A2 output
Prompt Builder output
retrieved context
```

Reason: MemoryRecord captures what the user asked and what answer was accepted.

---

## 10. First memory title behavior

At startup:

```text
MemoryManager.title == ""
```

No physical `.ragmem` file exists.

When the user presses `Feed Memory Manually` for the first time:

1. Validate prompt is non-empty.
2. Validate manual response is non-empty.
3. If no title exists:

   * store the prompt/response pair in `pending_manual_memory_pair`
   * set `memory_title_required = True`
   * log an INFO message
   * call `st.rerun()`

This is normal first-use flow, not a warning.

Correct log type:

```python
_log_runtime("Enter a memory title to create the first memory file.", "INFO", "PUBLIC")
```

Not:

```python
"WARN"
```

Need `st.rerun()` immediately after setting `memory_title_required = True`, otherwise the title form does not appear immediately.

Correct block in `do_feed_memory_manually()`:

```python
if not memory_manager.title.strip():
    st.session_state["pending_manual_memory_pair"] = {
        "input_text": prompt_text,
        "output_text": output_text,
    }
    st.session_state["memory_title_required"] = True
    _log_runtime("Enter a memory title to create the first memory file.", "INFO", "PUBLIC")
    st.rerun()
```

The form appears in memory area:

```python
render_memory_title_form()
```

After user enters title:

```python
do_confirm_memory_title_and_save()
```

This calls:

```python
memory_manager.start_new_history(title)
```

Then saves the pending pair.

---

## 11. Runtime Log integration

The user already had a TextForge/RagLog logging subsystem.

The memory workflow should use it, not a parallel `memory_status` mechanism.

Important files:

```text
ragstream/textforge/TextForge.py
ragstream/textforge/TextSink.py
ragstream/textforge/GUISink.py
ragstream/textforge/FileSink.py
ragstream/textforge/CliSink.py
ragstream/textforge/RagLog.py
```

`RagLog.py` provides:

```python
LogALL()
LogNoGUI()
LogConf()
```

`LogALL()` creates 4 sinks:

```text
sinks[0] = Sink0_Archive
sinks[1] = File_PublicRun
sinks[2] = CliRuntimeSink
sinks[3] = GuiPublicSink
```

The GUI sink writes into:

```text
st.session_state["textforge_gui_log"]
```

Initialize logger in `ui_streamlit.py`:

```python
from ragstream.textforge.RagLog import LogALL
```

Inside `init_session_state()`:

```python
if "textforge_gui_log" not in st.session_state:
    st.session_state["textforge_gui_log"] = ""

if "raglog" not in st.session_state:
    st.session_state.raglog = LogALL(session_state=st.session_state)
```

Helper in `ui_actions.py`:

```python
def _log_runtime(
    text: str,
    type: str = "INFO",
    sensitivity: str = "PUBLIC",
) -> None:
    logger = st.session_state.get("raglog")
    if logger is not None:
        logger(text, type, sensitivity)
```

Log levels:

```text
INFO
  normal successful workflow
  first title request
  memory file created
  memory record saved

WARN
  user action cannot continue
  empty prompt
  empty manual response
  empty memory title

ERROR
  exception / failed save / file/SQLite problem
```

Do not log full prompt/output as PUBLIC.

---

## 12. Runtime Log rendering and styling

File:

```text
ragstream/app/ui_layout.py
```

Problem fixed:

The first log line was shifted right because HTML was rendered with an indented multiline f-string and CSS had `white-space: pre-wrap`.

Fix:

Render Runtime Log div in one line:

```python
st.markdown(
    f'<div class="textforge-log-box" style="{log_box_style}">{log_html}</div>',
    unsafe_allow_html=True,
)
```

Runtime Log style was changed from yellow to light green:

```css
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
```

Requirement:

* newest log line at top normal
* older lines below italic

Implemented in `render_textforge_gui_log()`:

```python
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
```

---

## 13. Runtime Log red flash

The user asked whether the Runtime Log box can temporarily become red for 5 seconds.

Answer:

Possible only if:

1. `ui_actions.py` sets a timestamp.
2. `ui_layout.py` reads timestamp and changes style.

`ui_actions.py` needs:

```python
import time
```

At the exact place where flashing should start:

```python
_log_runtime("Enter a memory title to create the first memory file.", "INFO", "PUBLIC")
st.session_state["runtime_log_flash_until"] = time.time() + 5
st.rerun()
```

`ui_layout.py` also needs:

```python
import time
```

Inside `render_textforge_gui_log()`:

```python
flash_active = time.time() < st.session_state.get("runtime_log_flash_until", 0)

if flash_active:
    log_box_style = (
        f"min-height:{height}px; max-height:{height}px;"
        "background-color:#FFE5E5; border-color:#FF9A9A;"
    )
else:
    log_box_style = f"min-height:{height}px; max-height:{height}px;"
```

Then final render:

```python
st.markdown(
    f'<div class="textforge-log-box" style="{log_box_style}">{log_html}</div>',
    unsafe_allow_html=True,
)
```

Important implementation note:

Setting only `runtime_log_flash_until` does not change color. `ui_layout.py` must also render based on it.

Also: Streamlit will not automatically repaint after exactly 5 seconds unless there is a rerun/refresh. Without auto-refresh, it returns to green on the next rerun.

---

## 14. User keywords parsing

Current parser separates user keywords by:

* comma
* newline

Current line in `ui_actions.py`:

```python
raw_items = str(text or "").replace("\n", ",").split(",")
```

User asked about semicolon input:

```text
Word1; Word2; Word3
```

Change to:

```python
raw_items = str(text or "").replace("\n", ",").replace(";", ",").split(",")
```

Then all of these work:

```text
Word1, Word2, Word3
Word1
Word2
Word3
Word1; Word2; Word3
```

---

## 15. `.ragmem` and `.ragmeta.json`

The system was tested with real generated files.

Observed successful behavior:

* separate files created for different memory histories
* correct file IDs
* correct filenames
* correct title
* correct record count
* stable record IDs
* tags synchronized into `.ragmeta.json`
* user keywords synchronized
* YAKE keywords generated and stored
* active project saved
* embedded files snapshot saved

Example tested memory histories:

```text
2026-04-28-17-54-Music_TEST_RAG.ragmem
2026-04-28-17-54-Music_TEST_RAG.ragmeta.json

2026-04-28-17-55-Music2.ragmem
2026-04-28-17-55-Music2.ragmeta.json

2026-04-28-18-12-MUSIC3.ragmem
2026-04-28-18-12-MUSIC3.ragmeta.json
```

Example `.ragmeta.json` worked correctly:

* `MUSIC3` had two records
* first record tag changed to `GOLD`
* second record stayed `Green`
* tag summary showed:

  * `GOLD: 1`
  * `Green: 1`
* user keyword `Schiff` was saved
* YAKE generated terms such as:

  * `HAydn`
  * `MOzart`
  * `Beethoven`
  * `Andreas Schiff`

This proved the memory-recording design is functioning.

---

## 16. `.ragmem` versus `.ragmeta.json` truth

Important observation from testing:

`.ragmem` is append-oriented and stores the original full record block at capture time.

`.ragmeta.json` is rewritten and contains the current editable metadata state.

Therefore:

* if a tag is changed later, `.ragmeta.json` reflects the latest tag
* SQLite reflects the latest tag
* `.ragmem` may still contain the original captured tag in the original appended block

This is acceptable for the current architecture, because:

* `.ragmem` is durable full history
* `.ragmeta.json` and SQLite are current metadata truth

This should be documented clearly in requirements.

---

## 17. SQLite behavior

SQLite database:

```text
data/memory/memory_index.sqlite3
```

Main behavior:

* one global SQLite file
* many memory histories can be indexed
* refresh is scoped to active `file_id`
* records are upserted by `(file_id, record_id)`

If the user changes a tag in an old record and then adds a new memory, the save cycle:

1. syncs GUI edits
2. updates `MemoryManager.records`
3. rewrites `.ragmeta.json`
4. refreshes SQLite for the active `file_id`

This means:

* no need to rebuild whole database
* old files are untouched
* active file rows are updated cleanly

---

## 18. Project snapshot per MemoryRecord

Important accepted rule:

Project is not only MemoryManager-level metadata.

Each MemoryRecord captures:

```text
active_project_name
embedded_files_snapshot
```

Reason:

Within one memory history, the user can change Active DB / Project dynamically.

Example:

```text
records 1–10    Project1
records 11–18   Project2
record 19       Project3
records 20–30   Project2 again
```

Therefore project context must be stored per MemoryRecord.

Testing showed this works: records saved `active_project_name = TEST1` and included the complete embedded file snapshot.

---

## 19. A2 demo memory removal

The old A2 memory demo logic must be removed.

Old behavior:

* `do_a2_promptshaper()` created a demo memory entry
* used `a2_memory_demo_entries`
* used `a2_memory_demo_counter`
* used keys like `a2_memory_tag_<id>`

Accepted new behavior:

* A2 should only run A2.
* Memory is only created through `Feed Memory Manually` for now.
* Memory box displays `MemoryManager.records`.
* Old demo structures are no longer source of truth.

In `ui_streamlit.py`, remove old session-state initialization for:

```text
a2_memory_demo_entries
a2_memory_demo_counter
```

unless needed temporarily during cleanup.

In `ui_layout.py`, replace `render_memory_demo()` with `render_memory_records()`.

---

## 20. Current known next documentation work

A requirement document was drafted:

```text
Requirements_Memory_Recording.md
```

It describes:

* MemoryManager
* MemoryRecord
* manual memory feed
* `.ragmem`
* `.ragmeta.json`
* SQLite
* GUI sync
* tags
* keywords
* project snapshot
* boundaries to ingestion/retrieval

Suggested file split for future requirements:

```text
Requirements_Document_Ingestion.md
Requirements_Memory_Recording.md
Requirements_Memory_Ingestion.md
Requirements_Memory_Retrieval.md
```

Reason:

The old `Requirements_Ingestion_Memory.md` is mostly about static document ingestion and should not contain the new memory-recording design.

---

## 21. Memory ingestion is separate

Not implemented in this chat.

Important accepted distinction:

Part currently completed:

```text
Memory recording
```

Later separate design:

```text
Memory ingestion
Memory retrieval
```

Memory ingestion is not simple document chunking.

Reasons:

* memory records are input/output pairs
* LLM responses can be very large
* responses may contain code, requirements, UML, explanations
* naive chunking may retrieve only half of a meaningful Q/A relation
* retrieving the whole pair may be too large
* generated requirements/code should not automatically pollute vector memory

Potential future direction:

* frame protocol for LLM outputs
* parse frames
* skip code
* skip requirements drafts unless promoted
* use LangChain/LangGraph/Langflow concepts if useful
* preserve deterministic SQLite retrieval by tags/user keywords

---

## 22. LLM response frame protocol idea

Accepted idea for later RAGstream-controlled LLM calls:

LLM responses should use explicit frames:

```text
BEGIN_FRAME type=explanation
...
END_FRAME

BEGIN_FRAME type=code language=python filename=xxx.py
...
END_FRAME

BEGIN_FRAME type=requirements_update filename=Requirements_Memory.md
...
END_FRAME

BEGIN_FRAME type=uml filename=UML_Memory.puml
...
END_FRAME
```

Memory recording stores the full response unchanged.

Memory ingestion later decides what frames to embed or discard.

Accepted basic future policy:

* code: store but do not embed
* generated requirements updates: store but do not automatically embed
* explanation: may embed
* unknown frame type: do not embed by default

---

## 23. File extension decision

The custom extension:

```text
.ragmem
```

was accepted as good.

Reason:

* domain-specific memory archive/state file
* not confused with `.txt`, `.md`, or `.json`
* application-specific
* readable enough as a concept

Sidecar:

```text
.ragmeta.json
```

is also accepted because it is real JSON metadata.

Final pattern:

```text
YYYY-MM-DD-HH-mm-TITLE.ragmem
YYYY-MM-DD-HH-mm-TITLE.ragmeta.json
```

---

## 24. Current implementation file changes summary

Core memory files:

```text
ragstream/memory/memory_record.py
ragstream/memory/memory_manager.py
ragstream/memory/memory_actions.py
```

App integration:

```text
ragstream/app/ui_streamlit.py
ragstream/app/ui_actions.py
ragstream/app/ui_layout.py
```

Dependency:

```text
requirements.txt
```

Logger files exist and should not be modified unless necessary:

```text
ragstream/textforge/TextForge.py
ragstream/textforge/TextSink.py
ragstream/textforge/GUISink.py
ragstream/textforge/FileSink.py
ragstream/textforge/CliSink.py
ragstream/textforge/RagLog.py
```

---

## 25. Current desired tag colors

Use these colors:

```python
TAG_COLORS: dict[str, str] = {
    "Gold": "#D4AF37",
    "Silver": "#C0C7D2",
    "Red": "#E0115F",
    "Green": "#00A86B",
    "Black": "#111111",
}
```

Important:

* The green must be `#00A86B`, not dark green.
* The dark green `#0D4C3C` was rejected because it can be confused with black.

---

## 26. Latest small pending code refinements

These are small fixes/updates discussed at the end:

1. Change tag catalog in `memory_manager.py`:

```python
self.tag_catalog: list[str] = ["Gold", "Silver", "Red", "Green", "Black"]
```

2. Make semicolon work for user keywords in `ui_actions.py`:

```python
raw_items = str(text or "").replace("\n", ",").replace(";", ",").split(",")
```

3. Use jade green in `ui_layout.py`:

```python
"Green": "#00A86B",
```

4. Keep title request log as INFO, not WARN:

```python
_log_runtime("Enter a memory title to create the first memory file.", "INFO", "PUBLIC")
```

5. If red flash is kept, remember it requires both:

```text
ui_actions.py
ui_layout.py
```

not only one file.

---

## 27. Final state judgment

The memory-recording subsystem is working very well.

Confirmed working:

* manual Prompt/Response capture
* first-title workflow
* `.ragmem` file creation
* `.ragmeta.json` file creation
* multiple memory histories
* stable file IDs
* stable record IDs
* record count
* tag synchronization
* user keyword synchronization
* YAKE keyword generation
* active project snapshot
* embedded files snapshot
* Runtime Log integration
* GUI memory display from MemoryManager records

This is now a real functioning memory-recording layer, not only a design discussion.
