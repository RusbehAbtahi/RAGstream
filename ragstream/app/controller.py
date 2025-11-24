# -*- coding: utf-8 -*-
from __future__ import annotations

from ragstream.orchestration.super_prompt import SuperPrompt
from ragstream.preprocessing.prompt_schema import PromptSchema
from ragstream.preprocessing.preprocessing import preprocess

from ragstream.orchestration.agent_factory import AgentFactory
from ragstream.orchestration.llm_client import LLMClient
from ragstream.agents.a2_promptshaper import A2PromptShaper


class AppController:
    def __init__(self, schema_path: str = "ragstream/config/prompt_schema.json") -> None:
        """
        Central app controller.

        - Loads PromptSchema once (for PreProcessing) from the same path
          you used in your original working version.
        - Creates a shared AgentFactory + LLMClient.
        - Creates the A2PromptShaper agent.
        """
        # PreProcessing schema (OLD, working behaviour)
        self.schema = PromptSchema(schema_path)

        # Shared AgentFactory (for A2 and, later, other agents)
        self.agent_factory = AgentFactory()

        # Shared LLMClient
        self.llm_client = LLMClient()

        # A2 agent
        self.a2_promptshaper = A2PromptShaper(
            agent_factory=self.agent_factory,
            llm_client=self.llm_client,
        )

    def preprocess(self, user_text: str, sp: SuperPrompt) -> SuperPrompt:
        """
        Keep EXACTLY the old behaviour:
        - Ignore empty/whitespace-only input.
        - Otherwise run deterministic preprocessing, update sp in place.
        """
        text = (user_text or "").strip()
        if not text:
            return sp
        preprocess(text, sp, self.schema)
        return sp

    def run_a2_promptshaper(self, sp: SuperPrompt) -> SuperPrompt:
        """
        Run A2 on the current SuperPrompt.
        """
        return self.a2_promptshaper.run(sp)
