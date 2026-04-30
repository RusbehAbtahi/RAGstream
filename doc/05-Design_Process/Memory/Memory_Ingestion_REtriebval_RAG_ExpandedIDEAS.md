# Basis for Memory Ingestion and Retrieval

Your vision is fundamentally correct. The main adjustment is this:

Memory ingestion and memory retrieval must be designed as one system, not as two independent modules.

For documents, your current model can work with relatively uniform chunks. For memory, it cannot. Memory has different authority levels, different time behavior, Q/A pair integrity, tags, hard rules, user corrections, and future graph relations.

So the future memory system should have four retrieval lanes:

| Lane                    | Purpose                           | Retrieval style                    |
| ----------------------- | --------------------------------- | ---------------------------------- |
| Live Recent Context     | keep the chat “alive”             | deterministic recent turns         |
| Hard Rules              | enforce user-declared rules       | deterministic injection            |
| Tagged Important Memory | never lose important old material | tag-governed candidate selection   |
| Semantic / Graph Memory | retrieve relevant older knowledge | hybrid retrieval + graph expansion |

This is the basis.

---

# I. Audit of Your Vision

## 1. “Chat should be alive”

Your idea is correct.

The most recent conversation should not depend only on embedding retrieval. Recent context is special. It should be loaded directly unless excluded by tag.

This matches mainstream memory thinking: short-term memory is normally thread-scoped conversation state, while long-term memory is stored and recalled across sessions. LangChain/LangGraph memory docs make the same distinction between short-term thread memory and long-term memory across namespaces. ([docs.langchain.com][1])

For RAGstream, this means:

Recent turns are not “retrieved.”
They are fetched deterministically.

Suggested rule:

| Tag    | Recent-context behavior                    |
| ------ | ------------------------------------------ |
| Black  | never include                              |
| Green  | include if recent and budget allows        |
| Silver | include with higher priority               |
| Gold   | include or strongly consider even if older |
| Red    | not normal memory; goes to hard-rule lane  |

So your idea “if not BLACK, recent conversation comes directly” is good.

But I would not include too many raw recent Q/A pairs. The recent lane should have a small budget, because long contexts are not always used reliably by LLMs. The “Lost in the Middle” paper showed that models often use information best when it appears near the beginning or end of the context and can perform worse when relevant information is buried in the middle. ([MIT Press Direct][2])

So the principle is:

recent context must be direct, but compact.

---

## 2. “Silver 5 chats ago beats Green 3 chats ago”

Correct.

This should be a deterministic priority model, not pure vector retrieval.

Mainstream support exists for this idea. The Generative Agents paper used memory retrieval based on relevance, recency, and importance; memories were not selected only by semantic similarity. ([Google Forschungszentrum][3])

For RAGstream, the ranking dimensions should be:

| Dimension          | Meaning                                             |
| ------------------ | --------------------------------------------------- |
| recency            | how close the Q/A is to the current turn            |
| tag priority       | Gold/Silver/Green/Black/Red                         |
| semantic relevance | embedding / SPLADE / keyword similarity             |
| user keywords      | user-declared high-authority hints                  |
| project match      | active project and embedded-file snapshot           |
| graph relation     | connected concepts or decisions                     |
| source type        | manual memory, tool result, LLM response, hard rule |

So yes: Silver five turns ago can beat Green three turns ago.

That is not a bug. That is exactly what a serious memory ranking system should do.

---

## 3. “Memory doesn’t forget”

Correct, but this needs two separate mechanisms.

There are two different meanings of “doesn’t forget”:

| Meaning                   | Mechanism                               |
| ------------------------- | --------------------------------------- |
| It remains stored forever | `.ragmem`, `.ragmeta.json`, SQLite      |
| It is visible when needed | deterministic tag/rule/retrieval policy |

Your memory-recording design already solves the first part: `.ragmem` stores durable full records, `.ragmeta.json` stores current lightweight metadata, and SQLite is the searchable metadata index. 

