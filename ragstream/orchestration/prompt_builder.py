"""
PromptBuilder
=============
Assembles the final Super-Prompt from:
  - ❖ FILES (deterministic block by A1)
  - S_ctx (Facts / Constraints / Open Issues by A4)
  - tool_output (if any)
and applies the fixed authority order:
[Hard Rules] → [Project Memory] → [❖ FILES] → [S_ctx] → [Task/Mode]
"""
from typing import List, Optional

class PromptBuilder:
    def build(self, question: str, files_block: str | None, s_ctx, shape=None, tool: str | None = None) -> str:
        # assemble using the authority order from the docs (Hard Rules → Project Memory → ❖ FILES → S_ctx → Task/Mode)
        return "PROMPT"
