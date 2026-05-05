# Memory Retrieval + Memory Compression — Agreed Design Notes

Status: working source-of-truth notes for the next implementation step.

Scope: this document captures the current agreed facts and design wishes for Memory Retrieval, Memory Compression, Direct Recall, tag behavior, semantic memory chunks, working memory, and HardRules. It is intentionally not a detailed implementation-requirements document.

Last updated: 04.05.2026

---

## 1. Current implemented memory foundation

Memory Recording and Memory Ingestion already exist as separate implemented layers.

Current MemoryRecord truth exists in:

- `.ragmem` durable memory file,
- `.ragmeta.json` sidecar metadata file,
- `memory_index.sqlite3` for fast deterministic lookup and indexing,
- memory vector stores for semantic lookup.

For every MemoryRecord, memory ingestion stores three semantic vector groups:

1. one meta / record-handle vector,
2. one or more question/input vectors,
3. one or more answer/output vectors.

The parent object is the full MemoryRecord. Chunk-level retrieval may find the best question, answer, or meta match, but the selected episodic object is normally the parent MemoryRecord.

---

## 2. Core retrieval principle

Automatic memory retrieval works only on the current active memory log.

Other histories do not influence the current chat automatically.

Other histories can enter only through Direct Recall Key, because Direct Recall Key is an explicit user command.

This keeps normal retrieval safe, local, and understandable.

---

## 3. Memory categories in the current design

The current design separates four context sources:

1. **Working memory** — the most recent non-Black Q/A pairs from the current chat.
2. **Episodic memory** — selected full MemoryRecords from the current memory log.
3. **Semantic memory chunks + document chunks** — best evidence chunks judged and condensed by A3/A4.
4. **HardRules** — deliberately authored procedural rules stored outside normal MemoryRecords.

This separation is now preferred over mixing all behaviors into memory tags.

---

## 4. Simplified memory tags

The memory tag system is simplified for this implementation.

Active memory tags:

- `Green` — normal memory, eligible for semantic retrieval with decay.
- `Gold` — rare high-authority episodic memory, direct priority within strict limits.
- `Black` — excluded from retrieval in practice.

Removed from the current memory-tag design:

- `Red`
- `Platin`
- `Silver`

Reason:

- Red mixed HardRules with episodic memory and created ambiguity.
- Platin and Silver increased complexity and weakened the role of semantic ranking and decay.
- HardRules deserve their own deliberate subsystem.

Black is not physical deletion. The record remains in `.ragmem`, `.ragmeta.json`, SQLite, and vector stores, but it is not injected into context.

---

## 5. Retrieval source mode: Q / A / Q+A

Each MemoryRecord should have a separate retrieval-source metadata field.

Preferred field:

```text
retrieval_source_mode = "Q" | "A" | "QA"
```

Meaning:

- `Q` — use only the question/input side.
- `A` — use only the answer/output side.
- `QA` — use both question and answer; default mode.

This is not a tag and must not be encoded as a tag prefix.

GUI wish:

- Add a small popup/selectbox below the memory tag selector.
- Values shown to user: `Q`, `A`, `Q+A`.
- Default: `Q+A`.

This controls which part of the MemoryRecord participates in retrieval and compression.

---

## 6. Lane 1 — Direct Recall Key

Direct Recall Key is the only retrieval lane that can search across all histories, including the current log.

Direct Recall Key behavior:

- Max one Direct Recall Key per run.
- Lookup is deterministic through `memory_index.sqlite3`.
- Limit is 3000 tokens, no matter which memory it retrieves.
- It respects `retrieval_source_mode` (`Q`, `A`, `Q+A`).
- If the matched record is Black, it is not injected.

Direct Recall Key metadata belongs to Memory Recording.

GUI wish:

- Each key has a name.
- Each key may have a short explanation, around 500 characters.
- Key name and explanation are stored in SQLite.
- User can later review and reuse available Direct Recall Keys.

Direct Recall Key is an explicit user command, not automatic retrieval.

---

## 7. Lane 2 — Working memory / recent conversation

Working memory takes the most recent non-Black conversation pairs from the current chat.

Current default:

- take the latest two Q/A pairs if they are not Black.
- total working-memory budget: 4000 tokens.

Budget rule:

- latest Q/A pair may use up to 3000 tokens,
- second-latest Q/A pair normally uses up to 1000 tokens,
- if the latest pair is small, the second-latest pair may use up to 1500 tokens,
- the 4000-token total should only be reached when the latest pair is large.

Working memory is short-term context, not retrieved long-term episodic memory.

---

## 8. Lane 3 — Episodic MemoryRecord retrieval

Episodic retrieval selects full MemoryRecords from the current active memory log.

Current tag behavior:

- one effective Gold is allowed,
- Green records form the main democratic semantic pool,
- Black records are excluded.

Gold behavior:

- User may mark several records as Gold.
- Only the most recent Gold is effective as Gold in automatic retrieval.
- Effective Gold is directly selected.
- Gold compression limit: 3000 tokens.

