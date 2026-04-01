# Report 1 — Retrieval implementation status and next step

## 1. Objective

The Retrieval stage has been implemented as the first fully operational document-selection stage of the RAG pipeline. The implemented goal was to transform the current `SuperPrompt` after A2 into a ranked list of relevant document chunks from the active project database, display these chunks in the GUI, and store the result in a structured way for later stages. The overall deployment context remains the existing AWS Docker/nginx/Route53/EBS setup, with persistent runtime data mounted from `/home/ubuntu/ragstream_data` to `/app/data`.  

## 2. What was implemented

A Retrieval Top-K field was introduced in the Streamlit GUI so that the number of retrieved chunks can be selected at runtime. The GUI already uses project-specific document stores, and the active project selector remains the authority for which project database is queried. The stage order remains the same high-level pipeline order: PreProcessing → A2 → Retrieval → ReRanker → A3 → A4 → A5 → Prompt Builder.  

The Retrieval logic itself was implemented as a dedicated `Retriever` class with a single public entry point `run(sp, project_name, top_k) -> SuperPrompt`. The class reads the current `SuperPrompt`, extracts only `task`, `purpose`, and `context` from `sp.body`, splits the resulting retrieval query into overlapping pieces, embeds those pieces, reads all stored chunk vectors from the active project Chroma store, computes a retrieval score for every stored chunk, sorts the results, and writes the ranked result back into the same evolving `SuperPrompt`. The implementation is deterministic and independent from ReRanker and A3.  

## 3. Retrieval scoring and reconstruction

The query is not treated as one undivided string. It is first normalized from the `task`, `purpose`, and `context` fields, and then split using the same chunking culture as ingestion: `chunk_size = 500` and `overlap = 100`. This keeps the prompt side and document side structurally aligned. The embedding model used by the Retriever is `text-embedding-3-large`.  

The scoring method is no longer a simple single-query cosine pass. For each stored chunk, the similarity to all query pieces is computed, and these per-piece similarities are aggregated with LogAvgExp using `τ = 9`. This gives a smoother multi-piece relevance score than a pure maximum while still rewarding strong local matches. The ranked result is then truncated to the selected Top-K.  

Because the Chroma store contains embeddings and metadata rather than the authoritative raw chunk text, the selected chunks are reconstructed from `data/doc_raw/<project>` using the stored metadata fields such as `path` and `chunk_idx`, together with the same chunker used during ingestion. This preserves consistency between ingestion and retrieval. The stable chunk-id convention remains `rel_path::sha256::chunk_idx`.   

## 4. SuperPrompt changes and GUI result

The Retrieval result is now written into the shared `SuperPrompt` state. The selected chunk objects are stored in `base_context_chunks`. The stage view is stored in `views_by_stage["retrieval"]` as ordered triples `(chunk_id, retrieval_score, stage_status)`. The selected order is also copied into `final_selection_ids`, and the stage/history fields are updated accordingly. This makes Retrieval the first stage that produces a concrete ranked context snapshot inside the shared pipeline object.  

A general render method `compose_prompt_ready()` was added to `SuperPrompt`. This method now rebuilds the GUI-visible Super-Prompt from the current object state and appends a `## Related Context` section for retrieval-stage chunk display. This establishes a central path toward unifying prompt rendering later, while still remaining compatible with the earlier PreProcessing and A2 workflow.  

## 5. What was achieved

The implemented result is a complete first-stage Retrieval workflow:

* the active project is selected in the GUI,
* the retrieval depth is selected via Top-K,
* the current A2-shaped `SuperPrompt` is used as the retrieval source,
* the project-specific Chroma store is queried,
* ranked document chunks are reconstructed from raw files,
* the result is stored in `SuperPrompt`,
* and the selected context becomes visible in the Super-Prompt preview.   

This means that the system now has a real end-to-end bridge from prompt shaping to context selection.

## 6. Next step: ReRanker / BERT

