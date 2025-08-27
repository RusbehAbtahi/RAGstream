"""
ConversationMemory (read-only)
==============================
Two-layer history:
- Layer-G: recency window (last k turns), always available.
- Layer-E: episodic store with metadata (on-topic, soft fading).
Not part of the document store; no embeddings/retrieval.
"""
from typing import List, Tuple

class ConversationMemory:
    def __init__(self, k_default: int = 5) -> None:
        self.k_default = k_default
        self.soft_fading = True
        self.conflict_policy = "FILES>newer>older"

    def get_recent(self, k: int | None = None) -> List[Tuple[str, str]]:
        return []

    def get_episodic(self) -> List[Tuple[str, str]]:
        return []