Green behavior:

- If one effective Gold exists: select 2 Green MemoryRecords.
- If no effective Gold exists: select 3 Green MemoryRecords.
- Each selected Green record has an upper limit of 1500 tokens.
- Green selection is based on semantic relevance and temporal decay.

Episodic budget:

- maximum intended episodic budget: 6000 tokens.
- standard expected usage is usually lower.

This keeps episodic memory strong but prevents it from dominating the context pack.

---

## 9. Parent-level scoring for episodic retrieval

Each MemoryRecord has:

- one meta vector,
- question/input vectors,
- answer/output vectors.

Scoring idea:

- take the best answer-chunk score,
- take the best question-chunk score,
- take the single meta-vector score,
- combine them with weights.

Preferred importance order:

```text
Answer > Question > Meta
```

`retrieval_source_mode` controls which textual side is active:

- `Q` can suppress answer-side contribution,
- `A` can suppress question-side contribution,
- `QA` keeps both sides active.

Exact weights and decay formula remain open for implementation.

---

## 10. Lane 4 — Semantic memory chunks + document chunks

Semantic memory chunk retrieval is separate from episodic parent retrieval.

Design wish:

- select the best memory chunks independently,
- current working assumption: best 10 memory chunks,
- place memory chunks beside document chunks as evidence candidates,
- preserve metadata such as `source_type = memory_chunk | document_chunk`.

Downstream behavior:

- A3 judges usefulness across memory chunks and document chunks together.
- A4 condenses the useful evidence together.
- The final context receives only the A4 condensed output.
- Raw memory/document chunks are not injected into the final prompt as final context.

Combined semantic/document condensed budget:

- maximum 5000 tokens.

This means no separate semantic-memory downstream pipeline is needed now. Memory chunks and document chunks share the same A3/A4 evidence path.

---

## 11. HardRules subsystem

Red tag is removed from Memory Management.

HardRules become a separate procedural subsystem.

Reason:

HardRules are too important to be created casually from spontaneous Q/A memory. A normal Q/A record may be useful, but it is not necessarily precise enough to become a system-level rule.

Design wish:

- user writes HardRules deliberately in a dedicated GUI field,
- each HardRule may have title, tag/category, and description,
- HardRules are stored in a dedicated SQLite table,
- HardRules are visible to the user,
- user selects them intentionally before use,
- user may select many rules,
- final injected HardRules block is deterministically capped.

HardRules budget:

- maximum 3000 tokens.

Future agent support may merge selected HardRules or check them for contradiction, but this is not required for the first implementation.

---

## 12. Total context budget wish

Current maximum context-pack ceiling for these four sources:

| Context source | Maximum budget |
|---|---:|
| Working memory | 4000 tokens |
| Episodic memory | 6000 tokens |
| Semantic memory chunks + document chunks | 5000 tokens |
| HardRules | 3000 tokens |
| **Total ceiling** | **18000 tokens** |

This is a ceiling, not a target that must always be filled.

Standard expected usage is usually lower, around 8000–12000 tokens.

Heavy but acceptable usage is around 12000–18000 tokens.

Above 18000 tokens should be manual/debug mode only.

---

## 13. Configuration wish

The numeric limits should not be hard-coded permanently.

Design wish:

- store token budgets and retrieval limits in a global JSON configuration,
- load defaults at startup,
- allow future model-specific profiles,
- allow a GUI settings page later,
- keep safe defaults for normal users.

Example profile idea:

- standard GPT-5-class model profile,
- small/limited-model profile,
- high-context experimental profile.

This allows the same design to adapt to stronger or weaker LLMs without changing code.

---

## 14. User-facing simplicity wish

The internal system is advanced, but the user-facing GUI should remain simple.

For this implementation:

- show tag selection simply: `Green`, `Gold`, `Black`,
- show retrieval-source popup simply: `Q`, `A`, `Q+A`,
- keep Direct Recall Key as an optional advanced feature,
- keep HardRules separate and explicit,
- avoid exposing too many ranking/decay/token settings to normal users.

Advanced controls can later live in an expert/settings area.

Marketing direction:

- present the tool as controlled memory, not as a complicated tagging system,
- show that important answers can be remembered, recalled, and compressed intelligently,
- show Direct Recall and Gold as power features, not mandatory workflow.

---

## 15. Current open items for implementation

Still open:

- exact Answer / Question / Meta scoring weights,
- exact Green temporal decay formula,
- exact memory compression prompts,
- exact global JSON schema for budgets and profiles,
- exact HardRules table schema,
- exact Direct Recall Key GUI layout,
- exact A3/A4 formatting for mixed memory/document chunks,
- evaluation / benchmarking.

Not open anymore for the current implementation:

- Red tag is removed from Memory Management.
- Platin is removed from Memory Management.
- Silver is removed from Memory Management.
- Q/A/Q+A is metadata, not a tag.
- HardRules are separate from MemoryRecords.
