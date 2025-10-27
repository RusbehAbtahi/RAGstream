# ragstream/app/controller.py
from __future__ import annotations
from ragstream.orchestration.super_prompt import SuperPrompt
from ragstream.app.preprocessing import preprocess_prompt  # new file below

class AppController:
    def preprocess(self, user_text: str, sp: SuperPrompt) -> SuperPrompt:
        text = (user_text or "").strip()
        if not text:
            return sp  # no change if empty
        out = preprocess_prompt(text)  # pure function
        sp.history_of_stages.append("preprocessed")
        sp.stage = "preprocessed"
        sp.body["task"] = out.get("task") or text
        sp.prompt_ready = out.get("preview_text") or text
        return sp
