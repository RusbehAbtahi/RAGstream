# Final RAGstream Memory Compression Design

## 1. Document path stays unchanged

Document retrieval remains as it is now:

document chunks  
→ A3  
→ A4  
→ S_CTX_MD

A3/A4 should work on document evidence only.

Semantic memory chunks are no longer mixed into document chunks by default.

---

## 2. ActiveRetrievalBrief stays separate

ActiveRetrievalBrief is injected separately into the final SuperPrompt beside:

Task  
Purpose  
Context  

ActiveRetrievalBrief represents current working-conversation state.

It is not document evidence.  
It is not MemoryMerge source material.  
It is not S_CTX_MD.

MemoryMerge may see ActiveRetrievalBrief only as anti-duplication reference.

Meaning:

Use ActiveBrief to avoid repeating information already present there.  
Do not summarize ActiveBrief again into Memory Context.

---

## 3. Memory path is separate from document path

Memory path becomes:

episodic MemoryRecords  
+ semantic memory chunks  
+ working memory  
+ Direct Recall  
→ MemoryMerge  
→ one final Memory Context

This Memory Context is then injected into the SuperPrompt as memory context.

---

## 4. Episodic memory compression

Memory Retrieval selects up to 3–4 episodic Q/A MemoryRecords.

Each selected Q/A is reduced deterministically using query-aware sentence/window reduction.

Target:

max 400 tokens per selected Q/A

So total episodic input becomes approximately:

3 records → max 1200 tokens  
4 records → max 1600 tokens

The reduction is query-aware:

current user query  
+ Q/A sentence windows  
→ embedding similarity  
→ keep strongest relevant windows  
→ remove redundancy  
→ produce reduced Q/A text

---

## 5. Semantic memory compression input

Memory Retrieval also selects 5 semantic memory chunks.

Each semantic memory chunk is around 1200 characters, but real token counting must be used.

Approximate total:

5 semantic chunks ≈ 1500 tokens

Semantic chunks are memory material and go to MemoryMerge, not A3/A4.

---

## 6. MemoryMerge input

MemoryMerge receives:

reduced episodic Q/A material: about 1200–1600 tokens  
semantic memory chunks: about 1500 tokens  
optional working memory / Direct Recall  
ActiveRetrievalBrief only as anti-duplication reference

So normal MemoryMerge input is around:

2700–3100 tokens before final compression

---

## 7. MemoryMerge output

MemoryMerge produces one coherent final Memory Context.

Target:

max 700 tokens

The output should:

remove duplicated information  
merge overlapping episodes  
preserve only query-useful memory  
preserve durable decisions, corrections, constraints, entities, and rejected interpretations  
avoid repeating what ActiveBrief already says  
stay compact and operational  
not preserve Q/A block structure unless needed

Final result is not:

Episode 1 Q/A  
Episode 2 Q/A  
Episode 3 Q/A  

Final result is:

one synthesized runtime Memory Context

---

## 8. Runtime-only rule

MemoryMerge output is runtime-only.

It must never overwrite:

.ragmem  
.ragmeta.json  
SQLite  
original MemoryRecord input_text/output_text  
memory vectors  

Original Q/A remains the durable truth.

Compressed Memory Context is only prompt injection.

---

## 9. ActiveBrief design already decided

ActiveBrief is generated after durable MemoryRecord save.

It uses:

text-embedding-3-small  
activebrief relevance threshold: 0.25  
pending-topic threshold: 0.25  

Logic:

Q/A relevant to ActiveBrief  
→ update ActiveBrief

Q/A not relevant  
→ copy previous ActiveBrief forward  
→ store Q/A as pending topic

next Q/A matches pending topic  
→ confirmed topic shift  
→ update ActiveBrief with previous brief + pending Q/A + current Q/A

Topic shift must use update route, not init route.

Init route is only for no previous ActiveBrief.

---

## 10. Final SuperPrompt structure

Final SuperPrompt receives separate blocks:

Task  
Purpose  
Context  
ActiveRetrievalBrief  
S_CTX_MD from document A4  
Memory Context from MemoryMerge  

This keeps:

document evidence separate  
memory evidence separate  
conversation state separate  
user request separate