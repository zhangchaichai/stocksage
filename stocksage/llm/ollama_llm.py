"""Ollama LLM 实现，调用本地 Ollama 服务。"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=300.0, write=10.0, pool=5.0)


class OllamaLLM:
    """Ollama 本地 API 客户端。"""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self._base_url = base_url.rstrip("/")
        self._default_model = model

    @property
    def provider_name(self) -> str:
        return "ollama"

    @classmethod
    def is_available(cls) -> bool:
        # Ollama 不需要 API Key，只需本地服务运行
        return True

    def call(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """调用 Ollama chat API，返回文本响应。"""
        payload = {
            "model": model or self._default_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
            resp = client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()

        data = resp.json()
        content = data.get("message", {}).get("content", "")
        logger.info(
            "LLM call: model=%s (ollama), response_length=%d",
            model or self._default_model, len(content),
        )
        return content

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """流式调用 Ollama chat API，逐 chunk yield 文本。"""
        payload = {
            "model": model or self._default_model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            async with client.stream(
                "POST", f"{self._base_url}/api/chat", json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
