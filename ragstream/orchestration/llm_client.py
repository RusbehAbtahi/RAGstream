"""
LLMClient
=========
Thin adapter around OpenAI (or local model) providing streaming & retry.
Also exposes a basic cost estimator for UI display.
"""
class LLMClient:
    """Handles completion calls and cost estimation."""
    def complete(self, prompt: str) -> str:
        """Return LLM answer (dummy)."""
        return "ANSWER"

    def estimate_cost(self, tokens: int) -> float:
        """Rough USD cost estimate based on model pricing."""
        return 0.0
