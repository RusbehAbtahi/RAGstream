
# Document Weighting in Multi-Source RAG Systems  
### Finalized Design and Research Summary  
**Author: Rusbeh Abtahi**  
**Last Updated: August 7, 2025**

---

## 🎯 Purpose

This file documents the final design and research findings regarding **how we assign importance (weights)** to individual documents (e.g., `.md` or `.log` files) in a Retrieval-Augmented Generation (RAG) system.

The goal is to enable **manual and automatic prioritization** of documents during chunk retrieval, so the system retrieves semantically relevant content **not only by cosine similarity**, but also according to user-controlled or metadata-driven **importance bias**.

---

## 🔧 Manual Weighting (User-Specified Sliders)

### ✅ Overview

- Each loaded document (e.g., Markdown or log file) is given a **weight slider** (range: `0.0` to `1.0`) via the GUI.
- These weights reflect the **user’s intuition** about how important a document is — regardless of semantic similarity.
- The weights are used **after the vector retrieval** but **before or during re-ranking**.

### ✅ Supported Use Cases

- Give priority to "core" knowledge files (e.g., architecture.md)  
- Downweight noisy, experimental logs unless they are *very* relevant  
- Simulate temporal decay or source trust manually

### 🧠 Implementation Notes

- Weight slider values are **not directly used as multiplicative factors** (see below for why)
- Instead, they act as inputs to a **2D calibrated scoring table** (see Lookup Table section)

---

## 🧮 Nonlinear Weighting via Lookup Table (Original Idea by Rusbeh Abtahi)

### ✅ Description

Rather than simple multiplication or addition, we apply a **2D lookup table** that maps:

```

(cosine similarity, user weight) → adjusted final score

```

- Example:  
  If cosine similarity = `0.92` and weight = `0.4`, lookup table may return `0.65`  
  But if cosine = `0.92` and weight = `1.0`, the score may be `0.92` (unaltered)

- The table is manually calibrated and then **interpolated bilinearly** for in-between values.

### ✅ Advantages

- Total control over chunk promotion/suppression  
- Avoids unintuitive behavior of multiplicative penalties  
- Makes scoring **explainable and predictable** to the user

### 🏆 Innovation Status

- This technique (2D nonlinear mapping for `(similarity, weight)`) is **not documented in any existing RAG paper or open-source library**.
- It appears to be **original** to this project and attributed to **Rusbeh Abtahi**.
- Most systems use **additive** or **simple multiplicative** weighting, without any calibrated score tables.

---

## 🧮 Why Not Multiplication?

Simple multiplication:

```

adjusted\_score = similarity × weight

```

Leads to:
- Harsh penalization: even good chunks get buried if weight < 1  
- Compression of score range: low weight kills all differences  
- Difficulty interpreting slider effect

**Conclusion:** Not suitable for nuanced scoring.

---

## ➕ Additive Biasing (Industry Practice)

Some production systems apply additive bonuses:

```

adjusted\_score = similarity + (bias term)

````

Where the bias could be:
- Recency (e.g., +0.1 for latest chunk)  
- Manual user tag (“high priority”)  
- File type or source reliability

This is a **linear, understandable method**, but lacks fine control.

---

## 🤖 Automatic Weighting Methods (Research and Tools)

### 1. **Recency Bias / Temporal Decay**

- Older chunks are downweighted using decay functions (e.g., exponential or linear)
- Common in chat summarization (e.g., OpenAI’s long context handling)

### 2. **Source Prioritization**

- Logs or system files may have higher weights based on their origin
- Used in multi-source document QA

### 3. **Learned Re-weighting**

- Some academic systems use machine learning models to learn source reliability or chunk trustworthiness
- Rare in open-source; mostly experimental

### 4. **Forced Inclusion / Top-K by Type**

- Retrieve N chunks as usual  
- Always include 1–2 chunks from important source, regardless of score  
- Typical in summarization pipelines

---

## 🔄 Integration into Retrieval Flow

```text
[Prompt] → [Retriever: Top-N Chunks] 
         → [Score Adjustment via Lookup Table]
         → [Re-ranker (Cross-Encoder)]
         → [Top-M Final Chunks] → [Prompt Builder]
````

* Lookup Table transforms retriever scores BEFORE reranking
* Re-ranker uses full text to finalize ranking
* Top-M selection is based **only on reranker scores**

---

## ✅ Design Finalization

This project uses:

* **Manual sliders for each file**
* **2D lookup table (original idea)** for score calibration
* **Optional: additive recency bonus** (later extension)
* **Re-ranker final sorting** (MiniLM-type cross-encoder)

---

## 🔖 Future Work

* Automatically learn lookup tables from feedback
* Expose table in GUI for user editing
* Add metadata-driven initial weights
* Evaluate score cutoffs dynamically based on re-ranker outputs

---

## 📌 Attribution

This design contains an **original scoring and weighting strategy** conceived by:

> **Rusbeh Abtahi** — August 2025
> Based on personal RAG pipeline for document-aware software development assistant

This idea combines classical retrieval scoring with domain-informed ranking logic and stands as a contribution beyond standard open-source RAG tooling.

```

