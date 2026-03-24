"""BaseLLM 协议定义。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Protocol, runtime_checkable


@runtime_checkable
class BaseLLM(Protocol):
    """LLM 调用协议，所有 LLM 实现需满足此接口。"""

    def call(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """调用 LLM，返回生成的文本内容。"""
        ...

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> AsyncGenerator[str, None]:
        """流式调用 LLM，逐 token yield 文本内容。"""
        ...

    @property
    def provider_name(self) -> str:
        """Provider 标识名称。"""
        ...
