# RAGstream – Task 1 to Task 4 (v1) with state transitions

Start (input)

* User submits a prompt (could be plain text, Markdown with headings, or JSON-like with labeled fields).
* Goal of Tasks 1–4: convert that prompt into a clean, deterministic set of retrieval-ready text pieces, with full traceability back to the original prompt.

State S0 (raw)

* Data: raw prompt string, no structure known yet.
* Constraints: no LLMs used yet; no retrieval yet.

---

# Task 1 – Format detect and header extraction

What Task 1 does

* Detect the prompt format: plain text vs Markdown vs JSON-like.
* If Markdown/JSON-like: extract top-level headers/labels and their bodies.
* If plain text: header list is empty; the entire prompt remains as a single, unlabeled body.

Rules

* Detection is purely syntactic:

  * Markdown: lines starting with one or more “# …” become headers; bodies are lines until the next header.
  * JSON-like: top-level keys (e.g., "TASK": "...") become headers; values are bodies.
  * Plain text: no headers found.
* Do not classify any header as meta or content yet. Task 1 only parses and lists.

Outputs (state S1)

* Header list H = [(header_name_i, body_i, span_i)], preserving original order and exact character spans.
* If plain text: H is empty and body_plain = full prompt.
* Trace data (metadata bridge start): record exact character start–end for each header/body region and for plain text.

---

# Task 2 – Must-header check and canonicalization (Agent 00 only for unmapped)

What Task 2 does

* Ensure we have canonical header roles and must-haves present without using heavy LLMs on full bodies.

Inputs

* From S1: header list H (or empty if plain).
* Canon set: {SYSTEM, TASK, CONTEXT, PURPOSE, USER_PROMPT, AUDIENCE, FORMAT, DEPTH}.
* Must-headers: at minimum {TASK}; SYSTEM is optional meta but can be filled when present.

Deterministic pass

* Normalize each header name: uppercase, replace non-letters with spaces, collapse spaces.
* Alias table maps common variants to canon names (examples):

  * SYSTEM: SYSTEM, SYSTEM ROLE, MODEL ROLE, ROLE
  * TASK: TASK, QUESTION, INSTRUCTION
  * CONTEXT: CONTEXT, BACKGROUND
  * PURPOSE: PURPOSE, GOAL
  * USER_PROMPT: USER PROMPT, PROMPT
  * AUDIENCE: AUDIENCE
  * FORMAT: FORMAT, OUTPUT FORMAT
  * DEPTH: DEPTH, DETAIL LEVEL
* Headers that don’t match any alias are UNMAPPED.

LLM pass (Agent 00, cheap, headers only)

* If must-headers are missing or any headers remain UNMAPPED:

  * Send only the list of header names (no bodies) plus the canon set to Agent 00 to suggest mappings.
  * If a header is still ambiguous after that, optionally include a tiny snippet (first 200–300 chars) of that header’s body for those few headers only.
  * Cache accepted mappings for future reuse.

Classification

* META whitelist: {SYSTEM, AUDIENCE, FORMAT, DEPTH}. These are never used for retrieval.
* CONTENT set: {TASK, CONTEXT, PURPOSE, USER_PROMPT}. These can be retrieval candidates.

TASK guarantee (fallbacks)

* If TASK exists → use it.
* Else if USER_PROMPT exists → set TASK := USER_PROMPT.
* Else if any CONTENT sections exist → set TASK := first CONTENT section; keep the rest as they are.
* Else (only META or nothing) → no retrieval segments downstream.

Outputs (state S2)

* Canonicalized header map: original_name → {canon_name or UNKNOWN}.
* Role flags per section: META vs CONTENT vs UNKNOWN.
* Must-header status (TASK present or set by fallback).
* Updated trace entries linking each canon section to its original span and name.
* If plain text in S1: create a single CONTENT section TASK with the entire prompt.

---

# Task 3 – Build the segment table and filter out meta

What Task 3 does

* Construct a concrete table of sections for downstream retrieval.
* Remove META; keep only CONTENT sections; hold truly unknowns aside.

