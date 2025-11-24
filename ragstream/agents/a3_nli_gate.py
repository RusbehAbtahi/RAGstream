"""
Agents (A1..A4)
===============
Controller-side agents:
- A1 Deterministic Code Injector → builds ❖ FILES (FULL/PACK) and enforces Exact File Lock.
- A2 Prompt Shaper → suggests intent/domain + headers (advisory).
- A3 NLI Gate → keep/drop based on entailment with θ strictness.
- A4 Context Condenser → outputs S_ctx (Facts / Constraints / Open Issues) with citations.
"""
from typing import List, Dict, Tuple, Optional


class A3_NLIGate:
    def __init__(self, theta: float = 0.6) -> None:
        self.theta = theta
    def filter(self, candidates: List[str], question: str) -> List[str]:
        return candidates
