title: "00-Absolute_Master_Guide"
author: "Rusbeh Abtahi"
version: "2.1"
updated: "2025-06-20"
---

# 00-Absolute_Master_Guide.md

## I. File Loading Order

Load files in this **exact ascending order** for maximum context and consistency:

1. 00-Absolute_Master_Guide.md
2. 01-Technical_Profile_Rusbeh.md
3. 02-Chronological_Progress_Log.md
4. 03-Cognitive_Profile_Interaction_Guide.md
5. 04-My_Cognitive_Profile_Summary.md
6. 05-Cognitive_Management_Modes.md
7. 06-Simple_Ti_Mode.md
8. 11-Dynamic_Session_Tracker.md
9. 12-Prompt_Eng_Learning_Map.md
10. 13-PromptEng_ActualKnowledge.md
11. 16-AWS_Learning_Map.md
12. 17-AWS_ActualKnowledge.md
13. 20-TinyLlama_Architecture_and_Roadmap.md
14. 21-Bootstrap_MVP.md
15. 22-RQL_Intermediate_State.md
16. UML_Diagram - Detailed.txt
17. Epics2-7_final.md
18. gui_epic1_full.py
19. AWS_Diagram_intermediate.py

*No other files are included in this ChatGPT project. Any “Reserved” or legacy files are excluded.*

---

## II. Hierarchical Structure and File Roles

- **Core Identity & Cognitive Layer**
  - 01: Technical Profile — Technical CV, skill map, and project background.
  - 02: Chronological Progress Log — Time-ordered milestone tracker.
  - 03: Cognitive Profile Interaction Guide — LLM and collaborator interface strategy.
  - 04: My Cognitive Profile Summary — Detailed self-model (MBTI stack, simulation habits).
  - 05: Cognitive Management Modes — 8-mode MBTI-based project/leadership framework.
  - 06: Simple Ti Mode — Universal fallback for ultra-clear, beginner-proof explanations.

- **Execution & Dynamic Logging**
  - 11: Dynamic Session Tracker — Chronological tracker of active project phases and session state.

- **Prompt Engineering — Learning & Actual Knowledge**
  - 12: Prompt Eng Learning Map — Structured prompt engineering knowledge tree and learning priorities.
  - 13: PromptEng ActualKnowledge — Evidence-based self-audit of current prompt engineering skills.

- **AWS — Learning & Actual Knowledge**
  - 16: AWS Learning Map — Knowledge domains, learning priorities, and meta-inference map.
  - 17: AWS ActualKnowledge — What has actually been implemented, practiced, or mastered.

- **TinyLlama — Architecture, MVP, Requirements**
  - 20: TinyLlama Architecture and Roadmap — Unified architecture, requirements, and project vision.
  - 21: Bootstrap_MVP — Full technical audit of Lambda MVP and its orchestration (scripts, policies, flows).
  - 22: RQL_Intermediate_State — Expanded requirements for next-phase architecture (desktop GUI, GPU inference, cost, IAM, VPC).
  - UML_Diagram - Detailed.txt — **Canonical, detailed UML class and interaction diagram for the entire TinyLlama desktop, backend, and multi-backend architecture. Explicitly models the requirements and interactions defined in 22-RQL_Intermediate_State.md.**
  - Epics2-7_final.md — **Full, never-reduced, fully audited Epic and ticket list (Epics 2–7). All functional, acceptance, and implementation criteria for next-phase work, mapped to 22-RQL_Intermediate_State.md.**
  - gui_epic1_full.py — **Complete Python implementation of the desktop GUI and all associated controller/service/state modules for Epic 1. Implements the desktop GUI requirements in file 22 and is the living implementation reference for all future Epics.**
  - AWS_Diagram_intermediate.py — **Source of truth for TinyLlama AWS architecture. Generates up-to-date architecture diagrams programmatically. Encodes and visualizes all core components, flows, and Epic boundaries from 22-RQL_Intermediate_State.md. Preferred over static images for audit and version control.**

---

## III. General Rules and Guidance

- Always load files **in the order above** unless the user explicitly instructs otherwise.
- Do not reference, summarize, or load any file not present in this list for this ChatGPT project.
- Prioritize strict separation between prompt engineering, AWS/cloud, and TinyLlama domains—unless a file is cross-linked in its content.

---

## IV. Special Project Modes

| Project Mode                | File/Trigger(s)                                | Behavior                                                         |
|-----------------------------|------------------------------------------------|------------------------------------------------------------------|
| Prompt Engineering          | 12, 13                                         | Use advanced prompt logic, RAG, meta-prompt, and session mapping |
| AWS Cloud / DevOps          | 16, 17                                         | Guide for IAM, Lambda, EC2, CI/CD, budget, automation            |
| TinyLlama Architecture      | 20, 21, 22, UML_Diagram - Detailed.txt, Epics2-7_final.md, gui_epic1_full.py, AWS_Diagram_intermediate.py | Use for requirements, architecture, deployment, RQL audit        |
| Cognitive/Management Modes  | 03, 04, 05, 06                                 | Enable MBTI-based reasoning, Simple Ti Mode, or dynamic switching|
| Dynamic Session Tracking    | 11                                             | Use for active phase tracking, slot management                   |

---

## V. Expansion & Update Protocol

- **File Naming:** All new files must follow `NN-Topic_Title.md` (or `.py`/`.txt` as appropriate).
- **Integration:** Add new files only with explicit intent and update this master file.
- **Deprecation:** When a file is removed from the project, update this guide and remove its references from ChatGPT project loads.
- **Hierarchy:** Always maintain separation between learning maps, actual knowledge audits, and phase-specific architectural docs.

---

## VI. Minimal Dependency Map (Tree View)

```

00-Absolute\_Master\_Guide.md
├── 01-Technical\_Profile\_Rusbeh.md
├── 02-Chronological\_Progress\_Log.md
├── 03-Cognitive\_Profile\_Interaction\_Guide.md
│   ├── 04-My\_Cognitive\_Profile\_Summary.md
│   └── 05-Cognitive\_Management\_Modes.md
├── 06-Simple\_Ti\_Mode.md
├── 11-Dynamic\_Session\_Tracker.md
├── 12-Prompt\_Eng\_Learning\_Map.md
│   └── 13-PromptEng\_ActualKnowledge.md
├── 16-AWS\_Learning\_Map.md
│   └── 17-AWS\_ActualKnowledge.md
├── 20-TinyLlama\_Architecture\_and\_Roadmap.md
│   ├── 21-Bootstrap\_MVP.md
│   └── 22-RQL\_Intermediate\_State.md
│       ├── UML\_Diagram - Detailed.txt
│       ├── Epics2-7\_final.md
│       ├── gui\_epic1\_full.py
│       └── AWS\_Diagram\_intermediate.py

```

---

## VII. Cognitive/Management Interface

- MBTI simulation is referenced only via files present in this project (03, 04, 05, 06).
- Simple Ti Mode is always available for any technical or process explanation.
- Use dynamic tracking (11) for slot management, active session context, and project phase audit.

---