Segment table fields (per row)

* id: sequential identifier (e.g., text1, text2, …).
* canon_type: one of {TASK, CONTEXT, PURPOSE, USER_PROMPT} or UNDECIDED.
* original_header: the original header string (if any).
* text: the exact section body text.
* weight: initial weight = 1.0 for all kept content (equal weighting in v1).
* span: character start–end (and line range if available) in the original prompt.
* kept_for_retrieval: yes/no (yes for TASK/CONTEXT/PURPOSE/USER_PROMPT; no for META; undecided bucket kept=false by default).
* source_note: reason codes like KEPT_CONTENT, DROPPED_META, UNDECIDED.

Rules

* Remove all META sections (SYSTEM, AUDIENCE, FORMAT, DEPTH and their aliases).
* Keep CONTENT sections: TASK, CONTEXT, PURPOSE, USER_PROMPT.
* UNDECIDED handling:

  * Default: exclude from retrieval (kept_for_retrieval = no).
  * Optional switch include_undecided=true will promote them to kept_for_retrieval with weight=1.0 and type=UNDECIDED.
* No weighting differences in v1: all kept content = 1.0.

Outputs (state S3)

* Segment table T with rows for each CONTENT section chosen for retrieval (equal weights).
* UNDECIDED list retained in the trace but excluded by default.
* Clear auditability: every kept/dropped section points back to its original span.

---

# Task 4 – Chunk to query pieces (ingestion-aligned)

What Task 4 does

* Convert each kept CONTENT section into one or more retrieval-ready pieces, aligned with ingestion rules.

Chunking rules

* If section length ≤ ingestion_chunk_size → keep as one piece.
* If section length > ingestion_chunk_size → split using exactly the same size and overlap as ingestion.
* Always respect the embedding model’s maximum input length as a hard ceiling; if a single piece exceeds the model limit, sub-split that piece further using the same overlap.
* No special treatment by type in v1 (democratic policy): TASK, CONTEXT, PURPOSE are all treated the same.

Query pieces table (per row)

* piece_id: unique id (e.g., text1_p0, text1_p1, …).
* parent_text_id: link to the segment table row (traceability).
* canon_type: TASK/CONTEXT/PURPOSE/USER_PROMPT (copied from parent).
* text_piece: the exact chunk text.
* weight: 1.0 (copied from parent in v1).
* parent_span and piece_span: ranges in the original prompt and within the parent text.
* retrieval_filters: empty by default in v1.
* kept_for_retrieval: yes (all pieces from kept content).

Outputs (state S4)

* Final list of retrieval-ready query pieces with 1-to-N mapping from content sections, aligned to ingestion chunking.
* Full traceability from each piece back to the original prompt region and header.

---

# Summary of states and invariants

S0 raw → Task 1 → S1 parsed

* We only identify format and collect headers/bodies with spans.

S1 parsed → Task 2 → S2 canonicalized

* We map headers to canon names, separate META vs CONTENT, guarantee TASK via fallback, and keep a mapping table. Agent 00 is called only for unmapped or missing must-headers (headers only; tiny snippet if needed). Caching on.

S2 canonicalized → Task 3 → S3 segments

* We build the segment table, drop META, keep CONTENT (TASK/CONTEXT/PURPOSE/USER_PROMPT), set all weights to 1.0, and park unknowns in UNDECIDED (excluded by default).

S3 segments → Task 4 → S4 query pieces

* We chunk each kept content section using the same size and overlap as ingestion (and the model’s max as a hard limit). The result is a set of retrieval-ready pieces with complete traceability.

Global notes (v1)

* No LLMs see section bodies in Tasks 1–3 except for the optional 200–300 char snippet for Agent 00 when a header remains ambiguous.
* No special weighting in v1; all kept content = 1.0.
* No special handling for code, errors, filenames in v1; everything kept as content is treated equally. If later needed, deterministic filters can be added without changing Tasks 1–4.
* Traceability is mandatory at every step (spans, ids, links). This enables transparency and debugging and protects against silent misclassification.
