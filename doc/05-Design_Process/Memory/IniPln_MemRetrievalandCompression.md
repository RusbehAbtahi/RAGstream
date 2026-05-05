# Memory Ingestion / Retrieval — Final Decision Report for New Chat

## 1. Current State

The uploaded file `Memory_Ingestion_REtriebval_RAG_ExpandedIDEAS.md` contains the strategic basis for memory design: recent-context lane, hard-rule lane, tag-governed important memory, semantic/graph memory, Red rules, Gold/Silver priority, MemorySegment, ContextPack, and future Knowledge Map/Wiki ideas. It correctly states that memory ingestion and memory retrieval must be designed together, because memory is not normal document chunking. 

However, that file does not yet contain our latest concrete implementation decisions. The final decisions below must be treated as the current working baseline for the next chat.

---

# 2. Core Principle

A `MemoryRecord` is the truth object.

It contains the full original Q/A:

* full user question
* full assistant answer
* `record_id`
* timestamp
* tag
* YAKE keywords
* user keywords
* active project snapshot
* source
* hashes
* parent/reference information

The full Q/A is never replaced by chunks, summaries, or compressed versions.

Compression and vectorization are only retrieval-support layers.

---

# 3. Final Memory Ingestion Decision

For each `MemoryRecord`, we create three vector families.

## 3.1 Record-handle vector

One compact vector for the whole record.

It is not created from the full 20k/30k Q/A.

It should be created from a compact searchable representation:

* main user intent
* short question anchor
* YAKE keywords
* user keywords
* tag
* project name
* possibly a generated/deterministic title later

Purpose:

Find candidate `MemoryRecords`.

Meaning:

“This memory record may be relevant.”

---

## 3.2 Question-block vectors

The question is chunked separately from the answer.

If the question is large, for example 5,000 tokens, it is split into semantic blocks / sentence-window blocks.

Each question block vector stores metadata:

* `record_id`
* `role = question`
* `block_id`
* position
* start/end offset
* token count
* tag
* project
* YAKE keywords
* user keywords

Purpose:

Detect when the current query resembles an older user problem.

Meaning:

“This current question is similar to an old question.”

---

## 3.3 Answer-block vectors

The answer is chunked separately from the question.

If the answer is large, for example 15,000 tokens, it is split into semantic blocks / sentence-window blocks.

Each answer block vector stores metadata:

* `record_id`
* `role = answer`
* `block_id`
* position
* start/end offset
* token count
* tag
* project
* YAKE keywords
* user keywords
* optional `frame_type`

Purpose:

Detect useful answer regions inside the old answer.

Meaning:

“This old answer contains useful knowledge.”

---

## 3.4 Important ingestion rule

Do not combine Q and A into one vector chunk.

Reason:

Question similarity and answer usefulness are different signals.

A new query may match:

* the old question,
* the old answer,
* or both.

Keeping them separate gives better control.

---

# 4. Metadata / Keyword Decision

YAKE keywords and user keywords must be stored and used.

They are not replacements for embeddings.

They are extra retrieval signals.

## YAKE keywords

Use for:

* metadata display
* keyword boosting
* sparse/FTS/BM25-style search
* debugging why something was selected

## User keywords

User keywords have higher authority than YAKE keywords.

If the user explicitly writes keywords, retrieval should treat them as stronger than automatically extracted keywords.

## Tags

Tags are already part of the deterministic governance layer.

For the first implementation of pure semantic memory retrieval, tags may be stored but not fully activated yet.

Later:

* Gold = high-priority candidate eligibility
* Silver = strong boost
* Green = normal
* Black = exclusion
* Red = hard-rule/procedural memory

---

# 5. Final Memory Retrieval Decision

Retrieval must search all three vector families:

1. record-handle vectors
2. question-block vectors
3. answer-block vectors

The result is not treated as “normal chunks.”

The result is evidence for reconstructing a reduced Q/A-shaped memory context.

---

## 5.1 If record-handle vector matches

Meaning:

The memory record is generally relevant.

Action:

Look inside the parent record and select the best question anchor and answer blocks.

---

## 5.2 If question-block vector matches

Meaning:

The current query resembles an old user problem.

Action:

Use the matching question block as the question anchor, then select answer blocks from the same `MemoryRecord`.

---

## 5.3 If answer-block vector matches

Meaning:

The old answer contains useful knowledge.

Action:

