# CodeIndexer — Requirements Specification

*Version 1.0 • 2025-08-29*
*Standalone tool for deterministic code indexing (Python & Terraform). Not part of RAGstream.*

---

## 1  Purpose & Scope

CodeIndexer is a deterministic parsing tool that reduces large codebases into lightweight structural outlines.
Its mission is to transform raw Python and Terraform files into compact JSON/Markdown index files that preserve **structure** (modules, classes, functions, variables, resources) without code bodies, so they can be used for architectural reasoning, UML-like views, or feeding into RAG systems without context-window overflow.

---

## 2  Inputs

* Accepts a list of **files** and/or **folders**.
* Recursively scans subfolders.
* Supports:

  * **Python** (`.py`)
  * **Terraform/HCL** (`.tf`, `.tf.json`)

---

## 3  Outputs

* **Primary output:**

  * `code_index.json` — machine-readable structured index.
  * `code_index.txt` — human-readable outline (Markdown or plain text).

* Each entry contains:

  * `path` (relative path of file)
  * `type` (`python` or `terraform`)
  * `elements`: list of structural elements.

---

## 4  Functional Requirements

### 4.1 Python Indexing

| ID    | Requirement                                                                                                       | Priority |
| ----- | ----------------------------------------------------------------------------------------------------------------- | -------- |
| PY-01 | Detect **modules** with their file paths.                                                                         | Must     |
| PY-02 | Capture **imports** (`import`, `from … import …`).                                                                | Must     |
| PY-03 | Extract **top-level constants/variables** (`NAME = literal`).                                                     | Must     |
| PY-04 | Parse all **classes**: name, base classes, decorators, docstring (first line).                                    | Must     |
| PY-05 | Parse all **methods** inside classes: name, decorators, argument signature (args, defaults, `*args`, `**kwargs`). | Must     |
| PY-06 | Parse **module-level functions**: name, decorators, argument signature.                                           | Must     |
| PY-07 | Ignore function/method bodies; only signatures + docstrings.                                                      | Must     |
| PY-08 | Preserve ordering as in source.                                                                                   | Must     |

### 4.2 Terraform Indexing

| ID    | Requirement                                                                                               | Priority |
| ----- | --------------------------------------------------------------------------------------------------------- | -------- |
| TF-01 | Parse Terraform files with HCL v2 parser.                                                                 | Must     |
| TF-02 | Capture **providers**, **variables**, **outputs**, **data blocks**, and **resources**.                    | Must     |
| TF-03 | For each **resource/module**: record type, name, key attributes (`runtime`, `role`, `memory_size`, etc.). | Must     |
| TF-04 | Ignore values/expressions inside blocks; capture keys + identifiers only.                                 | Must     |
| TF-05 | Support `.tf.json` syntax equivalently.                                                                   | Must     |
| TF-06 | Ignore Terraform state files, tfvars, and `.terraform/` dirs.                                             | Must     |

### 4.3 Output Structure

| ID     | Requirement                                                                    | Priority |
| ------ | ------------------------------------------------------------------------------ | -------- |
| OUT-01 | JSON format: deterministic ordering (by path, then element order).             | Must     |
| OUT-02 | TXT format: tree-like outline with indentation (similar to ClamTex UML).       | Must     |
| OUT-03 | Include **signatures** for Python functions/methods.                           | Must     |
| OUT-04 | Include **key attributes** for Terraform resources/modules.                    | Must     |
| OUT-05 | Truncate large argument lists or attribute lists with configurable max length. | Should   |

---

## 5  Non-Functional Requirements

| Category    | Target                                                                                        |
| ----------- | --------------------------------------------------------------------------------------------- |
| Determinism | Always produce the same output for the same source tree.                                      |
| Performance | Indexing of a 10k LOC Python project or 200 Terraform resources completes < 5 s on local CPU. |
| Modularity  | Python and Terraform parsers are pluggable modules.                                           |
| Output Size | `code_index.txt` should remain ≤ 5 MB for very large repos; JSON ≤ 10 MB.                     |

---

## 6  Acceptance Criteria

1. Given a Python file with multiple classes, functions, and constants, the index lists each with signatures.
2. Given a Terraform file with providers, variables, and resources, the index lists each with type, name, and key attributes.
3. Running twice on the same tree produces identical JSON/TXT output (ignoring timestamp).
4. Excluded paths (`.git/`, `.venv/`, `.terraform/`, `*.tfstate*`, etc.) are never included.
5. The outline is parseable by both humans (TXT) and machines (JSON).

---

## 7  Glossary

* **Index**: Abstract structural outline of code/config without bodies.
* **Signature**: Function/method name + arguments.
* **Key Attributes**: Small set of Terraform block attributes (runtime, role, memory, etc.).

