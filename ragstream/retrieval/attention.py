"""
AttentionWeights (legacy shim)
==============================
Kept for legacy tests. In the current design, eligibility is controlled via
ON/OFF per-file toggles and Exact File Lock in the UI, not sliders.
"""
from typing import Dict

class AttentionWeights:
    """No-op weight application kept for backward compatibility."""
    def weight(self, scores: Dict[str, float]) -> Dict[str, float]:
        return scores
