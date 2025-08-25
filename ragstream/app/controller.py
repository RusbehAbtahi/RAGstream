# ragstream/app/controller.py
from .agents.a1_dci import A1_DCI
from .agents.a2_prompt_shaper import A2_PromptShaper
from .agents.a3_nli_gate import A3_NLIGate
from .agents.a4_condenser import A4_Condenser

class AppController:
    def __init__(self, retriever, reranker, prompt_builder, llm_client):
        self.shaper = A2_PromptShaper()
        self.dci = A1_DCI()
        self.gate = A3_NLIGate(theta=0.6)
        self.condenser = A4_Condenser()
        self.retriever = retriever
        self.reranker = reranker
        self.prompt_builder = prompt_builder
        self.llm = llm_client

    def handle(self, user_prompt, named_files, exact_lock):
        shape = self.shaper.propose(user_prompt)          # was suggest(...)
        files = self.dci.build_files_block(named_files, exact_lock)
        kept = []
        if not exact_lock:
            dense = self.retriever.search(user_prompt)
            ranked = self.reranker.rerank(dense, user_prompt)  # keep your own signature consistently
            kept = self.gate.filter(ranked, user_prompt)
        sctx = self.condenser.condense(kept)              # was make_sctx(...)
        prompt = self.prompt_builder.build(user_prompt, files, sctx, shape)
        return self.llm.complete(prompt)
