# ragstream/orchestration/llm_client.py
# -*- coding: utf-8 -*-
"""
LLMClient — thin wrapper around an LLM provider.

Current implementation:
- Uses OpenAI Python client v1 (OpenAI() + client.chat.completions.create).
- Reads OPENAI_API_KEY from environment (or optional api_key in __init__).
- Supports optional JSON-mode: if response_format={"type": "json_object"},
  it will attempt json.loads on the returned content and give you a dict.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Union
import os
import json

from ragstream.utils.logging import SimpleLogger

try:
    # New v1-style client
    from openai import OpenAI  # type: ignore[import]
except ImportError:  # pragma: no cover - import guard
    OpenAI = None  # type: ignore[assignment]

JsonDict = Dict[str, Any]


class LLMClient:
    """
    Neutral LLM gateway.

    You give it:
      - messages: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
      - model_name, temperature, max_output_tokens
      - optional response_format (e.g. {"type": "json_object"})

    It returns:
      - string (raw content) OR
      - dict (if JSON-mode used and parsing succeeded)
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        key = api_key or os.getenv("OPENAI_API_KEY") or ""
        self._client: Optional[OpenAI] = None  # type: ignore[type-arg]

        if OpenAI is None:
            SimpleLogger.info(
                "LLMClient: 'openai' v1 client not installed. Any LLM call will fail until you "
                "install it (e.g. 'pip install openai')."
            )
            return

        if not key:
            SimpleLogger.info(
                "LLMClient: OPENAI_API_KEY not set. Any LLM call will fail until you set it."
            )
            return

        try:
            # v1 client: hold a single instance
            self._client = OpenAI(api_key=key)
            SimpleLogger.info("LLMClient: OpenAI client initialised (v1 API).")
        except Exception as exc:
            SimpleLogger.error(f"LLMClient: failed to initialise OpenAI client: {exc!r}")
            self._client = None

    def chat(
            self,
            *,
            messages,
            model_name: str,
            temperature: float,
            max_output_tokens: int,
            response_format: dict | None = None,
    ):
        """
        Thin wrapper over OpenAI chat.completions.

        - Uses max_completion_tokens (new API) instead of max_tokens.
        - For gpt-5* reasoning models, we do NOT send temperature (it is unsupported).
        """
        if self._client is None:
            raise RuntimeError("LLMClient: OpenAI client is not initialised")

        # Base kwargs for the API call
        kwargs: dict = {
            "model": model_name,
            "messages": messages,
            "max_completion_tokens": max_output_tokens,
        }

        if response_format is not None:
            kwargs["response_format"] = response_format

        # temperature is illegal for gpt-5* reasoning models, allowed for others
        if temperature is not None and not model_name.startswith("gpt-5"):
            kwargs["temperature"] = temperature

        resp = self._client.chat.completions.create(**kwargs)
        # AgentPrompt.parse() expects the raw content (string or JSON-string)
        content = resp.choices[0].message.content
        return content if isinstance(content, str) else str(content or "")

