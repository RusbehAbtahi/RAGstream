# RAGstream handoff report for new chat
Date: 16.04.2026
Prepared from the current chat after the A3 implementation/refactor work

## 1. Purpose of this document

This document is a handoff report for a new chat.

Its purpose is to preserve the real current truth of:
- the Agent Stack,
- A2 PromptShaper,
- A3 NLI Gate,
- the new A3 prompt design,
- the neutrality decisions,
- the observed A3 behavior in tests,
- and the startup/performance diagnosis discussed at the end.

This document must be treated as a temporary high-authority handoff artifact because:
- current requirement files are not fully aligned with the present code behavior,
- current UML is not fully aligned with the present code behavior,
- and the chat contained important implementation decisions that are not yet written back consistently into requirements/UML.

Until requirements and UML are updated, this report is the best narrative source of truth for the current state of Agent Stack, A2, A3, and the recent performance diagnosis.

## 2. Source-of-truth hierarchy for the next chat

For the topics covered here, the practical source-of-truth order should be treated as:

1. current working code,
2. this handoff report,
3. current runtime JSON agent configs,
4. old requirements/UML only as background context.

Important:
for Agent Stack, A2, and A3, some requirement/UML text is now older than the actual implementation direction and older than the decisions taken in this chat.

## 3. Executive summary of achievements in this chat

### 3.1 A3 was turned from weak/placeholder behavior into a meaningful working stage

The most important achievement of this chat is that A3 is no longer only a vague or weak concept. It now has a concrete working behavior and a much better prompt design.

The final A3 direction reached here is:
- A3 is now a usefulness classifier over reranked chunks.
- It no longer tries to do aggressive duplication analysis.
- It uses local chunk ids 1..N in the LLM prompt instead of long real chunk ids.
- It wraps evidence chunks in a single outer XML-like structure.
- It sanitizes inner markdown structure markers so chunk-internal headings do not fight with outer prompt structure.
- It feeds only the real prompt text to the model, not noisy A2 meta fields.
- It prints/logs the real prompt sent to the LLM so the user can inspect it directly.

This dramatically improved clarity and made A3 much more inspectable and more trustworthy.

### 3.2 The Agent Stack was pushed toward neutrality

A major theme of this chat was the requirement that:
- AgentFactory must remain neutral,
- AgentPrompt must remain neutral,
- helper/composer code must remain neutral,
- and anything specific to A3 must live either in JSON or in the A3 agent itself.

This was not a small cosmetic preference. It was treated as a hard design rule.

The design intent reached here was:
- no A3-specific formatting logic in neutral Agent Stack files,
- no selector/classifier business logic hidden inside AgentFactory or AgentPrompt,
- special A3 prompt assembly must be local to A3,
- JSON and the agent itself carry specifics,
- neutral stack remains reusable for A2 and future agents.

### 3.3 A2 survived the refactor and still works

After the Agent Stack changes and the later AgentFactory fixes, A2 worked again.
This matters because the refactor initially broke A2 with a decision-target/catalog resolution issue, and then that was fixed.

So the practical status is:
- A2 is live,
- A2 uses the neutral JSON-driven stack,
- A2 is currently operational again after the fixes in this chat.

### 3.4 The A3 prompt itself became much better

The final A3 prompt design is much better than earlier versions because:
- long noisy real chunk ids were removed from the LLM-facing prompt,
- duplication instructions were removed after bad results,
- fake structure pollution from chunk-internal markdown was handled,
- only the actual user prompt text is fed into A3,
- and all of this is inspectable in logs.

### 3.5 A3 now shows real semantic filtering ability

The later A3 tests showed that:
- A3 is not blindly obeying Retrieval and ReRanker,
- A3 can discard several high-ranked but semantically weak/meta/template chunks,
- A3 can still over-include some secondary chunks,
- but overall the behavior is now much more meaningful than before.

In short:
A3 is not perfect yet, but it is now genuinely useful.

### 3.6 Startup/performance diagnosis was clarified structurally