The next implementation step is the ReRanker stage. Retrieval is fast and broad, but it is still embedding-based. The ReRanker will take the candidate chunks already selected by Retrieval and refine their order using a cross-encoder model, specifically the BERT-style reranker `cross-encoder/ms-marco-MiniLM-L-6-v2`. The current requirement already defines ReRanker as an independent stage that reads the Retrieval view from `SuperPrompt`, scores each `(Prompt_MD, chunk_text)` pair, and writes a new reranked stage view back into `SuperPrompt`. 

## 7. AWS instance choice for the next stage

The current deployment guide records the AWS environment as `eu-central-1`, Ubuntu 24.04, Docker, nginx, and persistent EBS-backed runtime storage mounted under `/home/ubuntu/ragstream_data`. This deployment structure remains unchanged. Only the EC2 compute instance is planned to be upgraded from `t3.small` to `m7i-flex.xlarge`. EBS, Docker, nginx, Route53, TLS, and the runtime data mount remain unchanged.  

The reason for this instance change is the upcoming ReRanker stage. Public on-demand Linux reference pricing as of 2026-03-16 shows `t3.small` at `$0.0208/hour` and `m7i-flex.xlarge` at `$0.1915/hour`, which is about `9.2×` higher compute cost. The selected `m7i-flex.xlarge` provides 4 vCPUs and 16 GiB RAM, which is much closer to the local laptop class and therefore much better aligned with the desired reranking performance target. ([Economize Cloud][1])

---

# Report 2 — Theory of Naive RAG and BERT ReRanking with the NVH example

## 1. Example pair

Prompt:

`What is NVH?`

Chunk:

`nvh contains noise vibration harshness in vehicle`

The purpose of this report is to preserve the intuition of both methods:

* how Naive RAG turns a whole prompt or chunk into one vector,
* how BERT-style reranking scores a prompt/chunk pair directly,
* and how the Python code conceptually looks in both cases.

## 2. Naive RAG: the outer Python view

In the current RAGstream code, the “make this text into one vector” step is conceptually handled by the embedding interface:

```python
from ragstream.ingestion.embedder import Embedder

embedder = Embedder(model="text-embedding-3-large")

prompt_vec = embedder.embed(["What is NVH?"])[0]
chunk_vec  = embedder.embed(["nvh contains noise vibration harshness in vehicle"])[0]
```

This is the important practical fact: the Python code sends the whole text string to the embedding model and receives one embedding vector back. The model used in the current Retriever is `text-embedding-3-large`, and OpenAI’s embedding endpoint returns a vector representation for each input text. The current project wrapper `Embedder.embed(texts)` does exactly that.   ([OpenAI Plattform][2])

After that, a similarity score is computed between the final prompt vector and the final chunk vector. In the current Retriever, cosine similarity is implemented by normalizing vectors and using the matrix product `A_norm @ Q_norm.T`. OpenAI’s current embeddings FAQ also states that cosine similarity is the recommended metric, and because the embeddings are length-normalized, cosine similarity is effectively a dot product after normalization.  ([OpenAI Help Center][3])

## 3. Naive RAG: the inner conceptual model

The important point is that the outer Python call does not manually compute “token vectors then mean.” That work is hidden inside the embedding model. Conceptually, the process looks like this:

1. tokenize the text,
2. assign each token an initial vector,
3. let tokens interact through transformer attention layers,
4. produce context-aware token vectors,
5. pool those contextual token vectors into one final text vector.

So the outer code is simple, but the internal model is not simple averaging from raw token vectors. OpenAI describes embeddings as a vector representation of a piece of text and returns one embedding vector per input string. ([OpenAI Plattform][4])

## 4. Naive RAG with tiny 2D toy vectors

To preserve intuition, a toy 2D example is useful.

Chunk tokens:

* `nvh = [0.90, 0.80]`
* `contains = [0.20, 0.10]`
* `noise = [0.80, 0.70]`
* `vibration = [0.85, 0.75]`
* `harshness = [0.82, 0.72]`
* `in = [0.10, 0.05]`
* `vehicle = [0.40, 0.60]`