The second part needs memory retrieval rules.

Gold/Silver should not only increase vector score. They should affect eligibility.

Suggested rule:

| Tag    | Retrieval role                                 |
| ------ | ---------------------------------------------- |
| Gold   | always enters the high-priority candidate pool |
| Silver | enters candidate pool with strong boost        |
| Green  | normal candidate                               |
| Black  | excluded                                       |
| Red    | hard-rule lane, not normal semantic retrieval  |

Your idea of limiting Gold is also correct. If everything is Gold, Gold loses meaning. The limit should not only be “max 3 Gold per chat,” but more generally:

Gold must be scarce at context-assembly time.

Better rule:

| Limit type                          | Purpose                                 |
| ----------------------------------- | --------------------------------------- |
| max Gold injected into one prompt   | prevents context pollution              |
| max Gold per memory history/session | prevents user from over-marking         |
| Gold review list in GUI             | lets user downgrade old Gold            |
| Gold conflict check                 | avoids injecting contradictory old Gold |

So your idea is good, but I would formulate it as a context budget rule, not only as a storage rule.

---

## 4. RED as hard rule

Your idea is strong, but Red must be defined very clearly.

I agree with this interpretation:

Red is not “important memory.”
Red is a hard rule / constraint / prohibition / instruction.

And yes: in that case, the LLM answer part can be ignored.

For Red records, the important content is usually the user’s input, not the assistant’s output.

So Red should be extracted into a separate Procedural Rule Store.

Example meaning:

| Record part      | RED behavior                               |
| ---------------- | ------------------------------------------ |
| user input       | authority source                           |
| assistant output | ignored or stored only for audit           |
| retrieval        | deterministic, not semantic                |
| context location | hard rules / system constraints section    |
| GUI control      | checkbox to activate/deactivate rule group |

This matches the mainstream distinction between semantic memory, episodic memory, and procedural memory. LangChain’s memory docs explicitly use this distinction: semantic memory for facts, episodic memory for experiences, and procedural memory for rules/instructions. ([docs.langchain.com][1])

So Red should become procedural memory.

This is a very good design direction.

---

# II. Part 3: Structure, Keywords, Summaries, Connections

Your part 3 is the real research/design layer.

You want memory to build structure:

* keywords
* summaries
* connections
* parent/child
* contradictions
* overlap
* support
* concept maps
* knowledge maps

This is not fantasy. This is exactly where the field is moving.

Microsoft GraphRAG combines text extraction, network analysis, LLM prompting, and summarization to understand large private text datasets through graphs instead of flat retrieval. ([Microsoft][4])

LlamaIndex’s property graph model defines a property graph as labeled nodes with metadata, connected by relationships into structured paths. ([LlamaIndex OSS Documentation][5])

Zep/Graphiti goes even closer to your memory idea: it builds temporal knowledge graphs for agent memory, tracks changing relationships over time, stores episodic data, supports semantic + keyword + graph search, and maintains provenance. ([Zep Hilfe][6])

So the professional name of your vision is:

relationship-aware memory retrieval with temporal knowledge graph support.

For RAGstream, the structure should develop in levels.

---

## Level 1: Cheap deterministic structure

This comes first.

No expensive LLM summary is required.

Use:

* tag
* user keywords
* YAKE keywords
* active project name
* embedded file snapshot
* created_at
* source type
* input/output hash
* parent_id
* detected frame types
* language markers for code
* maybe file/function names if detected cheaply

Your current MemoryRecord already stores input/output, tag, YAKE auto-keywords, user keywords, active project, embedded files, hashes, parent_id, and source. 

This is already a good foundation.

---

## Level 2: Frame detection

This is essential for ingestion.

A large answer is not one thing. It may contain:

