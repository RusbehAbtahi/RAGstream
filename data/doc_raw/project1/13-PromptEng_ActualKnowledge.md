---
title: "Prompt Engineering Actual Knowledge"
author: "Rusbeh Abtahi"
version: "2025-06-12"
---

# Prompt Engineering Actual Knowledge

## What I’ve Done

- **Personal Workflow and System Design**  
  Developed and maintained a multi-file, living documentation system for prompt engineering, including session logs, requirements, cognitive profile mapping, and prompt history. All documentation practices are actively used and refined.

- **Prompt Structuring and Meta-Prompting**  
  Designed, tested, and iterated on various prompt structures (system, role, output-format, tone, chain-of-thought, meta-prompts) for use with ChatGPT (and O3).  
  Practiced “mode switching” (Te, Ti, Fe, Se) and role instructions (MBTI types, critical reviewer, devil’s advocate), directly influencing LLM output style and reliability.

- **Custom RAG Pipeline Development**  
  Implemented a practical retrieval-augmented generation (RAG) pipeline in Python:  
  - Ingested markdown documents with sliding window chunking  
  - Generated OpenAI ada-002 embeddings for each chunk  
  - Performed cosine similarity retrieval for top-k answers  
  - Assembled and returned results  
  - Closed the pipeline after achieving clear, repeatable results

- **Document Retrieval & Vector Embeddings**  
  Built and tested document retrieval flows, managing embedding sizes, chunking, and similarity scoring.  
  Explored the practical limits of retrieval granularity and corpus coverage.

- **Multi-Agent Prompt Orchestration (Planner-Executor)**  
  Designed and prototyped simple agent-based flows where one prompt “plans” tasks and another “executes” them.  
  Ran basic planner–executor loops and reflected on bottlenecks, model alignment, and error propagation.

- **Prompt Evaluation and Diagnostics**  
  Conducted targeted tests for LLM summarization/merging bias and error modes.  
  Used “devil’s advocate” and self-critique scripts to challenge and diagnose model output.  
  Documented the need for explicit instructions to counter reductionist or alignment tendencies.

- **Session Mapping and Dynamic Context Windows**  
  Maintained up-to-date session logs and project mapping files to externally track context, chunking, and loaded knowledge, maximizing continuity across multiple ChatGPT sessions.

- **Iterative, Non-Redundant Documentation**  
  Routinely updated, split, and merged .md files to keep only high-value, current instructions and examples.  
  Developed systematic file-numbering and archiving strategies.

## What I’ve Learned

- **Prompt Structure Controls Output**  
  Discovered that clear, modular system prompts (with explicit format, tone, and constraints) are essential for reliable and repeatable LLM performance, especially for technical or multi-step workflows.

- **Mode and Role Switching Changes LLM Behavior**  
  Demonstrated how explicit role and mode prompts can shift LLM style, depth, and bias (MBTI modes, critical reviewer, etc.).

- **Retrieval and Chunking Strategy**  
  Learned the trade-offs of window sizes, overlap, and retrieval precision in embedding-based pipelines.  
  Saw firsthand the difference between in-memory model context and explicit retrieval from external knowledge.

- **Bias and Alignment Tendencies**  
  Documented ChatGPT’s (and O3’s) tendency to “parrot” or align unless forced into skepticism, and learned to counter this via robust prompt constraints.

- **Error & Summarization Failure Modes**  
  Experienced LLM reductionism in merges/summarizations, leading to robust anti-summarization prompts and context-preserving techniques.

- **Self-Audit & Error Analysis**  
  Practiced regular review of prompt outcomes, using critical/contradictory scripts to surface blind spots in prompt design.

- **Documentation as an Engineering Tool**  
  Established that rigorous, modular .md tracking of sessions, project states, and prompt variants improves reproducibility and scaling of prompt engineering.

## Current Skill Level

| Area                                             | Level                     | Notes                                                      |
|--------------------------------------------------|---------------------------|------------------------------------------------------------|
| Prompt design, structure, and meta-prompts       | Strong Intermediate+      | Regular practice, system templates, role/mode switching    |
| Retrieval-augmented pipelines (RAG, embeddings)  | Intermediate (practical)  | End-to-end pipeline built and closed, not just planned     |
| Multi-agent orchestration (planner–executor)     | Early Intermediate        | Simple flows tested, not full production agents            |
| LLM prompt evaluation/testing                    | Early Intermediate        | Self-diagnostics, not yet formal A/B or regression harness |
| Session/context mapping, doc strategy            | Advanced                  | Live, versioned docs; mapping; non-redundant iteration     |
| External/commercial prompt deployment            | Not yet done              | All work is internal and self-driven                       |
| Automation (API scripting, pipelines)            | Not yet                   | Manual workflows only; no API/CLI integration yet          |

## Next Steps

1. **Scripted/Automated Prompt Pipelines**  
   Move from manual .md file workflows to Python or CLI tools that dynamically build and submit prompts via OpenAI API, integrating selection, delivery, and result collection.

2. **Hands-On RAG Frameworks**  
   Deploy and experiment with LangChain, LlamaIndex, or similar frameworks on real project data—implement and tune retrieval-augmented flows, not just conceptualize.

3. **Formal Prompt Evaluation Harness**  
   Develop or adapt tools for prompt A/B testing, regression comparison, and “diff” logging to systematically measure and optimize prompt quality.

4. **Real-World Feedback**  
   Seek collaborative or client-driven prompt use cases to test the system under external constraints and feedback.

5. **Further Compression and Optimization**  
   Experiment more deeply with prompt compression, summarization, and chain-of-thought strategies to maximize information within context window limits.

---

*This file is strictly evidence-based. All listed skills are backed by actual session logs, code, or documentation as of June 2025. No planned or aspirational topics are included unless directly practiced.*
