# ragstream/app/controller.py
from __future__ import annotations
from ragstream.orchestration.super_prompt import SuperPrompt
from ragstream.preprocessing.prompt_schema import PromptSchema
from ragstream.preprocessing.preprocessing import preprocess  # correct import

class AppController:
    def __init__(self, schema_path: str = "ragstream/config/prompt_schema.json") -> None:
        self.schema = PromptSchema(schema_path)  # load once

    def preprocess(self, user_text: str, sp: SuperPrompt) -> SuperPrompt:
        text = (user_text or "").strip()
        if not text:
            return sp
        preprocess(text, sp, self.schema)  # updates sp in-place (sets prompt_ready, stage, history)
        return sp
