"""LLM 工厂：根据配置创建 LLM 实例。

v4.0 重构：ModelFactory 类 + ConfigManager 集成 + Provider 自动发现 + Fallback。
保留 create_llm() 向后兼容函数。
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv

from stocksage.llm.base import BaseLLM

load_dotenv()
logger = logging.getLogger(__name__)


class ProviderUnavailableError(ValueError):
    """指定 Provider 不可用 (API Key 缺失或初始化失败)。"""


class AllProvidersUnavailableError(Exception):
    """所有 Provider 均不可用。"""


@dataclass
class ProviderHealth:
    """Per-provider 健康状态跟踪。"""

    cooldown_seconds: int = 300
    _failures: dict[str, float] = field(default_factory=dict)

    def is_healthy(self, provider: str) -> bool:
        fail_time = self._failures.get(provider)
        if fail_time is None:
            return True
        return (time.time() - fail_time) > self.cooldown_seconds

    def mark_failed(self, provider: str) -> None:
        self._failures[provider] = time.time()
        logger.warning("Provider '%s' marked unhealthy, cooldown %ds", provider, self.cooldown_seconds)

    def mark_recovered(self, provider: str) -> None:
        if provider in self._failures:
            del self._failures[provider]
            logger.info("Provider '%s' recovered", provider)


# ---- Provider factory functions ----

def _create_deepseek(**kwargs: Any) -> BaseLLM:
    from stocksage.llm.deepseek import DeepSeekLLM
    api_key = kwargs.get("api_key") or os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise ProviderUnavailableError("DEEPSEEK_API_KEY 未设置")
    base_url = kwargs.get("base_url", "https://api.deepseek.com")
    return DeepSeekLLM(api_key=api_key, base_url=base_url)


def _create_openai(**kwargs: Any) -> BaseLLM:
    from stocksage.llm.openai_llm import OpenAILLM
    api_key = kwargs.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ProviderUnavailableError("OPENAI_API_KEY 未设置")
    base_url = kwargs.get("base_url", "https://api.openai.com/v1")
    return OpenAILLM(api_key=api_key, base_url=base_url)


def _create_anthropic(**kwargs: Any) -> BaseLLM:
    from stocksage.llm.anthropic_llm import AnthropicLLM
    api_key = kwargs.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ProviderUnavailableError("ANTHROPIC_API_KEY 未设置")
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


class ModelFactory:
    """多 Provider LLM 工厂。

    支持:
    - ConfigManager 集成 (按 Skill 配模型)
    - 自动发现可用 Provider
    - Fallback 链 (主 Provider 失败时自动切换)
    - 健康检查 + 冷却期
    """

    def __init__(
        self,
        config: Any | None = None,
        health_cooldown: int = 300,
    ):
        """初始化 ModelFactory。

        Args:
            config: ConfigManager 实例 (可选，不传则使用默认行为)。
            health_cooldown: Provider 失败后的冷却秒数。
        """
        self._config = config
        self._health = ProviderHealth(cooldown_seconds=health_cooldown)

    def create_model(
        self,
        provider: str | None = None,
        model_id: str | None = None,
        **kwargs: Any,
    ) -> BaseLLM:
        """创建 LLM 实例，支持 fallback。

        优先级: 指定 provider → ConfigManager.primary_provider → "deepseek"
        """
        provider = provider or self._get_primary_provider()

        try:
            return self._create_internal(provider, model_id, **kwargs)
        except (ProviderUnavailableError, Exception) as e:
            logger.warning("Primary provider '%s' failed: %s, trying fallback", provider, e)
            self._health.mark_failed(provider)

            for fallback in self._get_fallback_providers():
                if fallback == provider:
                    continue
                if not self._health.is_healthy(fallback):
                    logger.debug("Skipping unhealthy fallback '%s'", fallback)
                    continue
                try:
                    llm = self._create_internal(fallback, model_id, **kwargs)
                    self._health.mark_recovered(fallback)
                    return llm
                except (ProviderUnavailableError, Exception) as fb_err:
                    logger.warning("Fallback provider '%s' failed: %s", fallback, fb_err)
                    self._health.mark_failed(fallback)

            raise AllProvidersUnavailableError(
                f"所有 Provider 均不可用。主: {provider}, Fallback: {self._get_fallback_providers()}"
            )

    def create_model_for_skill(
        self,
        skill_name: str,
        **kwargs: Any,
    ) -> BaseLLM:
        """为特定 Skill 创建模型 (可独立配置 provider/model)。"""
        if not self._config:
            return self.create_model(**kwargs)

        skill_config = self._config.get_skill_model_config(skill_name)
        if skill_config.provider == "none":
            raise ProviderUnavailableError(f"Skill '{skill_name}' 配置为不使用 LLM")

        merged = dict(kwargs)
        if skill_config.temperature is not None:
            merged.setdefault("temperature", skill_config.temperature)
        if skill_config.max_tokens is not None:
            merged.setdefault("max_tokens", skill_config.max_tokens)

        return self.create_model(
            provider=skill_config.provider,
            model_id=skill_config.model_id,
            **merged,
        )

    def discover_providers(self) -> list[str]:
        """发现所有可用 Provider (API Key 存在)。"""
        if self._config:
            return self._config.available_providers
        available = []
        for name in _PROVIDERS:
            try:
                self._create_internal(name)
                available.append(name)
            except Exception:
                pass
        return available

    def _create_internal(
        self,
        provider: str,
        model_id: str | None = None,
        **kwargs: Any,
    ) -> BaseLLM:
        """内部创建方法。"""
        factory_fn = _PROVIDERS.get(provider)
        if factory_fn is None:
            supported = ", ".join(sorted(_PROVIDERS.keys()))
            raise ValueError(f"不支持的 LLM provider: {provider}。支持: {supported}")

        # 从 ConfigManager 获取额外配置
        if self._config:
            provider_cfg = self._config.get_provider_config(provider)
            if provider_cfg:
                api_key = self._config.get_provider_api_key(provider)
                if api_key:
                    kwargs.setdefault("api_key", api_key)
                base_url = self._config.get_provider_base_url(provider)
                if base_url:
                    kwargs.setdefault("base_url", base_url)
                if model_id is None:
                    model_id = self._config.get_provider_default_model(provider)

        if model_id:
            kwargs["model"] = model_id

        return factory_fn(**kwargs)

    def _get_primary_provider(self) -> str:
        if self._config:
            return self._config.primary_provider
        return "deepseek"

    def _get_fallback_providers(self) -> list[str]:
        if self._config:
            return self._config.fallback_providers
        return ["openai", "anthropic"]


# ---- 向后兼容函数 ----

_default_factory: ModelFactory | None = None


def _get_default_factory() -> ModelFactory:
    global _default_factory
    if _default_factory is None:
        _default_factory = ModelFactory()
    return _default_factory


def create_llm(provider: str = "deepseek", **kwargs: Any) -> BaseLLM:
    """根据 provider 名称创建 LLM 实例。

    向后兼容函数，内部委托给 ModelFactory。

    Args:
        provider: LLM 提供者名称（deepseek / openai / anthropic / ollama）。
        **kwargs: 传递给对应工厂函数的参数（如 api_key, base_url, model）。

    Returns:
        满足 BaseLLM Protocol 的 LLM 实例。
    """
    # 直接调用工厂函数，不走 fallback（保持旧行为）
    factory_fn = _PROVIDERS.get(provider)
    if factory_fn is None:
        supported = ", ".join(sorted(_PROVIDERS.keys()))
        raise ValueError(f"不支持的 LLM provider: {provider}。支持的 provider: {supported}")
    return factory_fn(**kwargs)


def list_providers() -> list[str]:
    """返回所有已注册的 provider 名称列表。"""
    return sorted(_PROVIDERS.keys())


def create_fallback_llm(
    providers: list[str] | None = None,
    health_cooldown: int = 300,
) -> BaseLLM:
    """创建支持级联降级的 FallbackLLM。

    Args:
        providers: 按优先级排列的 provider 列表，默认 ["deepseek", "openai", "anthropic"]。
        health_cooldown: provider 失败后的冷却秒数，默认 300。

    Returns:
        FallbackLLM 实例（满足 BaseLLM Protocol）。
    """
    from stocksage.llm.fallback import FallbackLLM

    providers = providers or ["deepseek", "openai", "anthropic"]
    return FallbackLLM(providers, health_cooldown=health_cooldown)