The slow startup was not treated as a mysterious PyTorch problem only.
The real structural diagnosis found here was:
- the UI creates the controller during first page load,
- the controller eagerly creates heavy stage objects during its own initialization,
- therefore the whole page waits for heavy initialization before becoming usable.

The better design agreed here is:
- fast UI boot,
- heavy reranker warm-up in background,
- disable reranker-related buttons until ready,
- show explicit loading/warming/ready state.

That is the professional direction for startup behavior.

## 4. Final current truth of A3

This section is the most important technical core of the whole report.

### 4.1 A3 purpose

A3 now acts as a reranked-chunk usefulness classifier.

Its job is:
- read the reranked candidate set,
- evaluate chunks comparatively as a set,
- assign usefulness labels,
- compute a working selected set,
- and write the result back into SuperPrompt.

It is no longer doing the earlier aggressive duplicate-marking design that was discussed before.

### 4.2 A3 inputs

A3 currently consumes:
- the current SuperPrompt,
- especially the reranked stage output,
- up to a bounded candidate set,
- and the prompt-under-evaluation text derived from the user prompt fields.

The current user-prompt block for A3 is built in this exact semantic order:
1. purpose text, if present,
2. task text,
3. context text, if present.

Important:
- no `## Purpose`
- no `## Task`
- no `## Context`
- no A2 meta fields like audience/tone/depth/confidence
- no extra labels inside that block

If purpose or context do not exist, only the existing pieces remain.
So if only task exists, A3 receives only task text.

### 4.3 A3 does not use long real chunk ids in the prompt

This was a very important change.

The LLM-facing A3 prompt no longer uses the real chunk ids like:
`TEST1/...::sha256::chunk_index`

Instead:
- the prompt uses local ids `1..N`,
- the local ids are mapped internally back to the real chunk ids after LLM output is parsed.

This makes the prompt much cleaner and removes useless noise from the model’s view.

Important consequence:
local chunk numbers are not stable across runs.
For example:
- chunk 23 in one run may be a completely different real chunk than chunk 23 in another run.
- this later became important when comparing test runs and discovering that “chunk 23” had changed identity between runs.

This is normal and expected in the current design.

### 4.4 A3 uses one outer structure only

A major design discussion in this chat was about prompt structure contamination.

Final current decision:
A3 evidence chunks use one outer XML-like structure only.

Conceptually the structure is:

<user_prompt_under_evaluation>
...
</user_prompt_under_evaluation>

<evidence_chunks>
  <chunk index="1" chunk_id="1" rank="1">
    <chunk_text>
      ...
    </chunk_text>
  </chunk>
  ...
</evidence_chunks>

<required_output>
...
</required_output>

The important decision was:
- do not mix many outer structure systems,
- do not keep outer markdown hierarchy plus XML plus raw markdown competition,
- use one outer wrapper style only.

### 4.5 Why chunk text needed sanitization

A big problem was discovered:
chunk text often contains markdown headings such as:
- `#`
- `##`
- `###`

If passed raw into the prompt, those internal headings can compete with the outer prompt structure and confuse the model.

Earlier there was a proposal to replace every `#` with `*`, but that was judged too superficial and too destructive.

The final better design chosen here was:
sanitize only line-start structure markers inside chunk text.

