# ragstream/orchestration/llm_client.py
# -*- coding: utf-8 -*-
"""
LLMClient — thin wrapper around an LLM provider.

Current implementation:
- Uses OpenAI Python client v1 (OpenAI() + client.chat.completions.create).
- Reads OPENAI_API_KEY from environment (or optional api_key in __init__).
- Keeps backward compatibility for old callers:
    * default return = raw content string
- Supports optional metadata return for cache/token inspection:
    * return_metadata=True -> {"content": "...", "usage": {...}}
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
import os

from ragstream.utils.logging import SimpleLogger

try:
    from openai import OpenAI  # type: ignore[import]
except ImportError:  # pragma: no cover - import guard
    OpenAI = None  # type: ignore[assignment]

JsonDict = Dict[str, Any]


class LLMClient:
    """
    Neutral LLM gateway.

    Default behavior stays backward compatible:
    - returns raw content string

    Optional behavior:
    - return_metadata=True returns:
        {
          "content": "...",
          "usage": {
              "prompt_tokens": ...,
              "completion_tokens": ...,
              "total_tokens": ...,
              "cached_tokens": ...
          }
        }
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
            self._client = OpenAI(api_key=key)
            SimpleLogger.info("LLMClient: OpenAI client initialised (v1 API).")
        except Exception as exc:
            SimpleLogger.error(f"LLMClient: failed to initialise OpenAI client: {exc!r}")
            self._client = None

    def chat(
        self,
        *,
        messages: List[Dict[str, str]],
        model_name: str,
        temperature: float,
        max_output_tokens: int,
        response_format: Dict[str, Any] | None = None,
        return_metadata: bool = False,
    ) -> Union[str, JsonDict]:
        """
        Thin wrapper over OpenAI chat.completions.

        Notes:
        - Uses max_completion_tokens (new API) instead of max_tokens.
        - For gpt-5* reasoning models, temperature is omitted.
        - Prompt caching for recent models is automatic on the provider side;
          this client does not implement a second cache system.
        """
        if self._client is None:
            raise RuntimeError("LLMClient: OpenAI client is not initialised")

        kwargs: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "max_completion_tokens": int(max_output_tokens),
        }

        if response_format is not None:
            kwargs["response_format"] = response_format

        if temperature is not None and not str(model_name).startswith("gpt-5"):
            kwargs["temperature"] = float(temperature)

        resp = self._client.chat.completions.create(**kwargs)

        content = resp.choices[0].message.content
        content_text = content if isinstance(content, str) else str(content or "")

        if not return_metadata:
            return content_text

        usage = self._extract_usage(resp)
        return {
            "content": content_text,
            "usage": usage,
        }

    @staticmethod
    def _extract_usage(resp: Any) -> JsonDict:
        """
        Extract token usage including cached tokens when the provider returns it.
        """
        usage_obj = getattr(resp, "usage", None)
        if usage_obj is None:
            return {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cached_tokens": 0,
            }

        prompt_tokens = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage_obj, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage_obj, "total_tokens", 0) or 0)

        prompt_tokens_details = getattr(usage_obj, "prompt_tokens_details", None)
        cached_tokens = 0
        if prompt_tokens_details is not None:
            cached_tokens = int(getattr(prompt_tokens_details, "cached_tokens", 0) or 0)

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cached_tokens": cached_tokens,
        }