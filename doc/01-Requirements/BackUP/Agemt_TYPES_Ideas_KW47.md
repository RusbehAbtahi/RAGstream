# Agent Type Structure (Multi-Axis View)

Agents are described as points in a multi-dimensional space, not as a flat list of labels.  
Each axis is independent (orthogonal).

---

## Axis 1 – Decision Engine

How the agent makes its decisions internally.

- Rule-based  
  - Decisions follow explicit code / rules / heuristics.  
  - Examples: deterministic routing, hard filters, schema checks.

- LLM-based  
  - Decisions are produced only by an LLM (single model or several models), given a prompt and schema.  
  - Examples: classification, writing, planning, critique.

- Hybrid  
  - Rule logic plus LLM reasoning combined inside one agent.  
  - Typical pattern: Python pre/post checks + LLM judgement in between.

---

## Axis 2 – Memory

Whether the agent itself can “look back” or “store” information between calls.

- Memoryless agent  
  - Only sees the current input; no direct access to past interactions or long-term store.  
  - Any logs or vector stores exist at system level, not visible as tools to the agent.

- Memory-augmented agent  
  - Has explicit read/write access to some external store (log, DB, vector index, key–value store).  
  - Uses simple primitives like “read previous items of type X” or “append summary Y” (conceptually; actual API can be neutral tools).  
  - In many systems, most agents remain memoryless and memory is centralized in the RAG / orchestration layer.

---

## Axis 3 – LLM Usage Pattern

How many LLM calls and models are orchestrated inside a single agent.

- Single-call agent  
  - One LLM call (one model) per invocation.  
  - Example: Chooser or Writer that returns JSON in a single step.

- Orchestrated agent (multi-call / multi-model)  
  - More than one LLM call inside the agent before returning a result.  
  - Common internal patterns:
    - Self-refine loop: propose → critique → refine.  
    - Cascade: cheap model first, escalate to stronger model if needed.  
    - Ensemble / jury: several calls or models in parallel, then compare or vote.  
    - Debate: two or more models argue; a judge model selects the final answer.

This axis is independent of Axis 1: an agent can be LLM-based and still be single-call, or orchestrated, without changing its rule/LLM/hybrid label.

---

## Axis 4 – Output Type

What kind of output the agent is meant to produce.

- Chooser  
  - Selects from fixed enums or discrete options (including 0/1, labels, route IDs).  
  - Output is typically JSON with enums + optional confidence.  
  - Used for routing, classification, yes/no decisions, relevance flags.

- Writer  
  - Produces new text or structured JSON with free-text fields.  
  - Used for explanations, summaries, rewrites, step-by-step plans, code, etc.

- Extractor  
  - Special case of Writer: may only copy or lightly normalize text that already appears in the inputs; no new facts.  
  - Used for information extraction, metadata generation, and low-hallucination grounding.

Many practical agents are “Writer (planner mode)” or “Chooser (multi-label)”, but the primitive types remain these three.

---

## Axis 5 – Collaboration Mode

How the agent is embedded into the broader workflow.

- System-driven  
  - Agent is called automatically inside a pipeline; human only sees final result.

- Human-in-the-loop  
  - Agent output is explicitly meant for human review or decision.  
  - Examples:
    - Planner agent that proposes a plan; human approves or edits.  
    - Critic/qualifier agent that scores quality; human decides whether to accept or re-run.

RAG-style systems often prefer human-in-the-loop for key steps (planning, evaluation, final formatting) and system-driven mode for low-risk substeps (retrieval, filtering).

---

## Example Roles (RAG-oriented, alle memoryless)

These roles are combinations of the axes above, commonly useful in RAG / software-engineering workflows.

- Chooser agent (router / classifier)  
  - LLM-based, memoryless, single-call, output = Chooser.  
  - Example: map messy input to enums (task type, tone, audience, etc.).

- Writer agent (prompt shaper / condenser / final answer)  
  - LLM-based, memoryless, single-call, output = Writer.  
  - Example: structure a “SuperPrompt”, generate explanations, rewrite requirements.

- Extractor agent (structure from text/code/specs)  
  - LLM-based, memoryless, single-call, output = Extractor.  
  - Example: extract classes, functions, requirements, TODOs, or “clean intent” from chaotic text.

- Retrieval-filter agent (semantic cleaner over chunks)  
  - LLM-based, memoryless, single-call, output = Chooser over many chunks at once.  
  - Reads all candidate chunks together and returns a 0/1 vector or relevance scores, removing overlaps and contradictions beyond pure similarity search.

- Planner agent  
  - LLM-based, usually memoryless, single-call, output = Writer (structured plan).  
  - Converts a high-level goal into a JSON plan of steps, indicating which agents or human actions are involved.

- Critic / qualifier agent  
  - Typically hybrid (Python checks + LLM judgement), memoryless, single-call, output = Chooser + short Writer fields.  
  - Scores outputs along dimensions like correctness, completeness, formatting, hallucination risk; often used in human-in-the-loop mode.

- Cleaner / intent agent  
  - LLM-based, memoryless, single-call, output = Extractor + Writer.  
  - Takes raw chaotic input, removes insults/noise, and splits it into:
    - one-line purpose,  
    - task core,  
    - context / background,  
    - discardable noise.

Each concrete agent in a RAG system can be described by:

- Decision engine: rule-based / LLM-based / hybrid  
- Memory: memoryless / memory-augmented  
- LLM usage: single-call / orchestrated  
- Output type: chooser / writer / extractor  
- Collaboration mode: system-driven / human-in-the-loop

This multi-axis description remains stable even as new agent roles are added.