Current conceptual mapping:
- line-start `# ...` -> `[H1] ...`
- line-start `## ...` -> `[H2] ...`
- line-start `### ...` -> `[H3] ...`
- line-start code fence ``` -> `[CODE_FENCE]`
- line-start `---` -> `[RULE]`

This is important because:
- chunk content stays semantically readable,
- but it no longer fights with the outer prompt structure.

This is one of the best design decisions made in this chat.

### 4.6 Duplication logic was removed from A3

Originally A3 tried to classify:
- usefulness,
- duplication,
- canonical_chunk_id,
- and a selection band.

That design produced many bad duplicate decisions.
The model over-called duplication even when chunks only partially overlapped or merely shared topic vocabulary.

The user manually inspected examples and judged those duplicate decisions to be bad.
This led to a major simplification.

Final current A3 decision:
remove duplication handling entirely from the A3 prompt and output.

Current A3 output now focuses only on:
- selection_band
- item_decisions with chunk_id and usefulness_label

Current usefulness labels:
- useful
- borderline
- discarded

This simplification was important and correct.
It made A3 more reliable.

### 4.7 A3 current JSON/output contract

The current A3 LLM output is conceptually:

{
  "selection_band": "high | medium | low",
  "item_decisions": [
    {
      "chunk_id": "1",
      "usefulness_label": "useful | borderline | discarded"
    },
    ...
  ]
}

Important:
- no duplicate_status
- no canonical_chunk_id
- no prose
- no comments
- no extra keys

### 4.8 A3 deterministic post-processing after LLM output

A3 does not stop at raw LLM output.
There is also deterministic post-processing.

The important behavior described in the current implementation direction is:

- useful chunks are the main selected working set,
- there is a hard max selection cap,
- if too few useful chunks exist, best borderlines are promoted in reranker order until the minimum floor is reached,
- A3 stage rows are written into `views_by_stage["a3"]`,
- discarded chunks get discarded stage status,
- non-discarded chunks are effectively treated as selected for stage-view purposes,
- `final_selection_ids` is written from the useful-first policy plus borderline fallback.

So A3 is hybrid in a real sense:
- semantic classification by LLM,
- controlled deterministic set construction afterward.

### 4.9 A3 prompt transparency/logging

One hard requirement in this chat was:
the exact prompt sent to the LLM must be visible in CLI/logs.

This is important because:
- without prompt transparency, debugging A3 is almost impossible,
- especially when chunk text and structure are complicated.

Current practical truth:
the logs shown in this chat confirm that the exact A3 system and user messages are printed and inspectable.

That is a major quality improvement.

## 5. Final current truth of A2

### 5.1 A2 role

A2 remains the PromptShaper.
It is a chooser-type agent that decides meta-configuration for the downstream answering behavior.

Current conceptual output includes:
- system role(s)
- audience
- tone
- depth
- confidence

### 5.2 A2 status after refactor

A2 initially broke after the AgentFactory refactor because of a catalog/decision_target resolution mismatch.
The failure was explicitly seen in the app.
That issue was then fixed.

Current practical status:
A2 works again.

### 5.3 A2 current behavior in practice

In the logged working example shown in this chat, A2 selected:
- `generative_ai_expert`
- `aws_cloud_architect`
- `software_architect`
for system roles,
and chose:
- `self_default_senior_engineer`
- `formal_te_si`
- `detailed`
- `high`

This proves that A2 is operational after the refactor.

### 5.4 A2 and neutrality

A2 must still remain a normal JSON-driven consumer of the Agent Stack.
The important design rule from this chat is:
A2-specific business logic should not be hidden in AgentFactory/AgentPrompt.
The neutral stack should remain generic.
A2 specifics belong in:
- A2 JSON,
- A2 agent wrapper,
- and its own deterministic handling.

## 6. Neutrality decisions for Agent Stack

This section is critical because neutrality was a central design constraint in the chat.

### 6.1 Hard rule established in the chat

The user established a hard rule:

Agent Stack must remain 100 percent neutral.

This applied especially to:
- AgentFactory
- AgentPrompt
- compose/helper functions
- high-level helper files

The meaning of “neutral” in this chat was:
- no A3-specific prompt structure logic hidden in AgentFactory,
- no selector/classifier business rules hidden in AgentPrompt,
- no special per-agent wording embedded in neutral helpers,
- anything special should live either in JSON or in the concrete agent.

### 6.2 Practical interpretation reached

The practical interpretation reached in the chat was:

Neutral stack responsibilities:
- config loading,
- validation,
- message composition from generic config and inputs,
- LLM calling,
- parse/validation scaffolding.

Non-neutral responsibilities:
- A3-specific evidence chunk rendering,
- A3-specific user-prompt-under-evaluation construction,
- A3-specific chunk sanitization,
- A3-specific required_output shaping,
- A3-specific deterministic post-processing.

Those non-neutral parts belong in:
- `a3_nli_gate.py`
- and the A3 JSON config.

### 6.3 Why this mattered

This separation mattered for two reasons.

First:
future reuse.
If A3 logic leaks into AgentFactory/AgentPrompt, the whole stack becomes difficult to trust for future agents.

Second:
readability and abstraction.
The user explicitly wanted main high-level files to remain abstract and easy to read, not overloaded with growing per-agent switch logic.

### 6.4 Resulting design principle

The design principle that should be preserved in the next chat is:

Agent Stack is a neutral shell.
A2/A3/A4 specifics belong in agent-local code and JSON.

## 7. Why earlier A3 behavior was considered bad or “BS”

Several earlier A3 behaviors were judged bad during this chat. The reasons are important.

### 7.1 Too much duplication logic

The earlier duplicate-marking behavior was bad because:
- it treated partial overlap as duplication,
- it often declared chunks duplicates when they clearly conveyed different ideas,
- it added too much fragile interpretation burden to A3,
- and manual inspection showed poor quality.

This directly led to duplication removal.

### 7.2 Noisy chunk ids polluted the prompt

Earlier A3 prompts used long real chunk ids.
That added:
- lots of visual noise,
- zero semantic value,
- and possible distraction for the model.

This led to local ids 1..N.

### 7.3 Inner markdown structure could destabilize the prompt

Raw chunk text with `##` and `###` could create prompt-structure ambiguity.
This was correctly recognized as dangerous.
That led to the final heading-sanitization design.

