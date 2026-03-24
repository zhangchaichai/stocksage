"""LLM 适配层：桥接 StockSage BaseLLM 与 tool calling 支持。

StockSage 的 BaseLLM 只有 call(messages) -> str，不支持 function calling。
此模块提供三条路径：
1. NanobotLLMAdapter — 包装 nanobot LLMProvider（已支持 function calling）
2. OpenAICompatAdapter — 使用 OpenAI SDK 调用 OpenAI-compatible API（如 DeepSeek）
3. BaseLLMToolCallingAdapter — 包装 StockSage 的同步 BaseLLM，添加 tool calling 支持

LiteLLMAdapter 作为 OpenAICompatAdapter 的别名保留向后兼容。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Provider config: model prefix → (env var for api_key, default base_url) ──
_PROVIDER_MAP: dict[str, tuple[str, str]] = {
    "deepseek": ("DEEPSEEK_API_KEY", "https://api.deepseek.com"),
    "gpt": ("OPENAI_API_KEY", "https://api.openai.com/v1"),
    "o1": ("OPENAI_API_KEY", "https://api.openai.com/v1"),
    "o3": ("OPENAI_API_KEY", "https://api.openai.com/v1"),
    "claude": ("ANTHROPIC_API_KEY", "https://api.anthropic.com/v1"),
}


def _load_dotenv_cascade() -> None:
    """从当前目录和父目录加载 .env 文件。"""
    from dotenv import load_dotenv

    load_dotenv()
    cwd = Path.cwd()
    for parent in [cwd.parent, cwd.parent.parent]:
        env_file = parent / ".env"
        if env_file.is_file():
            load_dotenv(env_file, override=False)


def _resolve_provider(model: str) -> tuple[str, str]:
    """根据 model 名称推断 env var 和 base_url。"""
    for prefix, (env_var, base_url) in _PROVIDER_MAP.items():
        if model.startswith(prefix):
            return env_var, base_url
    # Default to DeepSeek
    return "DEEPSEEK_API_KEY", "https://api.deepseek.com"


@dataclass
class ToolCallResult:
    """工具调用请求。"""

    id: str
    name: str
    arguments: dict[str, Any]

    def to_openai_tool_call(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments, ensure_ascii=False),
            },
        }


@dataclass
class AgentLLMResponse:
    """Agent LLM 调用的统一响应。"""

    content: str | None = None
    tool_calls: list[ToolCallResult] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    reasoning_content: str | None = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class NanobotLLMAdapter:
    """将 nanobot LLMProvider 适配为 SkillAgent 可用的接口。"""

    def __init__(self, provider: Any):
        self._provider = provider

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AgentLLMResponse:
        response = await self._provider.chat_with_retry(
            messages=messages,
            tools=tools,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        tool_calls = [
            ToolCallResult(
                id=tc.id,
                name=tc.name,
                arguments=tc.arguments,
            )
            for tc in response.tool_calls
        ]
        return AgentLLMResponse(
            content=response.content,
            tool_calls=tool_calls,
            finish_reason=response.finish_reason,
            usage=response.usage,
            reasoning_content=response.reasoning_content,
        )


class OpenAICompatAdapter:
    """使用 OpenAI SDK 调用 OpenAI-compatible API（DeepSeek / OpenAI / 其他兼容服务）。

    支持 function calling / tool calling，是 ChatAgent 和 SkillAgent 的默认 LLM 适配器。
    使用 openai 库（StockSage 已依赖），无需额外安装 litellm。
    """

    def __init__(
        self,
        model: str = "deepseek-chat",
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        _load_dotenv_cascade()

        self._model = model

        # Resolve provider-specific config
        env_var, default_base_url = _resolve_provider(model)

        if api_key:
            self._api_key = api_key
        else:
            self._api_key = os.environ.get(env_var, "")

        self._base_url = base_url or default_base_url

        if not self._api_key:
            logger.warning(
                "OpenAICompatAdapter: 未找到 API key (model=%s, env_var=%s)。"
                "请设置对应环境变量或在 .env 文件中配置。",
                model, env_var,
            )

        # Lazy-init client
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import httpx
            from openai import AsyncOpenAI

            timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=timeout,
                max_retries=2,
            )
        return self._client

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AgentLLMResponse:
        client = self._get_client()

        kwargs: dict[str, Any] = {
            "model": model or self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools

        try:
            response = await client.chat.completions.create(**kwargs)
        except Exception as e:
            logger.error("OpenAI API 调用失败: %s", e)
            raise

        choice = response.choices[0]
        content = choice.message.content
        tc_list = choice.message.tool_calls

        tool_calls: list[ToolCallResult] = []
        if tc_list:
            for tc in tc_list:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(
                    ToolCallResult(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args,
                    )
                )

        usage_dict = {}
        if response.usage:
            usage_dict = {
                "prompt_tokens": response.usage.prompt_tokens or 0,
                "completion_tokens": response.usage.completion_tokens or 0,
                "total_tokens": response.usage.total_tokens or 0,
            }

        return AgentLLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage_dict,
        )


# Backward compatibility alias
LiteLLMAdapter = OpenAICompatAdapter


class BaseLLMToolCallingAdapter:
    """将 StockSage 的 BaseLLM (call only) 适配为支持 tool calling。

    需要工具时使用 OpenAICompatAdapter，不需要工具时直接调用 BaseLLM。
    """

    def __init__(self, base_llm: Any, model: str | None = None):
        self._base_llm = base_llm
        self._model = model or getattr(base_llm, "model_name", "deepseek-chat")
        self._openai_adapter = OpenAICompatAdapter(model=self._model)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AgentLLMResponse:
        if tools:
            return await self._openai_adapter.chat(
                messages=messages,
                tools=tools,
                model=model or self._model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        # No tools needed — use the base LLM directly (offload sync call to thread)
        import asyncio

        content = await asyncio.to_thread(
            self._base_llm.call,
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return AgentLLMResponse(content=content)