Now suppose the token `nvh` attends to the other words with weights

* `0.25, 0.05, 0.20, 0.20, 0.20, 0.03, 0.07`

Then the updated vector for `nvh` is the weighted sum

[
nvh' =
0.25[0.90,0.80] +
0.05[0.20,0.10] +
0.20[0.80,0.70] +
0.20[0.85,0.75] +
0.20[0.82,0.72] +
0.03[0.10,0.05] +
0.07[0.40,0.60]
]

[
nvh' = [0.760,; 0.6825]
]

This means that the token `nvh` is no longer isolated. It now carries information from `noise`, `vibration`, `harshness`, and `vehicle`.

Now assume the final contextual token vectors for the whole chunk become:

* `nvh' = [0.76, 0.68]`
* `contains' = [0.58, 0.52]`
* `noise' = [0.78, 0.70]`
* `vibration' = [0.80, 0.72]`
* `harshness' = [0.79, 0.71]`
* `in' = [0.50, 0.46]`
* `vehicle' = [0.62, 0.60]`

A simple conceptual pooling step is then:

[
chunk_vector =
\frac{
[0.76,0.68] + [0.58,0.52] + [0.78,0.70] + [0.80,0.72] + [0.79,0.71] + [0.50,0.46] + [0.62,0.60]
}{7}
]

[
chunk_vector = [0.69,; 0.627]
]

This is not the exact OpenAI internal algorithm, but it is the right mental model: contextual token vectors are produced first, and then the model returns one fixed-size vector for the whole text. The current OpenAI embeddings documentation explicitly shows that one input string becomes one output embedding vector. ([OpenAI Plattform][4])

## 5. Naive RAG similarity step

Once a single vector exists for the prompt and for the chunk, the similarity step is easy.

Conceptual Python:

```python
import numpy as np

def cosine_similarity(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
```

Then:

```python
score = cosine_similarity(prompt_vec, chunk_vec)
```

In the current Retriever, the same idea is used in matrix form: vectors are normalized and multiplied to produce cosine similarities between all stored chunk vectors and all query-piece vectors. 

## 6. BERT reranking: the outer Python view

For BERT-style reranking, the Python interface is conceptually different. The model is not asked to embed one text independently. Instead, it takes the prompt and the chunk together as one pair and returns one relevance score.

Conceptual Python:

```python
from sentence_transformers import CrossEncoder

model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2")

score = model.predict([
    ("What is NVH?", "nvh contains noise vibration harshness in vehicle")
])[0]
```

This is the core difference. A CrossEncoder does not return one embedding per sentence. It takes exactly two texts as input and predicts one score for the pair. The Sentence Transformers CrossEncoder documentation states this explicitly and documents `.predict()` as the main inference method for sentence pairs. ([SentenceTransformers][5])

## 7. BERT reranking: what happens mathematically

The pair is packed together conceptually like this:

`[CLS] what is nvh ? [SEP] nvh contains noise vibration harshness in vehicle [SEP]`

Every token gets an initial vector. Then transformer self-attention is computed across the whole combined sequence. That means prompt tokens can directly attend to chunk tokens, and chunk tokens can directly attend to prompt tokens.

A toy example for one prompt token, `nvh`, is enough to preserve the idea.

Assume:

* `Q_nvh = [1.0, 0.5]`

and some chunk keys:

* `K_noise = [0.9, 0.4]`
* `K_vibration = [0.95, 0.45]`
* `K_harshness = [0.92, 0.43]`
* `K_vehicle = [0.3, 0.8]`

Attention scores come from inner products:

[
score(nvh, noise) = Q_{nvh} \cdot K_{noise} = 1.0 \cdot 0.9 + 0.5 \cdot 0.4 = 1.1
]

[
score(nvh, vibration) = 1.0 \cdot 0.95 + 0.5 \cdot 0.45 = 1.175
]