| Frame type         | Normal embedding policy             |
| ------------------ | ----------------------------------- |
| explanation        | embeddable                          |
| decision           | embeddable                          |
| rule               | hard-rule extraction                |
| code               | store, usually not embed            |
| requirements draft | store, not automatically embed      |
| UML                | store, not automatically embed      |
| command            | store, maybe metadata only          |
| error log          | store, maybe keyword/metadata index |
| unknown            | store, do not embed by default      |

Your own report already states this direction: memory ingestion is separate from recording; memory is not simple document chunking; Q/A records may contain code, requirements, UML, and explanations; code should be stored but not embedded by default; generated requirements and unknown frames should not automatically enter vector memory. 

This is exactly the right boundary.

---

## Level 3: Segment layer

A MemoryRecord remains the authority.

But retrieval should not retrieve the whole record immediately.

The retrieval unit should be a MemorySegment.

A MemorySegment should know:

| Field       | Meaning                            |
| ----------- | ---------------------------------- |
| record_id   | parent MemoryRecord                |
| role        | input or output                    |
| frame_type  | explanation, code, rule, UML, etc. |
| span        | where it came from                 |
| text        | segment text                       |
| embeddable  | yes/no                             |
| importance  | derived from tag/source            |
| project     | active project snapshot            |
| keywords    | auto and user keywords             |
| concept_ids | linked concepts                    |
| sibling_ids | neighboring segments               |

This solves the central problem:

You do not destroy the Q/A pair.
You do not feed the whole Q/A.
You do not retrieve meaningless chunks.

You retrieve a segment, then expand intelligently to the record level if needed.

---

## Level 4: Summary layer

You are right to avoid LLM summaries for every Q/A.

That would be expensive and unnecessary.

But summaries are useful selectively.

The RAPTOR paper is relevant here: it recursively embeds, clusters, and summarizes chunks into a tree so retrieval can use different abstraction levels instead of only short contiguous chunks. It improved performance on long-document QA and complex reasoning tasks. ([proceedings.iclr.cc][7])

For RAGstream, do not summarize everything.

Use summaries only when:

| Condition                                          | Action                                      |
| -------------------------------------------------- | ------------------------------------------- |
| record is very large                               | create short record summary                 |
| many sibling segments are often retrieved together | create cluster summary                      |
| record is Gold and long                            | create stable human-reviewable summary      |
| answer contains mostly code                        | no semantic summary unless user promotes it |
| record is Green and rarely used                    | no summary                                  |

So summary generation becomes selective, not automatic.

---

## Level 5: Knowledge Map / Graph

This is your deeper vision.

Nodes could be:

* MemoryRecord
* MemorySegment
* Concept
* Rule
* Decision
* Project
* File
* Requirement
* Function
* Error
* Tool result
* Document chunk

Edges could be:

* supports
* contradicts
* refines
* depends_on
* overlaps
* replaces
* implements
* tests
* explains
* belongs_to
* derived_from
* similar_to
* exception_to

This graph should not replace retrieval. It should guide retrieval.

The retrieval becomes:

semantic candidate → graph expansion → relation filtering → context budget assembly.

This is where advanced topology becomes real.

---

# III. Part 4: Documents, Wiki, Learning, Fine-Tuning, Knowledge Map

## 4.1 Agents slowly construct Knowledge Maps of documents

This is possible and realistic.

But I would not begin with fully automatic graph construction.

Start with semi-automatic construction:

| Step                          | Who decides |
| ----------------------------- | ----------- |
| extract candidate concepts    | system      |
| propose edges                 | system      |
| accept/reject important edges | user        |
| store accepted map            | system      |
| use map for retrieval         | system      |

GraphRAG and Graphiti show that automatic graph construction is feasible, but they also show why human governance matters: generated graphs can contain wrong edges, stale facts, or over-compressed summaries. Microsoft GraphRAG is oriented toward static private datasets and builds graph indexes plus community summaries; Graphiti/Zep emphasizes dynamic and temporal knowledge graphs for evolving agent memory. ([Microsoft][8])

