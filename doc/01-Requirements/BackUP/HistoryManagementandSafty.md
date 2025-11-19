# History Mamangement

## 1) Purpose & Scope

We add a two-layer Conversation Memory beside A1–A4 and your fixed authority order to keep answers “in the flow” without letting stale or duplicate content creep in. This plan is optimized for programming workflows (Python, Terraform, config files) with tight token budgets and fast turnaround.

## 2) Layers at a Glance

* Layer G — Short-term window (always-keep): Always include the last k user–assistant turns verbatim (k≈3–5). This mirrors human working memory and guarantees immediate continuity even if the new question looks off-topic.
* Layer E — Episodic store (selective): Older turns are stored with metadata and are only pulled in when they genuinely help the current question.

## 3) Metadata (what we stamp on every stored item)

* Turn distance n (how many turns ago it was said).
* Optional real-time gap Δt (only used when there’s a long break between sessions).
* Topic tags/keywords (derived from the turn).
* Importance flag i∈\[0,1] (manual “mark as important” or auto-promoted if reused often).
* Source: chat vs static (file path if it references a file).
* Version hints: filename/path, and when available, doc/file mtime or hash.

## 4) Selection Policy (plain rules, no math)

* Guaranteed recency: Always pass Layer G (the last k turns). No exceptions.
* Relevance first: From Layer E, search by topic/semantic match with the new question and propose only clearly related candidates.
* Soft preference for freshness: Prefer nearer turns over far-old ones, but do not drop a very relevant old item just because it’s old.
* Importance can override: If an item is tagged important (e.g., a decided requirement/API contract), it’s eligible even if older.
* Smooth keep/drop: Borderline items transition in/out smoothly (no hard jumpy thresholds).
* Token budget first: Include fewer, higher-value items rather than many weak ones.

## 5) Canonical Sources & Deduplication (A1 + A3 rules)

* A1 (Deterministic Code Injector) is canonical for files: If ❖ FILES injects a named file, treat that as the source of truth for that file during this turn.
* A3 (NLI Gate) acts as semantic bouncer:

  * Drop chat fragments that duplicate or partially overlap anything in ❖ FILES.
  * When two near-duplicates exist (e.g., a static snippet vs a chat snippet), keep the newer by metadata. If a file was explicitly injected by A1 in this turn, that file wins over chat duplicates.
  * Resolve conflicts by recency and authority: explicit ❖ FILES > newer item > older item.

## 6) How Layer E decides what to add (in words)

* Start from the candidate set that looks on-topic with the new question.
* Keep if “very new” OR “very on-topic” OR “marked important.”
* If two candidates say almost the same thing, keep the one that is newer (by turn distance or by file mtime/hash when applicable).
* If a candidate overlaps with ❖ FILES for the same path/content, drop the candidate (avoid echoes).
* Respect a fixed token budget for E; if over, trim weakest first (least relevant, oldest, not important).

## 7) Handling “chat updates vs static files”

* If you said something new in chat that updates a requirement but the static file still has the old version, prefer the newer chat update for this turn.
* Once the static file is updated and re-ingested, the updated file becomes canonical again via ❖ FILES.
* Until that happens, A3 suppresses static snippets that conflict with your newer chat update (to prevent mixed signals).

## 8) Long Dialogues (compression strategy)

* Roll very old spans into short, titled summaries (coverage notes of which turns they replace).
* Promote summaries that keep getting selected (they gain “importance”), so the system can recall long-range facts without rehydrating raw turns.
* Do not summarize recent spans (those live in G).

## 9) Recency model (concept, not math)

* Primary recency is “how many turns back” (turn distance). That’s stable and predictable.
* Optional real-time damping only kicks in if there’s a big pause between sessions (e.g., you left for a day). This prevents an old point from feeling “too fresh” just because few turns passed.
* Recent always wins ties unless an older item is both crucial and clearly on-topic.

## 10) Importance model (who defines it)

* Manual: You (or the UI) can mark a message “important” (e.g., final decision, requirement delta, API schema, contract).
* Automatic: The system gently promotes items that get reused repeatedly (selected often across turns). Promotion is gradual, not jumpy.

## 11) Operational defaults for programming workloads

* Default Exact File Lock: ON when you want laser-focused code work (A1 injects named files; retrieval off).
* When unlocked, retrieval happens but A3 aggressively drops anything overlapping with ❖ FILES.
* Always carry G (last k turns) to preserve your coding flow (notes, last stack traces, last decisions).

## 12) Logging, Transparency, and Controls

* GUI shows what was kept and why (e.g., “kept: recent window,” “kept: strong topical match,” “dropped: duplicate of ❖ FILES,” “dropped: older near-duplicate”).
* Knobs (conceptual): k (size of G), overall token budget for E, strictness of duplicate suppression, and whether real-time gaps should reduce freshness.
* Lightweight metrics: kept\_count, dropped\_duplicates, dropped\_old, reused\_items, and approximate token cost.

## 13) Acceptance Criteria (what “good” looks like)

* Continuity: Answers always reflect the last k turns even if the new question looks unrelated.
* No echoing: When a file is injected, chat fragments of the same file don’t show up.
* Freshness: Among near-duplicates, the newer one appears.
* Relevance: Older content only resurfaces when clearly on-topic or marked important.
* Brevity: Kept context stays within budget without losing essential facts.

## 14) Risks & Mitigations (kept simple)

* Risk: Old but highly relevant content is missed. Mitigation: allow “either very on-topic or very recent” to pass, plus manual importance tags.
* Risk: Conflicts between chat and files. Mitigation: explicit ❖ FILES wins this turn; prefer newer in ties; surface conflicts in the transparency panel.
* Risk: Token bloat from summaries. Mitigation: promote only compact summaries that proved useful; prune stale ones.

## 15) “What we are NOT doing”

* No hard, jumpy thresholds that flip behavior suddenly.
* No mixing code analysis through history when A1 can inject full files deterministically (history code fragments are suppressed when a file is present).
* No complicated math surfaces in the UI; rules are shown in plain language.


# RAGstream – Missing Safety Elements (Guardrails, Brakes, Airbags)

## 1. Guardrails (Policy / Boundaries)
- **Prompt-injection checks** missing (retrieved text could tell LLM to ignore rules).
- **Schema validation** not enforced (A4 must always output `Facts / Constraints / Open Issues`; ❖FILES block must always start with header).
- **Token/cost hard stops** not implemented (spec says ≤ 8k tokens, but no controller-level refusal).

## 2. Brakes (Timeouts / Retries)
- Only LLM retries and PyTool timeout planned.  
- **No controller-level timeouts** (retriever/reranker/condenser could hang indefinitely).
- **No global cancellation** if an agent stalls.
- **No backoff policy** beyond LLM calls.

## 3. Airbags (Fallbacks / Graceful Degradation)
- Current fallback = manual: Super-Prompt preview + Exact File Lock (human override).  
- **No automatic fallbacks**:
  - If A4 fails → fallback to raw reranked chunks.  
  - If retrieval fails → fallback to ❖FILES-only.  
  - If LLM call fails → retry with smaller model.  
- **No rollback** to previous working snapshot if audit fails.
