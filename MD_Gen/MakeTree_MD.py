#!/usr/bin/env python3
"""
MakeTree_MD.py

Prints a directory tree to the console and writes it to a Markdown file
with a header. Supports filter-dominant and “only” modes for directories
and file patterns.
"""
import os
import fnmatch

# --- CONFIGURATION ---
from pathlib import Path

# Project root = parent of MD_Gen
base_path_obj = Path(__file__).resolve().parent.parent
# Base path for the project tree
base_path=str(base_path_obj)

# Directories (relative to base_path) to include when only_dirs is empty
#include_dirs = [
  #  "ragstream",
   # "01_src",
#]

# Directories to skip always (filter-dominant)
filter_dirs = [
    r"terraform\10_global_backend\.terraform",
    r"XXX",

]

# File patterns to exclude always (filter-dominant)
filter_file_patterns = [
    "*.pyc",
    "*.sh",
]

# Only-mode directories: if non-empty, ignore include_dirs but still apply filter_dirs
only_dirs = [

    r"ragstream",

]

# Only-mode file patterns: if non-empty, ignore filter_file_patterns but still apply filter_file_patterns first
only_file_patterns = [
    "*.py",
    "*.tf",
    "*.yml",
    "*.json",
    "*.hcl",
    "*.txt"

]

# Output Markdown file path
md_output_path = "Project_Tree.md"


class TreeWriter:
    def __init__(self):
        self.lines = []

    def write(self, text: str):
        print(text)
        self.lines.append(text)


def normalize(path: str) -> str:
    """Normalize paths for case-insensitive comparison."""
    return os.path.normcase(os.path.normpath(path))


def is_dir_allowed(rel: str) -> bool:
    """
    Determine if a directory (relative to base_path) is allowed.
    1) Always exclude any directory listed in filter_dirs or under them.
    2) Then, if only_dirs is non-empty, allow only those matching only_dirs.
    3) Otherwise, allow.
    """
    rel_n = normalize(rel)
    # 1) filter-dominant exclusion
    for fd in filter_dirs:
        fd_n = normalize(fd)
        if rel_n == fd_n or rel_n.startswith(fd_n + os.sep):
            return False
    # 2) only-mode inclusion
    if only_dirs:
        return any(
            rel_n == normalize(d) or rel_n.startswith(normalize(d) + os.sep)
            for d in only_dirs
        )
    # 3) allow by default
    return True


def is_file_allowed(name: str) -> bool:
    """
    Determine if a file is allowed.
    1) Always exclude patterns in filter_file_patterns.
    2) Then, if only_file_patterns is non-empty, allow only those matching only_file_patterns.
    3) Otherwise, allow.
    """
    # 1) filter-dominant exclusion
    if any(fnmatch.fnmatch(name, pat) for pat in filter_file_patterns):
        return False
    # 2) only-mode inclusion
    if only_file_patterns:
        return any(fnmatch.fnmatch(name, pat) for pat in only_file_patterns)
    # 3) allow by default
    return True


def print_tree(path: str, writer: TreeWriter, prefix: str = ""):
    """
    Recursively print directory contents starting at path,
    respecting directory and file filters.
    """
    rel = os.path.relpath(path, base_path)
    if not is_dir_allowed(rel):
        return

    items = sorted(os.listdir(path))
    for idx, name in enumerate(items):
        full = os.path.join(path, name)
        # Skip files not allowed
        if os.path.isfile(full) and not is_file_allowed(name):
            continue

        is_last = idx == len(items) - 1
        connector = "└── " if is_last else "├── "
        writer.write(f"{prefix}{connector}{name}")

        if os.path.isdir(full):
            new_prefix = prefix + ("    " if is_last else "│   ")
            print_tree(full, writer, new_prefix)


def make_tree_md():
    """
    Generate the tree, print to console, and write Markdown output.
    """
    writer = TreeWriter()
    # Write base path
    writer.write(base_path)

    # Root-level files (always apply file filter)
    for name in sorted(os.listdir(base_path)):
        full = os.path.join(base_path, name)
        if os.path.isfile(full) and is_file_allowed(name):
            writer.write(f"├── {name}")

    # Choose directories to display: only_dirs takes precedence
    dirs_to_show = only_dirs if only_dirs else include_dirs
    for idx, d in enumerate(dirs_to_show):
        full = os.path.join(base_path, d)
        if not os.path.isdir(full):
            continue
        if not is_dir_allowed(d):
            continue

        is_last = idx == len(dirs_to_show) - 1
        connector = "└── " if is_last else "├── "
        writer.write(f"{connector}{d}")
        prefix = "    " if is_last else "│   "
        print_tree(full, writer, prefix)

    # Write to Markdown file
    with open(md_output_path, "w", encoding="utf-8") as md:
        md.write("# Local Project Tree\n\n")
        md.write("```\n")
        md.write("\n".join(writer.lines))
        md.write("\n```\n")

    print(f"\nMarkdown tree written to: {md_output_path}")


if __name__ == "__main__":
    make_tree_md()
