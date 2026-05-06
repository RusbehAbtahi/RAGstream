````markdown
# Requirement — Active Retrieval Brief per MemoryRecord

Last update: 05.05.2026

## 1. Purpose

This requirement defines the future `ActiveRetrievalBrief` function inside the Memory subsystem.

The goal is to keep a compact, query-independent working-context brief that helps later retrieval stages when the latest user message is weak, short, corrective, emotional, or context-dependent.

Example weak user message:

```text
No, only IaC.
````

By itself, this message is too weak for document retrieval.
With an `ActiveRetrievalBrief`, retrieval can still use the current meaningful work context.

---

## 2. Core idea

Each `MemoryRecord` shall have its own immutable cumulative brief:

```text
MemoryRecord_1 → ActiveRetrievalBrief_1
MemoryRecord_2 → ActiveRetrievalBrief_2
MemoryRecord_3 → ActiveRetrievalBrief_3
...
```

The brief represents the conversation/work context from the beginning of the active memory history up to that MemoryRecord.

It is not one global mutable object.

Normally, RAGstream uses the latest clean non-Black `ActiveRetrievalBrief`.

---

## 3. Query independence

`ActiveRetrievalBrief` must be query-independent.

It is not written as an answer to the current user query.

It is a compact description of the current working context, including:

```text
current project/topic
current task direction
important scope constraints
accepted corrections
rejected interpretations
stable user intent
important technical entities
```

---

## 4. Storage model

`ActiveRetrievalBrief` is generated once for a MemoryRecord and then remains stable.

Therefore it may belong to the stable MemoryRecord body.

Future MemoryRecord fields:

```text
qa_summary
active_retrieval_brief
active_retrieval_brief_contributor_ids
```

Because it is not GUI-editable metadata, it is not treated like:

```text
tag
retrieval_source_mode
direct_recall_key
user_keywords
```

---

## 5. First record behavior

For the first accepted MemoryRecord in a history:

```text
Q/A_1
→ LLM creates qa_summary_1
→ LLM creates active_retrieval_brief_1
→ store both with MemoryRecord_1
```

---

## 6. Later record behavior

For every later accepted MemoryRecord:

```text
previous clean ActiveRetrievalBrief
+ new Q/A summary
→ LLM updates cumulative ActiveRetrievalBrief_N
→ store with MemoryRecord_N
```

The updater must not use fixed numeric weighting such as 50/50 or 70/30.

Instead, it shall use semantic rules.

---

## 7. LLM updater rules

The ActiveRetrievalBrief updater must:

```text
1. Preserve stable project/task context.
2. Add only durable new information from the latest Q/A.
3. Treat corrections as high-importance scope constraints.
4. Treat insults, frustration, "no", "worse", "not good" as feedback signals, not as new topic content.
5. Remove or weaken interpretations that the user explicitly rejected.
6. Keep the brief query-independent.
7. Keep the brief compact, target 500–700 tokens.
8. Output contributor_record_ids.
```

---

## 8. Black-record handling

If a MemoryRecord is later marked Black, its effect may already exist inside later briefs.

To handle this, every `ActiveRetrievalBrief` must store:

```text
active_retrieval_brief_contributor_ids
```

Runtime selection rule:

```text
Use the latest ActiveRetrievalBrief whose contributor_record_ids contain no Black record.
```

Later advanced behavior may rebuild briefs from the last clean point.

---

## 9. Retrieval usage

Document Retrieval may later build its query from:

```text
TASK
+ PURPOSE
+ CONTEXT
+ latest clean ActiveRetrievalBrief
```

Memory Retrieval may also later use the same brief as optional query support.

The brief is retrieval support context, not final prompt context.

---

## 10. Relation to future MemoryMerge

This function belongs to the future MemoryMerge / Memory Compression stage.

MemoryMerge will handle:

```text
episodic memory compression
working memory compression
Direct Recall handling
ActiveRetrievalBrief generation/update
final memory context preparation
```

This requirement only preserves the design decision for `ActiveRetrievalBrief`.

```
```
