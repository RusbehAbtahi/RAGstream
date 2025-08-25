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


class A2_PromptShaper:
    def propose(self, question: str) -> Dict[str, str]:
        return {"intent": "explain", "domain": "software"}