### 7.4 Feeding A2 meta-output into A3 was wrong

At one point the A3 prompt-under-evaluation block contained:
- system-ish labels,
- audience-like labels,
- style language,
- and other upstream meta structure.

This was explicitly rejected.

The correct final rule became:
A3 should see only the real prompt text pieces:
purpose, task, context
without labels and without A2 meta garbage.

This was one of the key prompt improvements.

## 8. A3 prompt-sensitivity findings from the tests

This chat produced several important empirical findings.

### 8.1 Prompt wording changes A3 behavior in meaningful ways

A3 was tested with several different prompt phrasings.
The results showed that even small wording changes meaningfully changed chunk judgments.

This is not surprising in theory, but here it was observed concretely.

### 8.2 “What I have learned lately” attracted self-descriptive/inferred chunks

When the prompt was roughly:
“Explain what I have learned lately, especially in prompt engineering and cloud computing”

A3 was more likely to keep or tolerate:
- self-descriptive chunks,
- inferred-learning chunks,
- style-summary chunks,
- psychologically interpreted or meta-summary chunks.

This was because the phrase “I have learned” semantically invites self-summary.

### 8.3 “Projects done or planned” produced more project-centered behavior

When the prompt became roughly:
“Please explain the projects that were done or planned in prompt engineering and cloud computing”

A3 became more project-oriented.
That test was especially valuable because:
- the old controversial chunk about IAM troubleshooting / working style was no longer the same slot number,
- but the same underlying kind of chunk still moved in judgment,
- and several meta/template chunks were pushed down.

That proved that the new wording changed classifier behavior in a meaningful way.

### 8.4 “What do you know about ...” is more neutral and relevance-oriented

When the prompt became roughly:
“what do you know about prompt engineering and cloud computing”

A3 became more generally relevance-oriented and less tied to:
- “my learning”
- “my projects”
- or “my self-description”

In that run, the controversial self-inference/cloud-workflow chunk still appeared and was labeled useful.
This was not judged catastrophic.
The conclusion was:
it is not junk;
it is secondary relevance, not nonsense.

### 8.5 Important local-id lesson

During comparison of runs, it became clear that:
- local chunk numbers are ephemeral,
- so “chunk 23” in one run may not be “chunk 23” in another,
- therefore identity must always be checked via actual content, not local slot number.

This is important for future debugging.

## 9. Quality judgment of the final A3 behavior reached in this chat

### 9.1 Overall judgment

The final judgment reached in the chat was:
overall, the user was satisfied.

That satisfaction was not because A3 became perfect.
It was because A3 now showed meaningful semantic discrimination.

### 9.2 What was specifically encouraging

The most encouraging observation was:
A3 could discard several high-ranked but semantically weak chunks.

Examples discussed:
- high-ranked generic prompt/template chunks,
- meta-framework text,
- some profile-like or instruction-like chunks.