For RAGstream, the right path is:

automatic proposal, human-governed promotion.

---

## 4.2 Build your own Wiki

This is also realistic.

But the Wiki should not be just a dump of chat summaries.

It should be a curated knowledge product produced from memory and documents.

Suggested Wiki layers:

| Wiki layer            | Source                               |
| --------------------- | ------------------------------------ |
| Concepts              | extracted from memory/documents      |
| Decisions             | promoted from Q/A records            |
| Rules                 | Red procedural memory                |
| Requirements          | promoted requirements updates        |
| Architecture pages    | document + memory synthesis          |
| Troubleshooting pages | repeated errors and fixes            |
| Open questions        | unresolved issues from conversations |
| Glossary              | concepts and aliases                 |

The Wiki should grow slowly.

Good source events:

* user marks record Gold/Silver
* user creates Red rule
* repeated retrieval hits same concept
* A4 condenser repeatedly produces same fact
* user corrects assistant
* document retrieval repeatedly fails
* requirement/design decision is finalized

This is a very strong idea, but it must remain promotion-based.

Not every memory becomes Wiki.

---

## 4.3 AI learning / fine-tuning / memory / Wiki

These are different mechanisms.

| Mechanism        | Best use                                                           |
| ---------------- | ------------------------------------------------------------------ |
| Memory retrieval | facts, decisions, recent context, project continuity               |
| Knowledge map    | relationships, contradictions, dependencies, conceptual navigation |
| Wiki             | curated stable knowledge                                           |
| Fine-tuning      | style, stable behavior patterns, specialized classification        |
| Prompt rules     | immediate hard constraints                                         |
| Evaluation       | measuring whether retrieval/answers improved                       |

Fine-tuning is not the first solution for your current memory problem.

Your current problem is context selection, not model weights.

So the order should be:

1. memory recording
2. memory ingestion
3. memory retrieval
4. ContextPack assembly
5. knowledge map
6. Wiki promotion
7. evaluation
8. only later fine-tuning, if you have repeated stable patterns worth teaching

---

# IV. Focus on Memory Ingestion

Your ingestion challenge is exactly this:

Large Q/A pairs should remain intact, but retrieval should not blindly use whole pairs or meaningless chunks.

The solution is a layered ingestion model.

## Memory ingestion should produce several artifacts

| Artifact               | Purpose                                       |
| ---------------------- | --------------------------------------------- |
| Raw MemoryRecord       | truth, audit, full reconstruction             |
| Record metadata        | tag, project, keywords, source, hashes        |
| Frames                 | detect explanation/code/rule/UML/requirements |
| Segments               | retrieval units                               |
| Concepts               | topic/entity/requirement/function/rule        |
| Links                  | relation between records, segments, concepts  |
| Optional summary       | only for large/high-value records             |
| Embedding entries      | only for embeddable segments                  |
| Keyword/FTS entries    | for deterministic search                      |
| Rule entries           | for Red hard rules                            |
| ContextPack candidates | retrieval-time objects                        |

This must be separate from document ingestion.

Your current document ingestion uses one canonical chunking pass with shared IDs into dense and SPLADE branches. 

Memory ingestion should instead use record-aware segmentation.

---

## What happens to a large Q/A pair?

A large Q/A pair should be processed like this:

| Stage                     | Result                                          |
| ------------------------- | ----------------------------------------------- |
| keep full Q/A             | full MemoryRecord remains untouched             |
| detect frames             | explanation/code/rule/requirements/UML          |
| assign embeddability      | explanation yes, code no by default             |
| segment embeddable text   | semantic segments, not equal chunks             |
| keep Q anchor             | every answer segment can trace back to question |
| extract keywords/concepts | deterministic first                             |
| create optional summary   | only if large/important/frequent                |
| store graph links         | record ↔ segments ↔ concepts                    |
| index selectively         | only useful parts enter vector retrieval        |

