"""三层配置管理器: YAML 默认值 → .env → 环境变量。"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkillModelConfig:
    """单个 Skill 的模型配置。"""

    provider: str
    model_id: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class ConfigManager:
    """三层配置管理器。

    优先级: 环境变量 > .env > YAML 默认值

    Features:
    - 自动发现可用 Provider (扫描 API Key)
    - 按 Skill 独立配置 provider / model / temperature
    - Fallback 链配置
    """

    def __init__(self, config_dir: Path | None = None):
        self._config_dir = config_dir or Path(__file__).parent
        self._providers_config: dict[str, Any] = self._load_yaml("providers.yaml")
        self._skill_models: dict[str, Any] = self._load_yaml("skill_models.yaml")

    # ---- Public properties ----

    @cached_property
    def primary_provider(self) -> str:
        """解析主 Provider。

        优先级: PRIMARY_PROVIDER 环境变量 > YAML auto_detect > YAML default。
        """
        env = os.environ.get("PRIMARY_PROVIDER")
        if env:
            return env.lower()

        if self._providers_config.get("auto_detect"):
            discovered = self._auto_discover()
            if discovered:
                logger.info("Auto-discovered providers: %s, using '%s'", discovered, discovered[0])
                return discovered[0]

        return self._providers_config.get("primary_provider", "deepseek")

    @cached_property
    def fallback_providers(self) -> list[str]:
        """解析 Fallback 链。

        优先级: FALLBACK_PROVIDERS 环境变量 > YAML fallback_chain。
        """
        env = os.environ.get("FALLBACK_PROVIDERS")
        if env:
            return [p.strip().lower() for p in env.split(",") if p.strip()]
        return self._providers_config.get("fallback_chain", [])

    @cached_property
    def available_providers(self) -> list[str]:
        """返回所有已配置且可用的 provider 列表。"""
        return self._auto_discover()

    # ---- Provider config ----

    def get_provider_config(self, provider_name: str) -> dict[str, Any]:
        """获取指定 Provider 的完整配置。"""
        providers = self._providers_config.get("providers", {})
        return providers.get(provider_name, {})

    def get_provider_api_key(self, provider_name: str) -> str | None:
        """获取 Provider 的 API Key (从环境变量读取)。"""
        cfg = self.get_provider_config(provider_name)
        key_env = cfg.get("api_key_env", "")
        if key_env:
            return os.environ.get(key_env)
        return None

    def get_provider_default_model(self, provider_name: str) -> str | None:
        """获取 Provider 的默认模型名。"""
        cfg = self.get_provider_config(provider_name)
        return cfg.get("default_model")

    def get_provider_base_url(self, provider_name: str) -> str | None:
        """获取 Provider 的 base_url (如 siliconflow, ollama)。"""
        cfg = self.get_provider_config(provider_name)
        return cfg.get("base_url")

    # ---- Skill model config ----

    def get_skill_model_config(self, skill_name: str) -> SkillModelConfig:
        """获取 Skill 级别的模型配置。

        未配置的 Skill 使用 primary_provider 的默认配置。
        """
        skill_cfg = self._skill_models.get(skill_name, {})
        if not skill_cfg:
            return SkillModelConfig(provider=self.primary_provider)

        provider = skill_cfg.get("provider", self.primary_provider)
        # provider=none 表示此 Skill 不需要 LLM
        if provider == "none":
            return SkillModelConfig(provider="none")

        return SkillModelConfig(
            provider=provider,
            model_id=skill_cfg.get("model"),
            temperature=skill_cfg.get("temperature"),
            max_tokens=skill_cfg.get("max_tokens"),
        )

    # ---- Private helpers ----

    def _auto_discover(self) -> list[str]:
        """自动发现可用 Provider (检查 API Key 存在性)。"""
        preferred_order = ["deepseek", "openai", "siliconflow",
                           "anthropic", "azure", "ollama"]
        available: list[str] = []
        providers_cfg = self._providers_config.get("providers", {})

        for name in preferred_order:
            cfg = providers_cfg.get(name, {})
            if not cfg.get("enabled", False):
                continue
            key_env = cfg.get("api_key_env", "")
            if key_env and os.environ.get(key_env):
                available.append(name)
            elif name == "ollama":
                # ollama 不需要 API Key
                available.append(name)

        return available

    def _load_yaml(self, filename: str) -> dict[str, Any]:
        """加载 YAML 配置文件，文件不存在时返回空 dict。"""
        path = self._config_dir / filename
        if not path.exists():
            logger.debug("Config file not found: %s, using defaults", path)
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning("Failed to load config %s: %s", path, e)
            return {}

    def __repr__(self) -> str:
        return (
            f"ConfigManager(primary={self.primary_provider}, "
            f"fallback={self.fallback_providers}, "
            f"available={self.available_providers})"
        )
