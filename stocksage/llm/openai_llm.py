"""OpenAI LLM 实现，使用 OpenAI SDK。"""

from __future__ import annotations

import logging

import httpx
from openai import OpenAI

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)


class OpenAILLM:
    """OpenAI API 客户端。"""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=_DEFAULT_TIMEOUT,
            max_retries=2,
        )
        self._default_model = "gpt-4o-mini"

    def call(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """调用 OpenAI，返回文本响应。"""
        response = self._client.chat.completions.create(
            model=model or self._default_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or ""
        total_tokens = response.usage.total_tokens if response.usage else 0
        logger.info("LLM call: model=%s, tokens=%d", model or self._default_model, total_tokens)
        return content