The important principle:

The Q/A pair remains the truth object, but the answer is not retrieved as one giant block.

---

## What gets embedded?

Suggested policy:

| Content            | Embed?                                | Reason |
| ------------------ | ------------------------------------- | ------ |
| user question      | yes, usually as anchor                |        |
| explanation answer | yes                                   |        |
| design decision    | yes                                   |        |
| accepted rule      | not normal embedding; hard-rule store |        |
| code               | no by default                         |        |
| commands           | no by default, metadata only          |        |
| UML                | no by default, unless promoted        |        |
| requirements draft | no by default, unless promoted        |        |
| logs/errors        | maybe keyword/FTS first               |        |
| summaries          | yes, if created                       |        |

This directly addresses your concern about garbage context.

---

## What gets retrieved?

Retrieval should not return only raw segments.

It should return candidate memory units.

A candidate can be:

* one segment
* question anchor + answer segment
* summary + one evidence segment
* Gold record compressed view
* Red hard rule
* concept-linked cluster
* full record only in rare cases

So retrieval is not “top-k chunks.”

Retrieval is “build best memory package under budget.”

---

# V. Memory Retrieval Design

Memory retrieval should be layered.

## Layer 0: Hard Rules

Red records become procedural rules.

They are fetched deterministically.

They do not compete with semantic memory.

They go to a hard-rules section.

## Layer 1: Direct Recent Context

Last N non-Black Q/A records are considered directly.

They may be included as compact recent context.

Gold/Silver recent records get priority.

## Layer 2: Tagged Important Memory

Old Gold/Silver records enter a high-priority candidate pool even if semantic retrieval is weak.

But they still face context budget limits.

Gold should mean:

visible to candidate selection, not automatically dump full text.

## Layer 3: Semantic Segment Retrieval

Dense/SPLADE/keyword retrieval runs over embeddable MemorySegments.

This is where ordinary relevance enters.

## Layer 4: Graph Expansion

From retrieved segments, expand to:

* parent MemoryRecord
* question anchor
* neighboring segments
* linked concepts
* linked decisions
* contradiction/support relations
* project/document nodes

## Layer 5: ContextPack Assembly

The final step decides what goes into the prompt.

It should balance:

* relevance
* tag priority
* recency
* rule priority
* redundancy
* token budget
* relation diversity
* project match

This is the key new object:

ContextPack.

It is the final memory product for SuperPrompt.

---

# VI. Deterministic vs Embedding vs LLM

You asked to divide ingestion, embedding, retrieval, and deterministic parts.

Here is the clean division.

## Deterministic parts

These should be implemented first:

* read MemoryRecord
* preserve full Q/A
* tag handling
* Black exclusion
* Red hard-rule extraction
* project filter
* user keyword filter
* YAKE keyword storage
* frame detection where obvious
* code/UML/requirements exclusion from embedding
* SQLite indexing
* recency score
* tag priority score
* ContextPack budget rules

## Embedding / sparse parts

These come next:

* embed question anchors
* embed explanation segments
* embed design-decision segments
* embed optional summaries
* SPLADE/BM25/FTS for keyword-heavy search
* hybrid fusion

## Graph / knowledge-map parts

These come after segment retrieval works:

* concept nodes
* record-to-concept links
* concept-to-concept links
* support/contradict/depends/refines edges
* graph expansion from retrieved nodes
* graph-based reranking

## LLM-assisted parts

These should be selective, not default:

* summarize very large Gold/Silver records
* propose graph edges
* classify difficult frame boundaries
* extract concepts from important records
* consolidate Wiki pages
* detect contradictions between high-value memories

This keeps cost under control.

---

# VII. Immediate Design Decision

The next requirement files should be split exactly as your report already suggested:

* Requirements_Memory_Ingestion.md
* Requirements_Memory_Retrieval.md

