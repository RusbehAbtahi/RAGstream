# ragstream/prompt_schema.py
# Purpose: Load prompt schema JSON once and expose it to preprocessing + name matcher.
# Notes:
# - No hashing, no guards. Minimal deterministic accessors only.
# - All fields are kept on this instance; SuperPrompt is NOT modified here.

from __future__ import annotations
from typing import Dict, Set, Optional
import json
import unicodedata
import re

class PromptSchema:
    def __init__(self, json_path: str) -> None:
        self.json_path = json_path
        self.canonical_keys: Set[str] = set()
        self.must_keys: Set[str] = set()
        self.defaults: Dict[str, str] = {}
        self.aliases: Dict[str, str] = {}
        self.bilingual: Dict[str, Dict[str, str]] = {}

        self._load()

    def _load(self) -> None:
        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Minimal fields used at this stage (others ignored on purpose)
        self.canonical_keys = {self.normalize_key(k) for k in data.get("canonical_keys", [])}
        self.must_keys = {self.normalize_key(k) for k in data.get("must_keys", [])}
        self.defaults = {self.normalize_key(k): v for k, v in data.get("defaults", {}).items()}
        self.aliases = {self.normalize_key(k): self.normalize_key(v) for k, v in data.get("aliases", {}).items()}
        self.bilingual = {}
        for lang, mapping in (data.get("bilingual", {}) or {}).items():
            self.bilingual[lang] = {self.normalize_key(k): self.normalize_key(v) for k, v in mapping.items()}

    # Normalization used everywhere: lowercase, NFKC, trim, collapse inner spaces, strip punctuation runs.
    def normalize_key(self, s: str) -> str:
        if not isinstance(s, str):
            return ""
        s = unicodedata.normalize("NFKC", s).lower().strip()
        s = re.sub(r"\s+", " ", s)              # collapse whitespace
        s = re.sub(r"[^\w\s]+", "", s)          # drop punctuation (only for header keys)
        return s

    def is_canonical(self, key: str) -> bool:
        return self.normalize_key(key) in self.canonical_keys

    def to_canonical_or_none(self, key: str) -> Optional[str]:
        nk = self.normalize_key(key)
        if nk in self.canonical_keys:
            return nk
        # alias lookup
        if nk in self.aliases:
            return self.aliases[nk]
        # bilingual lookup
        for _lang, mapping in self.bilingual.items():
            if nk in mapping:
                return mapping[nk]
        return None

    def is_must(self, key: str) -> bool:
        return self.normalize_key(key) in self.must_keys

    def default_for(self, key: str) -> str:
        return self.defaults.get(self.normalize_key(key), "")
