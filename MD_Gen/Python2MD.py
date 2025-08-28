#!/usr/bin/env python3
import os
import json

# === Configuration ===
# Absolute path to your project root
PROJECT_ROOT = r"C:\0000\Prompt_Engineering\Projects\GTPRusbeh\RAGstream2"

# Base package to scan
PACKAGE_BASE = os.path.join(PROJECT_ROOT, "ragstream")

# Subdirectories (relative to PACKAGE_BASE) to include
SUBDIRS = [
    "app",
    "config",
    "ingestion",
    "orchestration",
    "retrieval",
    "memory",
    "utils",
]

# Output files (next to this script by default)
SCRIPT_DIR = os.path.dirname(__file__) if "__file__" in globals() else os.getcwd()
OUTPUT_MD = os.path.join(SCRIPT_DIR, "ragstream_python.md")
OUTPUT_JSON = os.path.join(SCRIPT_DIR, "ragstream_python.json")


def generate_python_md(
    project_root: str = PROJECT_ROOT,
    package_base: str = PACKAGE_BASE,
    subdirs: list = SUBDIRS,
    output_md: str = OUTPUT_MD,
    output_json: str = OUTPUT_JSON,
):
    """
    Recursively scans ragstream/<subdir> for .py files (excluding __init__.py),
    writes a Markdown document with headings + code blocks, and creates a JSON
    index of '~\\...' paths where '~' represents the project root.
    """
    md_lines = ["# Python Files Index (ragstream)", ""]
    json_index = []

    # Ensure package base exists
    if not os.path.isdir(package_base):
        raise SystemExit(f"Package base not found: {package_base}")

    # For each requested subdir, walk recursively
    for rel_sub in subdirs:
        abs_dir = os.path.join(package_base, rel_sub)
        if not os.path.isdir(abs_dir):
            # Skip missing folders silently
            continue

        # Directory heading (absolute path for clarity, like your original)
        md_lines.append(f"## {abs_dir}")
        md_lines.append("")

        # Walk recursively, deterministic order
        for root, dirs, files in os.walk(abs_dir):
            dirs.sort(key=lambda d: d.lower())
            files = [f for f in files if f.endswith(".py") and f != "__init__.py"]
            files.sort(key=lambda f: f.lower())

            for fname in files:
                full_path = os.path.join(root, fname)

                # Build tilde-prefixed Windows-style relative path for JSON and headings
                rel_path = os.path.relpath(full_path, project_root).replace(os.sep, "\\")
                tilde_path = f"~\\{rel_path}"
                json_index.append(tilde_path)

                # File heading shows the path (clearer than just filename when recursive)
                md_lines.append(f"### {tilde_path}")
                md_lines.append("```python")
                with open(full_path, "r", encoding="utf-8") as f:
                    for line in f:
                        md_lines.append(line.rstrip("\n"))
                md_lines.append("```")
                md_lines.append("")

        md_lines.append("")  # blank line between subdir sections

    # Write Markdown
    with open(output_md, "w", encoding="utf-8") as md_file:
        md_file.write("\n".join(md_lines))

    # Write JSON index
    with open(output_json, "w", encoding="utf-8") as json_file:
        json.dump(json_index, json_file, indent=2, ensure_ascii=False)

    print(f"Markdown written to: {output_md}")
    print(f"JSON index written to: {output_json}")


if __name__ == "__main__":
    generate_python_md()
