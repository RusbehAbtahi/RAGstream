"""
LLMClient
=========
Adapter for model calls + cost estimate.
"""
class LLMClient:
    def complete(self, prompt: str) -> str:
        return "ANSWER"
    def estimate_cost(self, tokens: int) -> float:
        return 0.0