Use the answer block as core evidence, then attach the best question anchor from the same `MemoryRecord`.

---

## 5.4 If both question and answer blocks match

This is the strongest case.

Action:

Build a reduced Q/A pack from:

* best matching question block
* best matching answer block(s)
* neighbor blocks if needed
* parent `record_id`

---

# 6. Final Context Object

The memory retrieval output should become a `MemoryContextPack`.

It should contain:

* selected question anchor
* selected answer block(s)
* optional neighboring windows
* parent `MemoryRecord` reference
* score metadata
* token count
* reason/source metadata

This `MemoryContextPack` is then injected into the SuperPrompt memory section.

No A4-like memory condenser is required for this design.

---

# 7. Final Compression Decision

Large Q/A records must not be sent whole into the final prompt.

For huge records, we decided on two-stage compression.

## Stage 1: deterministic sentence/block preselection

Input example:

30,000-token Q/A

Process:

* retrieve relevant blocks/sentences
* expand with neighboring windows
* deduplicate
* keep original order
* enforce token budget

Output target:

6,000–8,000 tokens

This stage is local and deterministic.

No LLM.

---

## Stage 2: hosted cheap LLM compression

Input:

Only the reduced 6k–8k token extract, not the full 30k Q/A.

Model:

`gpt-5-nano`

Task:

Produce a compact reduced Q/A memory pack.

Output target:

1,000–3,000 tokens

This output becomes the final memory context for that large record.

---

# 8. Why This Compression Design Was Chosen

Pure deterministic reduction from 30k directly to 3k is possible, but risky.

It may lose bridge sentences and context.

Better decision:

30k → deterministic preselection to 6k–8k
then
6k–8k → `gpt-5-nano` compression to 1k–3k

This gives a better chance of preserving meaning while still keeping cost low.

---

# 9. Postponed / Rejected / Parallel Ideas

## 9.1 LongLLMLingua

Status: off the table for now.

Reason:

It needs local model execution through `torch`/`transformers`.

On the user’s CPU-only laptop, it may be too slow for large 8k-token compression.

It is not a good immediate implementation dependency.

---

## 9.2 Local LLM compressor

Status: postponed / not selected.

Reason:

The user does not have a GPU.

CPU-only local compression may be slow and operationally annoying.

Current selected path is hosted `gpt-5-nano`.

---

## 9.3 Full Q/A summarization directly with LLM

Status: possible but not selected as default.

Example:

Send full 20k or 30k Q/A to an LLM and ask for summary.

Reason not selected:

It is easy but wasteful.

The preferred design first reduces text deterministically, then sends only selected text to the cheap LLM.

---

## 9.4 A4-like condenser for memory

Status: not needed.

Reason:

Memory retrieval already produces reduced Q/A packs.

A4 remains part of the document RAG pipeline, but memory context does not need a separate A4-style condenser at this stage.

---

## 9.5 Knowledge Map / Graph / Wiki

Status: future direction, not part of immediate implementation.

The uploaded file correctly preserves this vision: Knowledge Map, graph relations, Wiki growth, GraphRAG-like ideas, and human-governed promotion. 

But immediate implementation should focus on:

* MemoryRecord ingestion
* vector families
* metadata/keywords
* retrieval
* reduced Q/A MemoryContextPack
* two-stage compression for huge records

Knowledge Map and Wiki come later.

---

# 10. Immediate Implementation Target

The next chat should focus on implementing:

## Memory ingestion

Create derived retrieval objects from existing `MemoryRecord`:

* record-handle vector
* question-block vectors
* answer-block vectors
* metadata rows
* parent links
* offsets
* keyword fields

## Memory retrieval

Search:

* record handles
* question blocks
* answer blocks

Then assemble:

* best question anchor
* best answer blocks/windows
* parent reference
* MemoryContextPack

## Large-record compression

If selected memory context is too large:

1. deterministic sentence/block preselection to 6k–8k tokens
2. `gpt-5-nano` prompt compression to 1k–3k tokens
3. use result as final MemoryContextPack

---

# 11. Final Baseline Sentence

The final design is:

MemoryRecord remains the truth.
Vectors are only retrieval handles.
Q and A are chunked separately.
Retrieval searches record-handle, question-block, and answer-block vectors.
The final output is a reduced Q/A-shaped MemoryContextPack.
Huge records use deterministic preselection plus `gpt-5-nano` compression.
LongLLMLingua and local compressor models are not part of the current implementation.
