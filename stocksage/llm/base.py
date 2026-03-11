"""BaseLLM 协议定义。"""

from __future__ import annotations

from typing import Protocol


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