[
score(nvh, harshness) = 1.0 \cdot 0.92 + 0.5 \cdot 0.43 = 1.135
]

[
score(nvh, vehicle) = 1.0 \cdot 0.3 + 0.5 \cdot 0.8 = 0.7
]

These raw scores are softmaxed into attention weights. Suppose they become:

* `noise: 0.26`
* `vibration: 0.29`
* `harshness: 0.27`
* `vehicle: 0.18`

Then the new meaning vector for `nvh` becomes the weighted sum of value vectors:

[
new_nvh =
0.26V_{noise} + 0.29V_{vibration} + 0.27V_{harshness} + 0.18V_{vehicle}
]

So the prompt token `nvh` learns that it is strongly related to `noise`, `vibration`, and `harshness`. This is exactly the behavior that makes the pair semantically understandable even if the wording is not identical.

The same process happens for all tokens, across multiple transformer layers. The original BERT/Transformer mechanism is based on Query/Key/Value attention and repeated layer-wise refinement, not on a single cosine comparison. ([SentenceTransformers][5])

## 8. BERT final score

At the end of the network, the model produces one pair-level representation, usually associated with the `[CLS]` token or an equivalent classifier representation. A small final layer maps that representation to one scalar relevance score.

Toy example:

Assume the final `[CLS]` representation is

[
h_{CLS} = [1.2, -0.4, 0.9]
]

and the final linear head is

[
w = [0.7, -0.2, 0.5], \quad b = 0.1
]

Then the final score is:

[
s = w \cdot h_{CLS} + b
]

[
s = 0.7 \cdot 1.2 + (-0.2) \cdot (-0.4) + 0.5 \cdot 0.9 + 0.1
]

[
s = 1.47
]

That scalar is the reranking score.

The Python-level meaning is simple:

```python
score = model.predict([(prompt, chunk)])[0]
```

The mathematical meaning is not simple cosine similarity; it is a learned nonlinear function of token-to-token interactions across the entire prompt/chunk pair. ([SentenceTransformers][5])

## 9. The short comparison to remember after 3 months

Naive RAG:

* whole prompt goes into an embedding model,
* whole chunk goes into the same embedding model,
* one vector comes out for each text,
* cosine similarity compares those two final vectors.

Conceptual Python:

```python
prompt_vec = embedder.embed([prompt])[0]
chunk_vec  = embedder.embed([chunk])[0]
score = cosine_similarity(prompt_vec, chunk_vec)
```

The “text to single vector” step is handled by the embedding model itself. In the current RAGstream project, this is exposed through `Embedder.embed(...)`.  ([OpenAI Plattform][4])

BERT reranking:

* prompt and chunk are packed together as one pair,
* token-level attention runs across both texts jointly,
* the network produces one scalar relevance score for the pair.

Conceptual Python:

```python
model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2")
score = model.predict([(prompt, chunk)])[0]
```

This is why Retrieval is fast and broad, while ReRanker is slower but much more precise. The current project requirement already fixes ReRanker as a separate cross-encoder stage after Retrieval.  ([SentenceTransformers][5])

[1]: https://www.economize.cloud/resources/aws/pricing/ec2/t3.small/?utm_source=chatgpt.com "t3.small pricing: $15.1840 monthly - AWS EC2"
[2]: https://platform.openai.com/docs/models/text-embedding-3-large?utm_source=chatgpt.com "text-embedding-3-large Model | OpenAI API"
[3]: https://help.openai.com/en/articles/6824809-embeddings-frequently-asked-questions%3F.iso?utm_source=chatgpt.com "Embeddings FAQ | OpenAI Help Center"
[4]: https://platform.openai.com/docs/guides/embeddings/embedding-models%20.class?utm_source=chatgpt.com "Vector embeddings - OpenAI API"
[5]: https://www.sbert.net/docs/package_reference/cross_encoder/cross_encoder.html?utm_source=chatgpt.com "CrossEncoder — Sentence Transformers documentation"
