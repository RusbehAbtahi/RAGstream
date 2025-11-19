````markdown
# RAGstream — Supplementary Requirements Pack #2
**Topics:** JSON Governance (agents + memory), Human-in-the-Loop Escalation, **A0 FileScopeSelector**, **A5 Schema/Format Enforcer**  
*Version 0.1 • 2025-09-07*  
*Status: Supplementary (to be merged into main Requirements.md later).*

---

## 0) Scope & Compatibility

- These requirements refine the already-approved design (Requirements v2.3) by:
  1) Mandating **JSON-only internal communication** between components/agents.  
  2) Converting **ConversationMemory (Layer-G/E)** storage/exchange to **structured JSON**, while keeping Layer-E embeddings **selection-only** and separate from document vectors.  
  3) Adding **Human-in-the-Loop escalation** metadata to all agent outputs.  
  4) Introducing **A0 FileScopeSelector** (deterministic pre-filter for the Eligibility Pool).  
  5) Introducing **A5 Schema/Format Enforcer** (contract checker with one bounded self-repair).
- No changes to A1–A4 interfaces are required at the code boundary; JSON envelopes formalize their I/O without altering roles.
- Back-compat note (memory): when merged, JSON persistence supersedes any plain-text log; if both exist, JSON is canonical.

---

## 1) JSON Governance (Agents & Controller)

**Goal.** Every internal handoff is a **structured JSON object** with provenance and purpose.

### SR2-JSON-01 (Envelope Required) — **Must**
All agents/controllers MUST produce/consume a JSON **Envelope**:

