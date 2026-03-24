"""Anthropic LLM 实现，使用 anthropic SDK。"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)


class AnthropicLLM:
    """Anthropic (Claude) API 客户端。"""

    def __init__(self, api_key: str):
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic SDK 未安装。请运行: pip install anthropic"
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        self._async_client = anthropic.AsyncAnthropic(api_key=api_key)
        self._default_model = "claude-sonnet-4-20250514"

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @classmethod
    def is_available(cls) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def _convert_messages(
        self, messages: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, str]]]:
        """将 OpenAI 格式 messages 转换为 Anthropic 格式，提取 system message。"""
        system_text = ""
        converted = []
        for msg in messages:
            if msg["role"] == "system":
                system_text = msg["content"]
            else:
                converted.append(msg)
        return system_text, converted

    def call(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """调用 Anthropic API，返回文本响应。

        将 OpenAI 格式的 messages 转换为 Anthropic 格式。
        """
        system_text, converted_messages = self._convert_messages(messages)

        kwargs = {
            "model": model or self._default_model,
            "messages": converted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_text:
            kwargs["system"] = system_text

        response = self._client.messages.create(**kwargs)
        content = response.content[0].text if response.content else ""
        input_tokens = response.usage.input_tokens if response.usage else 0
        output_tokens = response.usage.output_tokens if response.usage else 0
        logger.info(
            "LLM call: model=%s, input_tokens=%d, output_tokens=%d",
            model or self._default_model, input_tokens, output_tokens,
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
        """流式调用 Anthropic API，逐 chunk yield 文本。"""
        system_text, converted_messages = self._convert_messages(messages)

        kwargs = {
            "model": model or self._default_model,
            "messages": converted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_text:
            kwargs["system"] = system_text

        async with self._async_client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
