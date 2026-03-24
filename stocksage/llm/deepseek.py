"""DeepSeek LLM 实现，通过 OpenAI 兼容 API 调用。"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncGenerator

import httpx
from openai import AsyncOpenAI, OpenAI

logger = logging.getLogger(__name__)

# 单次请求超时: 连接 10s，读取 120s（防止 DeepSeek API 无响应挂起数小时）
_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)


class DeepSeekLLM:
    """DeepSeek API 客户端，使用 OpenAI SDK。"""

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=_DEFAULT_TIMEOUT,
            max_retries=2,
        )
        self._async_client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=_DEFAULT_TIMEOUT,
            max_retries=2,
        )
        self._default_model = "deepseek-chat"

    @property
    def provider_name(self) -> str:
        return "deepseek"

    @classmethod
    def is_available(cls) -> bool:
        return bool(os.environ.get("DEEPSEEK_API_KEY"))

    def _clamp_max_tokens(self, max_tokens: int) -> int:
        _API_MAX_TOKENS = 8192
        if max_tokens > _API_MAX_TOKENS:
            logger.warning(
                "max_tokens=%d 超出 API 上限 %d，已自动裁剪",
                max_tokens, _API_MAX_TOKENS,
            )
            return _API_MAX_TOKENS
        return max_tokens

    def call(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8000,
    ) -> str:
        """调用 DeepSeek，返回文本响应。空响应自动重试最多 2 次。"""
        max_tokens = self._clamp_max_tokens(max_tokens)

        max_retries = 2
        for attempt in range(max_retries + 1):
            response = self._client.chat.completions.create(
                model=model or self._default_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content or ""
            finish_reason = response.choices[0].finish_reason
            total_tokens = response.usage.total_tokens if response.usage else 0

            if finish_reason == "length":
                logger.warning(
                    "LLM 响应因 max_tokens=%d 被截断 (model=%s, tokens=%d)，输出可能不完整",
                    max_tokens, model or self._default_model, total_tokens,
                )

            # 空响应重试
            if not content.strip() and attempt < max_retries:
                logger.warning(
                    "LLM 返回空响应 (attempt %d/%d, tokens=%d)，%0.1fs 后重试...",
                    attempt + 1, max_retries + 1, total_tokens, 1.0,
                )
                time.sleep(1.0)
                continue

            logger.info(
                "LLM call: model=%s, tokens=%d",
                model or self._default_model,
                total_tokens,
            )
            return content

        # 所有重试均失败
        logger.error("LLM 连续 %d 次返回空响应", max_retries + 1)
        return content

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8000,
    ) -> AsyncGenerator[str, None]:
        """流式调用 DeepSeek，逐 chunk yield 文本。"""
        max_tokens = self._clamp_max_tokens(max_tokens)

        response = await self._async_client.chat.completions.create(
            model=model or self._default_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