Your current memory-recording requirement explicitly says it does not define Chroma memory ingestion, memory chunking, frame-based embedding, memory retrieval, deterministic fetching, or merging memory with RAG pipeline. 

So the next step is not implementation. The next step is defining these two requirement files.

---

# VIII. Proposed Architecture Basis

The future memory architecture should be:

| Layer             | Object                        |
| ----------------- | ----------------------------- |
| Recording truth   | MemoryRecord                  |
| Metadata truth    | `.ragmeta.json` + SQLite      |
| Ingestion unit    | MemoryFrame                   |
| Retrieval unit    | MemorySegment                 |
| Authority unit    | MemoryRecord                  |
| Rule unit         | MemoryRule                    |
| Graph unit        | MemoryConcept / KnowledgeNode |
| Relation unit     | MemoryLink / KnowledgeEdge    |
| Final prompt unit | ContextPack                   |

And the flow should be:

MemoryRecord is captured.

Memory ingestion derives frames, segments, concepts, links, and optional summaries.

Memory retrieval selects candidate segments/rules/records using deterministic filters, tags, hybrid retrieval, and graph expansion.

ContextPack assembles only the best memory material under budget.

SuperPrompt receives the ContextPack.

This fits your existing RAGstream model because SuperPrompt is already the central state and context carrier for a run. 

---

# IX. Final Answer to Your Vision

Your part 1 is correct:

recent conversation should be directly considered, with Black exclusion and tag-aware priority.

Your part 2 is correct:

important memory must not depend only on semantic similarity. Gold/Silver/Red must create deterministic visibility. Gold needs scarcity rules. Red should become procedural hard rules.

Your part 3 is correct but needs formalization:

keywords alone are not enough; the serious direction is MemorySegment + Concept + Link + optional Summary + Knowledge Map.

Your part 4 is realistic:

the same insights can later improve document retrieval, build a Wiki, and create a slowly growing Knowledge Map. But this should be promotion-based and evaluated, not automatic dumping.

The core architecture direction is:

Memory ingestion is not document chunking.

Memory retrieval is not top-k chunk retrieval.

The correct future design is:

MemoryRecord as truth.
MemorySegment as retrieval unit.
Red rules as procedural memory.
Gold/Silver as deterministic priority controls.
Knowledge Map as relation structure.
ContextPack as final prompt memory package.

[1]: https://docs.langchain.com/oss/python/concepts/memory?utm_source=chatgpt.com "Memory overview - Docs by LangChain"
[2]: https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00638/119630/Lost-in-the-Middle-How-Language-Models-Use-Long?utm_source=chatgpt.com "Lost in the Middle: How Language Models Use Long Contexts | Transactions of the Association for Computational Linguistics | MIT Press"
[3]: https://research.google/pubs/generative-agents-interactive-simulacra-of-human-behavior/?utm_source=chatgpt.com "Generative Agents: Interactive Simulacra of Human Behavior"
[4]: https://www.microsoft.com/en-us/research/project/graphrag/?utm_source=chatgpt.com "Project GraphRAG - Microsoft Research"
[5]: https://docs.llamaindex.ai/en/stable/module_guides/indexing/lpg_index_guide/?utm_source=chatgpt.com "Property Graph Index - LlamaIndex"
[6]: https://help.getzep.com/graphiti/graphiti/overview?utm_source=chatgpt.com "Overview | Zep Documentation"
[7]: https://proceedings.iclr.cc/paper_files/paper/2024/hash/8a2acd174940dbca361a6398a4f9df91-Abstract-Conference.html?utm_source=chatgpt.com "RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval"
[8]: https://www.microsoft.com/en-us/research/blog/introducing-drift-search-combining-global-and-local-search-methods-to-improve-quality-and-efficiency/?locale=zh-cn&utm_source=chatgpt.com "Introducing DRIFT Search: Combining global and local search methods to improve quality and efficiency - Microsoft Research"
