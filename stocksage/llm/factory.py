"""LLM 工厂：根据配置创建 LLM 实例。

v3.0 重构：provider 注册表模式，支持 deepseek / openai / anthropic / ollama。
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from stocksage.llm.base import BaseLLM

load_dotenv()


def _create_deepseek(**kwargs: Any) -> BaseLLM:
    from stocksage.llm.deepseek import DeepSeekLLM

    api_key = kwargs.get("api_key") or os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 环境变量未设置，或通过 api_key 参数传入")
    return DeepSeekLLM(api_key=api_key)


def _create_openai(**kwargs: Any) -> BaseLLM:
    from stocksage.llm.openai_llm import OpenAILLM

    api_key = kwargs.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY 环境变量未设置，或通过 api_key 参数传入")
    base_url = kwargs.get("base_url", "https://api.openai.com/v1")
    return OpenAILLM(api_key=api_key, base_url=base_url)


def _create_anthropic(**kwargs: Any) -> BaseLLM:
    from stocksage.llm.anthropic_llm import AnthropicLLM

    api_key = kwargs.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY 环境变量未设置，或通过 api_key 参数传入")
    return AnthropicLLM(api_key=api_key)


def _create_ollama(**kwargs: Any) -> BaseLLM:
    from stocksage.llm.ollama_llm import OllamaLLM

    base_url = kwargs.get("base_url", "http://localhost:11434")
    model = kwargs.get("model", "llama3")
    return OllamaLLM(base_url=base_url, model=model)


# Provider 注册表：名称 → 工厂函数
_PROVIDERS: dict[str, Any] = {
    "deepseek": _create_deepseek,
    "openai": _create_openai,
    "anthropic": _create_anthropic,
    "ollama": _create_ollama,
}


def create_llm(provider: str = "deepseek", **kwargs: Any) -> BaseLLM:
    """根据 provider 名称创建 LLM 实例。

    Args:
        provider: LLM 提供者名称（deepseek / openai / anthropic / ollama）。
        **kwargs: 传递给对应工厂函数的参数（如 api_key, base_url, model）。

    Returns:
        满足 BaseLLM Protocol 的 LLM 实例。

    Raises:
        ValueError: provider 不受支持时。
    """
    factory = _PROVIDERS.get(provider)
    if factory is None:
        supported = ", ".join(sorted(_PROVIDERS.keys()))
        raise ValueError(f"不支持的 LLM provider: {provider}。支持的 provider: {supported}")
    return factory(**kwargs)


def list_providers() -> list[str]:
    """返回所有已注册的 provider 名称列表。"""
    return sorted(_PROVIDERS.keys())