```json
{
  "agent": "A2_PromptShaper",
  "goal": "propose_headers",                  // required in every object
  "timestamp": "2025-09-07T12:34:56Z",
  "request_id": "r-20250907-123456-001",
  "turn_id": 42,
  "source": "internal",                       // internal | external | file
  "version": "1.0",
  "escalate": false,                          // default false; set true with reason if needed
  "reason": null,
  "provenance": {
    "files": [{"path": "docs/Req.md", "sha256": "...", "mtime": 1694000000}],
    "history_refs": [{"id": "E:12345", "score": 0.82}],
    "eligibility": ["docs/Req.md", "notes/NVH.md"]
  },
  "payload": { /* agent-specific structured data */ }
}
````

### SR2-JSON-02 (Determinism) — **Must**

* Envelope keys are stable; agent-specific `payload` schemas are documented; float scores use fixed precision.
* No free-text handoffs; prose lives inside typed fields in `payload`.

### SR2-JSON-03 (Provenance & Hashing) — **Must**

* Any referenced file or history item MUST include verifiable identifiers (path+hash for files; id/hash for history).
* Controller may compute and attach a **content hash** of the outgoing `payload` for traceability.

### SR2-JSON-04 (Transport & Storage) — **Must**

* JSON flows are in-process (no network). For debugging, the **Debug Logger** may write envelopes to disk (trace/vars), but envelopes themselves remain the system of record for inter-agent data.

### SR2-JSON-05 (Validation) — **Must**

* Controller validates required envelope fields before dispatch; on missing/invalid fields, set `escalate=true` with reason and halt.

---

## 2) JSON-based ConversationMemory (Layer-G & Layer-E)

**Goal.** Persist and exchange memory as **structured JSON**, keep Layer-E embeddings **selection-only**, and maintain determinism.

### SR2-CM-01 (Stores) — **Must**

* **G-store (recency):** `PATHS.logs/conversation.jsonl` (append-only JSONL).
  Each line is a `MemoryTurn`:

  ```json
  { "role": "user|assistant|external",
    "text": "...",
    "timestamp": "2025-09-07T12:00:01Z",
    "goal": "store_recency_turn",
    "provenance": { "source": "user|assistant|external", "hash": "...", "file_refs": [] }
  }
  ```
* **E-index (episodic embeddings):** `PATHS.logs/history_store.pkl` (NumPy snapshot) + `history_index_meta.json` (JSON metadata with store generation, vector count, caps).

### SR2-CM-02 (Read Paths) — **Must**

* On each prompt:
  **G:** read last *k* turns from the JSONL tail.
  **E:** read the latest published `.pkl` snapshot and select candidates **only** (never inject E text).

### SR2-CM-03 (Guardrails) — **Must**

* Enforce existing guardrails: capacity caps, token budgets, soft fading, synonym aliasing, **❖FILES > newer > older**, and “ignore E items tied to files that are OFF in Eligibility unless the file is explicitly injected via ❖FILES”.

### SR2-CM-04 (Write Discipline) — **Must**

* After each completed turn (including UI-08/09 external replies), append the `MemoryTurn` JSON to JSONL and **fsync**.
* Async pipeline: embed only **new** tail chunks; write to `history_store_dynamic.pkl` then **atomic swap** to publish `history_store.pkl`.

### SR2-CM-05 (Validation & Recovery) — **Must**

* On JSON parse/validation failure: set `escalate=true`, include reason with line offset; continue with previous valid snapshot.

---

## 3) Human-in-the-Loop Escalation

### SR2-HIL-01 (Trigger) — **Must**

* Any agent that cannot proceed deterministically MUST set `"escalate": true` and add a short `"reason"` (e.g., `"schema_violation"`, `"insufficient_context"`, `"validation_fail"`).

### SR2-HIL-02 (Controller Behavior) — **Must**

* When receiving an envelope with `escalate=true`, the controller stops the pipeline, surfaces the reason in UI, and waits for user action; **no** uncontrolled retries.

### SR2-HIL-03 (UI) — **Must**

* UI shows a clear escalation panel with: reason, offending agent, `request_id`, suggested next steps (retry, adjust eligibility, inject ❖FILES).

---

## 4) A0 — FileScopeSelector (Deterministic Pre-Filter)

**Goal.** Produce the minimal, explainable Eligibility Pool before A1/A2.

### SR2-A0-01 (Inputs) — **Must**

* Prompt text; FileManifest (path, sha256/MD5, mtime, tags); UI toggles (ON/OFF per file, ❖FILES lock); optional include/exclude lists; static alias map (e.g., NVH ⇄ vehicle acoustics).

### SR2-A0-02 (Rules) — **Must**

1. **OFF** files are never eligible; never override ❖FILES lock.
2. **Hard include** list wins; **hard exclude** removes regardless.
3. Match priority: **title/regex > tag > alias list** (no embeddings).
4. Ties: priority tags → **mtime** (newer first) → **path** (A-Z).
5. Enforce **max N**; if exceeded, truncate with recorded reason.
6. No network / LLM; decisions are explainable from manifest.
7. Emit per-file **reason trace**.

### SR2-A0-03 (Outputs) — **Must**

Envelope `payload` schema:

```json
{
  "eligible_files": [
    {"path": "docs/Req.md", "reason": ["KEPT:title-regex"], "sha256": "...", "mtime": 1694000000}
  ],
  "candidate_files_block": { "files": ["docs/Req.md", "notes/NVH.md"] },
  "trace": [
    {"path": "legacy/old.md", "decision": "DROPPED", "reason": ["DROPPED:OFF"]}
  ]
}
```

### SR2-A0-04 (Failure) — **Must**

* If zero files and no ❖FILES lock → return `EMPTY_ELIGIBILITY`.
* If ❖FILES lock refers to a missing file → `LOCK_MISS` and `escalate=true`.

---

## 5) A5 — Schema/Format Enforcer (Contract + Single Self-Repair)

**Goal.** Ensure generated artifacts comply with a pinned **CodeSpec.md**; allow exactly one bounded repair.

### SR2-A5-01 (Inputs) — **Must**

* Draft artifact; **CodeSpec.md** (versioned, hashed); task metadata (language/runtime/allowed libs); stop conditions (single file, filename, no prose).

### SR2-A5-02 (Checks) — **Must**

1. Structure order (header → docstring → methods) and required logging/docstring presence.
2. Naming + imports (allowlist/denylist); forbidden calls (hidden I/O, network, time) if disallowed.
3. Output shape: **single fenced code block**, fixed filename, no extra prose.
4. Pinned formatter/linter (style only), whitespace normalization.

### SR2-A5-03 (Self-Repair) — **Must**

* On hard violation: produce a **violation list** and attempt **one** self-repair at `temp=0` using only {violation list + CodeSpec excerpts + original prompt}.
* Re-validate once; if still failing → return FAIL with violation report; set `escalate=true`.

### SR2-A5-04 (Outputs) — **Must**

Envelope `payload` schema:

````json
{
  "status": "PASS|FAIL",
  "violations": [
    {"rule": "no_extra_prose", "evidence": "…", "suggestion": "remove trailing text"}
  ],
  "artifact": {"filename": "main.py", "code_fenced": "```python\n...\n```"},
  "hashes": {"spec_sha256": "...", "draft_sha256": "...", "final_sha256": "..."}
}
````

---

## 6) JSON Schemas (Reference)

> **Note:** These are illustrative; when merging, place the canonical JSON Schemas under `/schemas/` and version them.

* **Envelope (common):** required fields = `agent`, `goal`, `timestamp`, `request_id`, `turn_id`, `source`, `version`, `provenance`, `payload`; optional `escalate`, `reason`.
* **MemoryTurn (JSONL):** required `role`, `text`, `timestamp`, `goal`, `provenance`.
* **A0 payload:** required `eligible_files[]`, `trace[]`; optional `candidate_files_block`.
* **A5 payload:** required `status`, `violations[]`; optional `artifact`, `hashes`.

---

## 7) Acceptance Criteria

1. **JSON-only Handoffs**

   * All internal calls exchange valid envelopes; any missing required field yields `escalate=true` and a UI stop.

2. **Memory Persistence**

   * After each turn, a `MemoryTurn` line is appended to `conversation.jsonl` and fsynced.
   * On restart, Layer-G rebuilds from JSONL tail; Layer-E loads from the latest snapshot; prompt path never blocks on embedding.

3. **A0 Determinism**

   * Given mixed files and toggles, A0 returns the same ordered list and identical reason traces for identical inputs.

4. **A5 Contract**

   * For non-compliant drafts, one self-repair is attempted and re-validated; final output is either PASS or FAIL with explicit violations.

5. **Escalation**

   * Any envelope may set `escalate=true`; controller stops and UI displays reason and context; no uncontrolled retries.

---

## 8) Non-Goals / Deferred

* **Agent Cards**, **reasoning\_budget**, and **CoT rubric** are **deferred**; not part of this pack.
* No multi-agent recursion or autonomous planning added.

---

## 9) Merge Notes (when integrating into main Requirements.md)

* Replace any plain-text memory log reference with **JSONL** as canonical.
* Add references to the **Envelope** schema in A1–A4 sections (I/O description only; no interface rename).
* Insert A0 before A1/A2 in the orchestration narrative; insert A5 after A4 as a post-artifact check.
* Keep **Layer-E** selection-only and separate from document vectors; ❖FILES authority unchanged.

```
```