This means A3 is not just echoing Retrieval/ReRanker.

### 9.3 What still remains imperfect

A3 can still be somewhat generous in some cases.
Certain borderline-useful self-summary or inferred-interest chunks may still survive as useful or borderline.
That is not ideal, but it is not catastrophic.

The final tone in the chat was:
good enough to be satisfied for now,
clearly improved,
still not the final endpoint.

## 10. Startup/performance diagnosis from the final discussion

This is the second major section after A3.

### 10.1 The structural problem

The startup issue is not merely “ColBERT is slow.”
The structural problem identified in the current code path is:

In the UI:
- `AppController()` is created immediately on first page load.

In the controller:
- heavy stage objects are eagerly created during controller initialization.

This means:
- the page cannot become usable before controller initialization finishes,
- and controller initialization already includes heavy stage initialization.

So:
boot path and heavy-model path are mixed together.

### 10.2 Why this feels bad to the user

The result is:
- app appears to “hang” or feel dead,
- even though the problem is not that the app is broken,
- but that first-page readiness is blocked by heavy backend initialization.

That is poor product behavior.

### 10.3 The wrong solution rejected here

A lazy-load-on-first-click approach was discussed and rejected by the user.

Reason:
that only moves the waiting pain from app boot to first reranker use.
The user preferred not to click a reranker button and then suddenly wait a long time.

That objection is valid.

### 10.4 The better solution agreed here

The better design agreed here is:

- UI becomes visible immediately.
- heavy reranker warm-up starts in background,
- reranker-related buttons stay disabled until ready,
- UI shows status such as:
  - loading
  - warming
  - ready

This is the best compromise for the current system.

It avoids both:
- total app boot blocking,
- and unpleasant first-click blocking.

### 10.5 Secondary resource-lifecycle smell

A smaller but related architectural smell was also noted:
heavy helper resources inside ingestion are recreated per action instead of being managed cleanly as reusable resources.

This is not the main startup issue, but it belongs to the same family of lifecycle design problems.

## 11. Files that matter most after this chat

This section lists the most important files conceptually involved in the work discussed here.

### 11.1 Highest priority current-code truth files

1. `ragstream/agents/a3_nli_gate.py`
   - current A3 logic
   - A3 prompt construction
   - A3 local chunk-id mapping
   - A3 sanitization helper
   - A3 deterministic post-processing

2. `data/agents/a3_nli_gate/001.json`
   - current A3 static prompt text
   - current A3 output schema
   - current A3 agent contract

3. `ragstream/orchestration/agent_factory.py`
   - neutral config loading and resolution
   - important after the refactor/fix work

4. `ragstream/orchestration/agent_prompt.py`
   - neutral agent prompt composition/parse behavior

5. `ragstream/orchestration/agent_prompt_helpers/compose_texts.py`
   - neutral helper territory; must remain generic

6. `ragstream/orchestration/superprompt_projector.py`
   - relevant because prompt rendering/projection logic was part of the refactor discussion

7. `ragstream/agents/a2_promptshaper.py`
   - practical A2 agent behavior

8. `data/agents/a2_promptshaper/003.json`
   - current A2 chooser config
   - important because A2 broke and was fixed around this config path

9. `ragstream/app/controller.py`
   - current startup path
   - current eager creation problem
   - current stage wiring
   - current retrieval/reranker instantiation pattern

10. `ragstream/app/ui_streamlit.py`
    - current first-page controller construction
    - current session-state lifecycle
    - button wiring and startup behavior

### 11.2 Practical note

Even if some of these files were not all reprinted at the end of the chat, they were central to the work done here and should be treated as the main code areas to inspect first in any continuation.

## 12. Requirements/UML mismatch notes

This section is critical for the next chat.

### 12.1 Requirements_AgentStack is conceptually useful but structurally older

The current requirements file for Agent Stack is still useful for philosophy and architecture direction, but parts of it are too conceptual or older than the concrete implementation now in play.

Important:
use it as intent/background, not as exact operational truth.

### 12.2 Requirements_RAG_Pipeline still reflects older A3 assumptions

