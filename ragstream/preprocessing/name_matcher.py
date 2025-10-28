# ragstream/name_matcher.py
# Purpose: Deterministic header → canonical key resolution.
# Methods USED at this stage ONLY:
#   1) exact canonical
#   2) alias
#   3) bilingual
# NO edit-distance, NO templates/cues, NO LLM here (kept for later).

from __future__ import annotations
from typing import Optional, Tuple
from .prompt_schema import PromptSchema

class NameMatcher:
    def __init__(self, schema: PromptSchema) -> None:
        self.schema = schema

    def resolve(self, raw_header: str) -> Tuple[Optional[str], str]:
        """
        Returns (canonical_key | None, method)
        method ∈ {"canonical","alias","bilingual","unknown"}
        """
        # 1) canonical
        if self.schema.is_canonical(raw_header):
            return (self.schema.normalize_key(raw_header), "canonical")

        # 2) alias
        nk = self.schema.normalize_key(raw_header)
        if nk in self.schema.aliases:
            return (self.schema.aliases[nk], "alias")

        # 3) bilingual
        for _lang, mapping in self.schema.bilingual.items():
            if nk in mapping:
                return (mapping[nk], "bilingual")

        # 4) unknown
        return (None, "unknown")
