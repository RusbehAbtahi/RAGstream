Updated from your provided `SmallChanges.md`. 

````markdown
# Frontend Requirement — AIDAs Advertisement UI Package

## 1. Scope

This document defines frontend requirements for preparing AIDAs for product-style advertisement material.

Covered pages:

- MAIN
- HARD RULES
- METRICS
- RACT

Implementation scope:

- layout
- labels
- visible UI elements
- popup/menu structure
- static/default display values
- advertisement-ready example content
- frontend interaction states

Backend execution is outside the scope of this requirement.

---

## 2. Global Naming and Label Requirements

### 2.1 Product Name

The visible product name shall be:

```text
AIDAs
````

The name `RAGstream` shall not be shown as the main product title in advertisement-facing screenshots or clips.

### 2.2 Main Text Area Labels

The MAIN page shall use the following visible labels:

```text
Prompt        → User Request
Super-Prompt  → Engineered Prompt
```

### 2.3 Advertisement Example Topic

The visible example content used in the MAIN page shall be software-development related.

The example shall not use MBTI, personality, music, or unrelated personal topics.

Suitable topic domain:

```text
requirements
architecture
code
tests
memory retrieval
agent configuration
implementation status
software lifecycle governance
```

Example user request direction:

```text
Check whether the current memory retrieval implementation matches the requirements and architecture, and prepare an implementation-oriented Engineered Prompt.
```

---

# 3. MAIN Page Requirements

## 3.1 MAIN Page Purpose

The MAIN page shall present the normal AIDAs workflow first and the teaching/debug workflow second.

The visible order shall emphasize:

```text
Memory
→ LLM Call
→ Prompt Builder
→ Manual Memory Feed
→ Pipeline Debug Buttons
→ Status / Logs
```

---

## 3.2 Left Panel Layout

The left panel shall contain two main text areas.

### 3.2.1 User Request

Visible title:

```text
User Request
```

Content:

* software-development example request
* preferably related to requirements, architecture, code, tests, or memory retrieval

### 3.2.2 Engineered Prompt

Visible title:

```text
Engineered Prompt
```

Content:

* structured AIDAs-generated prompt
* sections such as:

  * System
  * Configuration
  * Current User Request
  * Supporting Context
  * Previous Conversation Summary
  * Memory Context
  * Retrieved Project Evidence Summary
  * Raw Retrieved Evidence if visible

The visible retrieved/context text shall match the software-development example topic.

---

## 3.3 Right Panel Layout

### 3.3.1 Memory Area

The Memory section remains at the top.

It shall show:

* stored Q/A memory cards
* tag selector
* retrieval source mode selector
* Direct Recall Key field
* memory-related controls

Visible memory terms may include:

```text
Gold
Green
Black
QA
Q
A
Direct Recall Key
```

---

### 3.3.2 Primary Action: LLM Call

Directly below Memory, the UI shall show the primary LLM action.

Required visible elements:

```text
LLM Call
Model Menu / Model Selection
```

The LLM Call area shall contain:

* Button: `LLM Call`
* Popup/menu button or dropdown beside it
* Model/provider selection inside popup/menu

The popup/menu shall include model/provider groups such as:

```text
OpenAI
Claude
Gemini
Local / Custom
```

Example visible model names may include:

```text
GPT-5.5
GPT-5 mini
Claude Sonnet
Claude Opus
Gemini Pro
Local Model
Custom Endpoint
```

The popup/menu shall include:

* provider selector
* model selector
* optional temperature field
* optional max tokens field
* primary blue button:

```text
Call LLM
```

---

### 3.3.3 Prompt Builder

Below LLM Call, the UI shall show the Prompt Builder action.

Required elements:

* Button: `Prompt Builder`
* Three checkboxes beside or near it:

```text
use A2 PromptShaper LLM
use Retrieval SPLADE
use ReRanking ColBERT
```

Prompt Builder shall be visually presented as the main action that builds the Engineered Prompt.

---

### 3.3.4 Manual Memory Feed

Below Prompt Builder, the UI shall show the manual orchestration path.

Required elements:

* Button: `Feed Memory Manually`
* Text area beside it for pasting an LLM reply

The text area placeholder may be:

```text
Paste LLM reply here for memory capture.
```

---

### 3.3.5 Teaching / Debug Pipeline Buttons

The step-by-step pipeline buttons shall be placed below the primary workflow controls.

Required buttons:

```text
Pre-Processing
A2-PromptShaper
Retrieval
ReRanker
A3 NLI Gate
A4 Condenser
A5 / Future
```

Optional button:

```text
Prompt Builder Debug
```

These buttons are secondary controls.

---

### 3.3.6 Retrieval Top-K

Retrieval Top-K shall be moved below the primary workflow area or into a lower settings/debug section.

Default visible value:

```text
30
```

---

### 3.3.7 Progress, Status, and Runtime Log

At the bottom of the MAIN right panel, show:

* progress bar
* current pipeline status
* runtime log

Visible status examples:

```text
Prompt Builder pipeline completed.
Memory Retrieval finished.
A4 Condenser completed.
LLM Call ready.
```

Runtime Log shall remain visible as a product observability element.

---

# 4. HARD RULES Page Requirements

## 4.1 Page Title

Visible title:

```text
Hard Rules
```

## 4.2 Page Structure

The HARD RULES page shall contain:

1. hard rule input area
2. Add Hard Rule button
3. active hard rules list
4. rule category selector
5. rule preview area
6. optional Engineered Prompt insertion preview

---

## 4.3 Hard Rule Input Area

Required elements:

* text input or text area for a new hard rule
* category selector
* priority selector
* Add button

Button label:

```text
Add Hard Rule
```

---

## 4.4 Rule Categories

Visible rule categories may include:

```text
No Placeholders
Conceptual Precision
Code Culture
Architecture Discipline
Testing Discipline
Traceability
Security / Secrets
Documentation
```

---

## 4.5 Example Hard Rules

The page may show example hard rules such as:

```text
Do not use placeholders in implementation commands.
Every code change must be linked to a requirement ID.
Do not modify architecture without updating the related requirement.
Do not introduce a new agent without a JSON configuration entry.
Every implemented feature must have at least one test reference.
```

---

## 4.6 Active Rules List

The active rule list shall show rule cards or rows with:

* rule ID
* rule text
* category
* priority
* status

Example columns:

```text
Rule ID
Category
Priority
Rule Text
Status
```

Example statuses:

```text
Active
Inactive
Draft
```

---

## 4.7 Engineered Prompt Rule Preview

The page shall include a preview block showing how selected hard rules can appear in an Engineered Prompt.

Example section title:

```text
Hard Rules Preview
```

Example preview structure:

```text
## Hard Rules
- Do not use placeholders in implementation commands.
- Every code change must be linked to a requirement ID.
```

---

# 5. METRICS Page Requirements

## 5.1 Page Title

Visible title:

```text
Metrics
```

## 5.2 Page Structure

The METRICS page shall be a dashboard-style page with cards and diagrams.

It shall include:

* token metrics
* cost metrics
* time metrics
* agent metrics
* retrieval metrics
* memory metrics
* Engineered Prompt metrics

---

## 5.3 Metric Cards

Required metric cards:

```text
Total Tokens
Engineered Prompt Tokens
A2 Tokens
A3 Tokens
A4 Tokens
Memory Context Tokens
Retrieved Evidence Tokens
Estimated Cost
Pipeline Time
LLM Calls
Memory Hits
Retrieved Chunks
A3 Useful Chunks
```

---

## 5.4 Diagrams

The page shall include simple visual diagrams.

Recommended diagram types:

```text
bar chart
line chart
donut/pie chart
small table
status cards
```

Required chart topics:

```text
Token Usage by Stage
Cost by Stage
Pipeline Time by Stage
Memory vs Document Context
Useful vs Discarded Evidence
```

---

## 5.5 Example Default Values

The frontend may use static/default values such as:

```text
Engineered Prompt Tokens: 6,850
Memory Context Tokens: 1,240
Retrieved Evidence Tokens: 3,900
A2 Tokens: 420
A3 Tokens: 1,180
A4 Tokens: 2,100
Pipeline Time: 42 s
Estimated Cost: €0.18
Memory Hits: 4
Retrieved Chunks: 30
A3 Useful Chunks: 8
```

---

## 5.6 Metrics Table

A table shall show stage-level metrics.

Example columns:

```text
Stage
Input Tokens
Output Tokens
Cached Tokens
Time
Cost
Status
```

Example rows:

```text
PreProcessing
A2 PromptShaper
Retrieval
Memory Retrieval
ReRanker
A3 NLI Gate
A4 Condenser
Prompt Builder
LLM Call
```

---

# 6. RACT Page Requirements

## 6.1 Page Name

Working page name:

```text
RACT
```

Possible later display name:

```text
Project Governance
```

## 6.2 RACT Meaning

RACT means:

```text
R = Requirements
A = Architecture
C = Code
T = Tests
```

---

## 6.3 Page Purpose

The RACT page shall show traceability between:

```text
Requirements
Architecture / UML
Code
Tests
```

Each RACT item connects GitHub addresses or repository paths.

---

## 6.4 Page Structure

The RACT page shall contain:

1. project selector
2. RACT traceability table
3. GitHub address fields
4. Project Status button
5. contradiction / missing coverage report area
6. commit-watchdog option
7. status summary cards

---

## 6.5 RACT Traceability Table

The table shall contain columns such as:

```text
Requirement ID
Requirement Address
Architecture Address
Code Address
Test Address
Status
Coverage
Notes
```

Example values:

```text
MEM-RET-001
doc/01-Requirements/Requirements_Memory_Retrieval.md
doc/02-Architucture/UML_MemoryRetrieval.txt
ragstream/retrieval/retriever_mem.py
tests/test_memory_retrieval.py
Implemented
Missing partial tests
Needs benchmark coverage
```

---

## 6.6 GitHub Address Fields

The page shall support visible GitHub/repository addresses for:

```text
Requirement Address
Architecture Address
Code Address
Test Address
```

Example path format:

```text
github.com/RusbehAbtahi/RAGstream/blob/main/doc/01-Requirements/...
github.com/RusbehAbtahi/RAGstream/blob/main/doc/02-Architucture/...
github.com/RusbehAbtahi/RAGstream/blob/main/ragstream/...
github.com/RusbehAbtahi/RAGstream/blob/main/tests/...
```

---

## 6.7 Project Status Button

Required button:

```text
Project Status
```

The page shall include a report area with sections:

```text
Implemented Requirements
Partially Implemented Requirements
Missing Code
Missing Tests
Code Without Requirement Link
Architecture Mismatch
Possible Contradictions
```

---

## 6.8 RACT Status Cards

The page shall include summary cards such as:

```text
Requirements Linked
Architecture Links
Code Links
Test Links
Missing Tests
Possible Contradictions
Unlinked Code Files
```

Example default values:

```text
Requirements Linked: 42
Architecture Links: 31
Code Links: 58
Test Links: 12
Missing Tests: 19
Possible Contradictions: 3
Unlinked Code Files: 7
```

---

## 6.9 Commit Watchdog Area

The RACT page shall include an optional commit-watchdog section.

Visible elements:

* checkbox:

```text
Watch Git Commits
```

* button:

```text
Check Latest Commit
```

* status field:

```text
Latest commit checked
```

* report preview:

```text
Changed files
Related requirements
Missing tests
Possible architecture impact
```

---

## 6.10 Requirement ID Linkage

The RACT page shall show the idea that code can be linked to requirement IDs.

Visible example:

```text
Requirement ID: MEM-RET-001
Code File: ragstream/retrieval/retriever_mem.py
Function: MemoryRetriever.run(...)
Test File: tests/test_memory_retrieval.py
```

---

# 7. Advertisement Screenshot Content Requirements

## 7.1 MAIN Page Screenshot Content

The MAIN page shall be prepared with a software-development example.

Visible areas shall include:

* User Request about software development
* Engineered Prompt with structured sections
* Memory Context related to implementation
* Retrieved Project Evidence Summary related to requirements/code
* Runtime Log with successful pipeline messages
* Memory card related to the same topic

---

## 7.2 Hard Rules Screenshot Content

The HARD RULES page shall show:

* at least 4 active hard rules
* Add Hard Rule button
* rule category selector
* Hard Rules Preview block

---

## 7.3 Metrics Screenshot Content

The METRICS page shall show:

* token dashboard
* cost dashboard
* time dashboard
* agent token usage chart
* Engineered Prompt token count
* memory/retrieval stats

---

## 7.4 RACT Screenshot Content

The RACT page shall show:

* Requirements / Architecture / Code / Tests table
* GitHub addresses
* Project Status button
* status cards
* report preview
* commit-watchdog controls

---

# 8. Visible Workflow Ordering for Advertisement

The MAIN page shall visually support this workflow:

```text
User Request
→ Prompt Builder
→ Engineered Prompt
→ LLM Call
→ Memory Capture
```

The optional manual workflow shall be visually supported as:

```text
Engineered Prompt
→ external fixed-rate LLM account
→ answer pasted into Manual Memory Feed
→ memory card created
```

The governance workflow shall be visually supported as:

```text
Requirement
→ Architecture
→ Code
→ Test
→ Project Status
```

---

# 9. Implementation Priority

Frontend implementation priority:

```text
1. MAIN page label and layout update
2. LLM Call popup/menu
3. METRICS page dashboard
4. HARD RULES page
5. RACT page
6. Advertisement-ready example content
```

```
```