The older pipeline requirement material still speaks in a way that assumes:
- duplicate marking,
- Multi-Chooser-style richer A3 output,
- and older A3 behavior.

Current practical A3 truth after this chat is simpler:
- usefulness classification only,
- no duplication fields,
- local prompt chunk ids,
- XML-like wrapper and sanitized chunk text.

### 12.3 Requirements_Main / Implementation_Status likely underrate A3 maturity

Some docs still imply A3 is placeholder/scaffold or not yet truly implemented.
After this chat, that is no longer a fair description.
A3 is not “finished forever,” but it is now a real functioning stage with meaningful behavior.

### 12.4 UML_AgentStack is outdated relative to current design intent

The UML around Agent Stack reflects an older structural picture and should not be trusted literally for:
- exact method surfaces,
- exact ownership of prompt assembly specifics,
- or exact neutrality boundaries now enforced in this chat.

### 12.5 Architecture and requirements are not fully synchronized with code

This was explicitly recognized in the chat.
So in the next chat, no one should assume:
“requirement says X, therefore current code must still do X.”

For Agent Stack, A2, and A3, code plus this report are more reliable than older documentation.

## 13. Concrete conclusions that must not be lost in the next chat

This is a compact preservation list.

1. A3 is now usefulness-only. Duplication logic was intentionally removed.

2. A3 prompt chunk ids are local ids `1..N`, not real long chunk ids.

3. Local chunk numbers are not stable across runs.

4. A3 prompt feeds only the real prompt text:
   purpose, task, context
   with no labels and no A2 meta garbage.

5. A3 evidence chunks use one outer XML-like structure only.

6. Chunk-internal markdown headings are sanitized to `[H1]`, `[H2]`, `[H3]`, etc.

7. The exact A3 LLM prompt must remain visible in logs/CLI for inspection.

8. Agent Stack must remain neutral.
   A3 specifics belong in A3 code or JSON, not in neutral stack files.

9. A2 is working again after the AgentFactory fix.

10. Current docs/UML are not fully aligned with the current code and recent chat decisions.

11. Startup slowness is structurally caused by eager heavy initialization in the boot path.

12. Preferred startup redesign:
    fast UI boot + background reranker warm-up + disabled dependent buttons until ready.

## 14. Recommended agenda for the next chat

The next chat should start from this report and then do work in this order.

### 14.1 First task: preserve the current truth

Before any further refactor, the next chat should:
- restate the current A3 truth from this report,
- verify the relevant code files,
- and refuse to silently fall back to older requirement assumptions.

### 14.2 Second task: write documentation back into requirements/UML

The next chat should update:
- Requirements_AgentStack
- Requirements_RAG_Pipeline
- maybe Requirements_Main / Implementation_Status
- relevant UML
so they reflect:
- actual A3 usefulness-only design,
- neutrality boundaries,
- current startup/resource-lifecycle understanding.

### 14.3 Third task: implement startup redesign

Then the next chat should redesign startup so that:
- controller boot is cheap,
- heavy reranker resource warms separately,
- UI is visible immediately,
- dependent buttons are disabled until ready.

### 14.4 Fourth task: only then continue deeper reranker work

Only after startup/resource lifecycle is cleaned should further reranker performance tuning continue.
Otherwise it is too easy to confuse:
- model slowness,
- boot-path blocking,
- and warm-up policy.

## 15. Final bottom-line statement

The most important result of this chat is this:

A3 is no longer an abstract or weak placeholder.
It now has a real, much cleaner, much more inspectable design:
- usefulness-only,
- local chunk ids,
- single outer wrapper,
- sanitized inner structure,
- real prompt-text-only input,
- deterministic post-processing,
- and visible logging.

At the same time, the Agent Stack was pushed back toward its intended neutrality.
That is architecturally more important than any single prompt tweak.

And finally, the startup problem is now understood structurally:
the app feels slow because heavy stage initialization is currently mixed into first-page boot.
The agreed better direction is not lazy first-click loading, but:
fast UI boot + background warm-up + ready-state gating.

This report should be carried into the next chat and treated as the current narrative truth until requirements and UML are brought back into sync with code.