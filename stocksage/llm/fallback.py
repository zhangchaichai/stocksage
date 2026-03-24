"""FallbackLLM: multi-provider LLM with cascading fallback and health tracking."""
from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from stocksage.llm.base import BaseLLM

logger = logging.getLogger(__name__)


class _ProviderHealth:
    """Tracks per-provider health with cooldown periods."""

    def __init__(self, cooldown_seconds: int = 300):
        self._failures: dict[str, float] = {}
        self._cooldown = cooldown_seconds

    def is_healthy(self, provider: str) -> bool:
        fail_time = self._failures.get(provider)
        if fail_time is None:
            return True
        return (time.time() - fail_time) > self._cooldown

    def mark_failed(self, provider: str) -> None:
        self._failures[provider] = time.time()
        logger.warning("Provider '%s' marked unhealthy, cooldown %ds", provider, self._cooldown)

    def mark_recovered(self, provider: str) -> None:
        if provider in self._failures:
            del self._failures[provider]
            logger.info("Provider '%s' recovered", provider)


class FallbackLLM:
    """Multi-provider LLM with automatic fallback.

    Tries providers in order. If a provider fails, it is marked unhealthy
    for a cooldown period and skipped on subsequent calls until the cooldown
    expires. The last provider in the chain is always tried as a last resort.

    Usage::

        llm = FallbackLLM(["deepseek", "openai", "anthropic"])
        result = llm.call(messages, temperature=0.7)
    """

    def __init__(
        self,
        providers: list[str],
        health_cooldown: int = 300,
    ):
        from stocksage.llm.factory import create_llm

        self._provider_names: list[str] = []
        self._providers: dict[str, BaseLLM] = {}
        self._health = _ProviderHealth(health_cooldown)

        for name in providers:
            try:
                self._providers[name] = create_llm(name)
                self._provider_names.append(name)
            except Exception as e:
                logger.warning("Skipping provider '%s' (init failed): %s", name, e)

        if not self._provider_names:
            raise RuntimeError(
                f"No LLM providers available from: {providers}. "
                "Check API keys and environment variables."
            )

        logger.info("FallbackLLM initialized with providers: %s", self._provider_names)

    @property
    def provider_name(self) -> str:
        return f"fallback({','.join(self._provider_names)})"

    def call(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """Call LLM with automatic fallback across providers."""
        errors: list[tuple[str, str]] = []

        for i, name in enumerate(self._provider_names):
            is_last = (i == len(self._provider_names) - 1)

            # Skip unhealthy providers unless it's the last one
            if not self._health.is_healthy(name) and not is_last:
                logger.debug("Skipping unhealthy provider '%s'", name)
                continue

            provider = self._providers[name]
            try:
                result = provider.call(
                    messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                self._health.mark_recovered(name)
                return result
            except Exception as e:
                logger.warning("Provider '%s' failed: %s, trying next", name, e)
                self._health.mark_failed(name)
                errors.append((name, str(e)))

        raise RuntimeError(f"All LLM providers failed: {errors}")

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> AsyncGenerator[str, None]:
        """Stream LLM with automatic fallback across providers."""
        errors: list[tuple[str, str]] = []

        for i, name in enumerate(self._provider_names):
            is_last = (i == len(self._provider_names) - 1)

            if not self._health.is_healthy(name) and not is_last:
                logger.debug("Skipping unhealthy provider '%s' for streaming", name)
                continue

            provider = self._providers[name]
            try:
                if hasattr(provider, "stream"):
                    async for chunk in provider.stream(
                        messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    ):
                        yield chunk
                    self._health.mark_recovered(name)
                    return
                else:
                    # Fallback: non-streaming call, yield all at once
                    result = provider.call(
                        messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    self._health.mark_recovered(name)
                    yield result
                    return
            except Exception as e:
                logger.warning("Provider '%s' streaming failed: %s, trying next", name, e)
                self._health.mark_failed(name)
                errors.append((name, str(e)))

        raise RuntimeError(f"All LLM providers failed for streaming: {errors}")

    @property
    def provider_names(self) -> list[str]:
        """Return the list of configured provider names."""
        return list(self._provider_names)
