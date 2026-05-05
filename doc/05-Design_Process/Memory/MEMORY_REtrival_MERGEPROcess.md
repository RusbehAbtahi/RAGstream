````markdown
## Pipeline wiring update — Memory Retrieval / MemoryMerge

### 1. Retrieval button behavior

For the current implementation, Memory Retrieval should be triggered together with the normal Document Retrieval when the user presses the existing `Retrieval` button.

This follows the same development/debug logic as document retrieval:

- Document Retrieval currently places many candidate chunks into the `SuperPrompt` object and GUI for inspection.
- These are not final prompt context yet.
- Later stages select, judge, rerank, condense, or merge them.

Memory Retrieval should behave the same way.

Pressing `Retrieval` should populate the `SuperPrompt` object with a structured memory candidate pool, for example:

- working-memory candidates,
- episodic MemoryRecord candidates,
- semantic memory chunk candidates,
- Direct Recall candidate, if a Direct Recall Key was provided.

These candidates should also be visible in the SuperPrompt GUI for inspection.

At this stage, the memory candidates are not yet the final compressed memory context.

---

### 2. Candidate-pool logic

Memory Retrieval may collect more memory candidates than will finally be injected.

For inspection/debugging, it is acceptable to store and display:

- latest two non-Black Q/A pairs as working-memory candidates,
- effective Gold candidate,
- selected Green episodic candidates,
- possibly more episodic candidates than the final MemoryMerge will use,
- top semantic memory chunks,
- Direct Recall candidate, if active.

The final token-limited memory context is produced later.

---

### 3. Semantic memory chunks

Semantic memory chunks follow the document-evidence path.

The intended downstream flow is:

```text
semantic memory chunks + document chunks
→ A3 NLI Gate
→ A4 Condenser
→ condensed retrieved evidence context
````

Current working balance:

```text
5 memory chunks + 25 document chunks = 30 A3 candidates
```

A3 judges usefulness across both memory chunks and document chunks.

A4 condenses the useful selected evidence into `S_CTX_MD`.

---

### 4. Working memory, episodic memory, and Direct Recall

Working memory, episodic MemoryRecords, and Direct Recall are not handled by A3/A4 in the current design.

They follow a separate memory-merge path.

The intended downstream flow is:

```text
working memory candidates
+ episodic MemoryRecord candidates
+ Direct Recall candidate
→ MemoryMerge
→ compressed / trimmed / formatted memory context
→ SuperPrompt memory context section
```

---

### 5. Rename A5 button for current implementation

For the current implementation phase, the existing `A5 Format Enforcer` button should be repurposed and renamed to:

```text
MemoryMerge
```

Its current role should be:

* take the memory candidates already stored in `SuperPrompt`,
* apply the configured token limits,
* compress / trim / format them,
* write the final memory context block back into the `SuperPrompt`.

A5 Format Enforcer remains postponed.

---

### 6. Future Prompt Builder behavior

Later, when Prompt Builder becomes the full automatic composer, it should run this sequence automatically:

```text
Document Retrieval
+ Memory Retrieval
+ A3/A4 semantic evidence condensation
+ MemoryMerge
+ future HardRules / direct fetchers
+ final deterministic prompt assembly
```

For now, manual buttons remain useful because they expose the candidate pools and intermediate context blocks for inspection.

```
```
