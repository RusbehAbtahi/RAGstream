# A3 Model Experiments and Intelligent Ingestion Notes

## Purpose

This note documents the recent A3 experiments on model choice, chunk judgment quality, and the conclusion that the next main improvement should come from smarter ingestion and chunk representation, not only from stronger models.

---

## 1. Context

The tested A3 task was:

- classify reranked chunks as `useful`, `borderline`, or `discarded`
- assign one global `selection_band`
- prepare a synthesis-ready working set for downstream answering

The concrete prompt used in the main test was about character and mind-process management, using chunks mainly from cognitive-profile-related files, mixed with some unrelated prompt/template material.

---

## 2. Models discussed and tested

Main serious candidates:
- `gpt-4o-mini`
- `gpt-4.1-mini`
- `gpt-5-mini`

Cheap experimental model also tested:
- `gpt-5-nano`

---

## 3. Main result

The experiments showed that a cheaper model can perform as well as, or even better than, a more expensive one for this specific A3 classification task.

### `gpt-5-nano`
Result: too weak for the current A3 setup.

Observed problems:
- weak discrimination
- collapse into vague labeling
- outputs such as `selection_band: unknown`
- tendency toward nearly-all-borderline behavior

Conclusion:
`gpt-5-nano` is below the reliability threshold for this A3 configuration.

### `gpt-4.1-mini`
Result: strong model, but in this task it often behaved too generously.

Observed problems:
- too many chunks promoted to `useful`
- global `selection_band` pushed too easily toward `high`

Conclusion:
`gpt-4.1-mini` is capable, but in the tested A3 setup its calibration was softer than desired.

### `gpt-4o-mini`
Result: surprisingly good for this task.

Observed behavior:
- set `selection_band` to `medium` in a case where `medium` was more realistic than `high`
- produced a more discriminative spread than weaker models
- still made some local mistakes, but the global judgment was closer to the intended behavior

Conclusion:
For this exact A3 setup, `gpt-4o-mini` looked like the best cost-performance candidate among the tested models.

Important note:
This does not mean `gpt-4o-mini` is generally better than `gpt-4.1-mini`.
It means that in this specific A3 prompt + chunk representation + rule setup, it behaved better.

---

## 4. Main limitation discovered

The main remaining errors are not explained only by model intelligence.

The larger issue is chunk representation.

A key example was one problematic chunk that looked semantically related on the surface, but actually belonged to another task frame. Because the chunk was shown out of its original document/task context, it could easily be judged as relevant even though it was globally wrong.

This means:

- the model may judge local wording correctly
- but still fail the global relevance judgment
- because the chunk has lost its parent context

Conclusion:
The current ceiling is not only model quality.
The bigger issue is representation quality.

---

## 5. Main strategic conclusion

The next quality jump should not come mainly from buying a stronger model.

It should come from making ingestion and architecture smarter.

The main direction that emerged from the discussion was:

- smarter splitting
- better preservation of parent context
- richer chunk metadata
- better source and role awareness

---

## 6. Intelligent ingestion

The working idea is:

Intelligent ingestion = chunking that preserves meaning, context, and role.

A chunk should not be treated as anonymous text only.
It should carry structured information about what it is and where it comes from.

### Metadata dimensions discussed
At minimum, each chunk should ideally carry:

- source file name
- document type
- heading path / section path
- section role
- parent document id
- chunk order
- whether the chunk is, for example:
  - example
  - template
  - prompt instruction
  - actual knowledge
  - CV/profile material
  - future plan / roadmap
  - reflection / commentary

Reason:
If A3 knows that a chunk is an example, template, prompt instruction, or actual knowledge statement, it can judge it much more accurately.

This was one of the strongest conclusions of the discussion.

---

## 7. Smarter splitting

Naive splitting can destroy:

- task frame
- example boundaries
- heading meaning
- relation to surrounding text
- whether a fragment is descriptive, instructional, or evidential

This was directly relevant to the observed chunk-classification mistakes.

The conclusion was that splitting should preserve more context, especially around headings, examples, and section roles.

---

## 8. Knowledge map / knowledge graph direction

A deeper idea discussed was that metadata is only the first layer.

There may be a richer structure beyond plain tags.

### Metadata layer
Descriptive labels attached to chunks.

### Knowledge map layer
A more organized hierarchy of:
- topic families
- document classes
- section classes
- category structure

### Knowledge graph layer
Possible relations such as:
- `example_of`
- `continuation_of`
- `section_of`
- `duplicate_of`
- `derived_from`
- `supports`
- `contradicts`

Practical conclusion from the discussion:
the immediate value is in stronger metadata and document-role awareness.
A full graph may be interesting later, but the current need is first to preserve chunk identity and role.

---

## 9. Human feedback layer

Another important idea was human correction.

Example:
if repeated testing shows that certain chunks are bad, secondary, or misleading, the system should be able to remember that pattern.

This was discussed as more realistic than jumping directly to fine-tuning.

Examples of useful human feedback:
- this chunk is not good for this type of question
- this chunk is secondary
- this chunk type is usually example-only
- this file type should be lower priority for this task family

Conclusion:
A lightweight correction memory was seen as more practical than full fine-tuning at this stage.

---

## 10. A3 prompt / rule insight

The experiments also suggested that too many hard rules can become noisy.

One important improvement was to make the logic more orthogonal:

- local chunk label = `useful / borderline / discarded`
- global set label = `selection_band`

Another important clarification was:

- `useful` should mean both relevant and meaningfully additive
- chunks with the same meaning should not both be promoted unless they genuinely complement each other
- `medium` should be the normal center of gravity unless the set is clearly strong or clearly weak

This refinement improved the setup more than simply making the prompt longer.

---

## 11. Practical pipeline decisions discussed

### A. Retrieval / A3 size
A concrete direction discussed was:

- retrieval / rerank candidate band: 30
- A3 input set: 20

Reason:
The tail of the 30 often contains too much overlap, continuation fragments, and secondary material.
Reducing A3 input from 30 to 20 may reduce noise without losing the useful core.

### B. Optional slow components
Another practical conclusion was that if A3 already performs strong semantic filtering, then slow retrieval components such as SPLADE and ColBERT may become optional rather than mandatory.

This led to the idea of having:
- a faster mode
- and a fuller quality mode

The key point was not the exact final architecture, but the recognition that A3 is already strong enough to justify rethinking the earlier dependence on slower stages.

---

## 12. Main architectural insight

The project has reached a more mature stage.

Earlier, the main question was:
Which model is strong enough?

Now the more important question is:
How should information be represented so that even a medium-cost model can judge correctly?

This is a real shift in the project.

The bottleneck is moving from raw model strength toward:
- ingestion quality
- context preservation
- metadata
- source identity
- structural role
- and correction memory

---

## 13. Final conclusion

The experiments support the following conclusions:

- cheap does not automatically mean too weak
- `gpt-5-nano` was too weak for this A3 task
- `gpt-4.1-mini` was capable but often too generous in this setup
- `gpt-4o-mini` gave the best practical balance in this experiment
- the next real quality jump should come less from model upgrades and more from:
  - intelligent ingestion
  - better splitting
  - metadata-rich chunks
  - stronger provenance / section-role awareness
  - and lightweight human correction

## Final strategic statement

The project is moving from “find a better model” toward “build a smarter representation and retrieval system.”

That appears to be the correct next phase.