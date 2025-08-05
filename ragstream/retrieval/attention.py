"""
AttentionWeights
================
Applies user-controlled slider weights to raw similarity scores.
"""
from typing import Dict

class AttentionWeights:
    """Holds per-document weights (0-1) and applies them to similarity scores."""
    def weight(self, scores: Dict[str, float]) -> Dict[str, float]:
        """Return re-weighted scores (dummy implementation)."""
        return scores
