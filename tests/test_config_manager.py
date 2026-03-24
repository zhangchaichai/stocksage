"""ConfigManager tests."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from stocksage.config.manager import ConfigManager, SkillModelConfig


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Create temp config dir with providers.yaml and skill_models.yaml."""
    providers = {
        "primary_provider": "deepseek",
        "auto_detect": True,
        "providers": {
            "deepseek": {
                "enabled": True,
                "api_key_env": "DEEPSEEK_API_KEY",
                "default_model": "deepseek-chat",
                "base_url": None,
            },
            "openai": {
                "enabled": True,
                "api_key_env": "OPENAI_API_KEY",
                "default_model": "gpt-4o-mini",
            },
            "anthropic": {
                "enabled": True,
                "api_key_env": "ANTHROPIC_API_KEY",
                "default_model": "claude-sonnet-4-20250514",
            },
            "ollama": {
                "enabled": False,
                "base_url": "http://localhost:11434",
                "default_model": "qwen2.5:14b",
            },
        },
        "fallback_chain": ["openai", "anthropic"],
    }
    skill_models = {
        "judge": {"provider": "anthropic", "model": "claude-sonnet-4-20250514", "temperature": 0.3},
        "fetch_price_data": {"provider": "none"},
        "technical_analyst": {"temperature": 0.5},
    }
    with open(tmp_path / "providers.yaml", "w") as f:
        yaml.dump(providers, f)
    with open(tmp_path / "skill_models.yaml", "w") as f:
        yaml.dump(skill_models, f)
    return tmp_path


class TestConfigManagerBasic:
    def test_primary_provider_from_yaml(self, config_dir):
        with patch.dict(os.environ, {}, clear=True):
            cm = ConfigManager(config_dir)
            assert cm.primary_provider == "deepseek"

    def test_primary_provider_env_overrides_yaml(self, config_dir):
        with patch.dict(os.environ, {"PRIMARY_PROVIDER": "openai"}, clear=True):
            cm = ConfigManager(config_dir)
            assert cm.primary_provider == "openai"

    def test_primary_provider_auto_discover(self, config_dir):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            cm = ConfigManager(config_dir)
            assert cm.primary_provider == "openai"

    def test_fallback_providers_from_yaml(self, config_dir):
        with patch.dict(os.environ, {}, clear=True):
            cm = ConfigManager(config_dir)
            assert cm.fallback_providers == ["openai", "anthropic"]

    def test_fallback_providers_env_overrides(self, config_dir):
        with patch.dict(os.environ, {"FALLBACK_PROVIDERS": "ollama,deepseek"}, clear=True):
            cm = ConfigManager(config_dir)
            assert cm.fallback_providers == ["ollama", "deepseek"]


class TestConfigManagerAutoDiscover:
    def test_discover_finds_available(self, config_dir):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-xxx", "OPENAI_API_KEY": "sk-yyy"}, clear=True):
            cm = ConfigManager(config_dir)
            avail = cm.available_providers
            assert "deepseek" in avail
            assert "openai" in avail
            assert "ollama" not in avail  # disabled

    def test_discover_empty_when_no_keys(self, config_dir):
        with patch.dict(os.environ, {}, clear=True):
            cm = ConfigManager(config_dir)
            avail = cm.available_providers
            assert avail == []


class TestConfigManagerSkillModelConfig:
    def test_configured_skill(self, config_dir):
        with patch.dict(os.environ, {}, clear=True):
            cm = ConfigManager(config_dir)
            cfg = cm.get_skill_model_config("judge")
            assert cfg.provider == "anthropic"
            assert cfg.model_id == "claude-sonnet-4-20250514"
            assert cfg.temperature == 0.3

    def test_none_provider_skill(self, config_dir):
        with patch.dict(os.environ, {}, clear=True):
            cm = ConfigManager(config_dir)
            cfg = cm.get_skill_model_config("fetch_price_data")
            assert cfg.provider == "none"

    def test_unconfigured_skill_uses_primary(self, config_dir):
        with patch.dict(os.environ, {}, clear=True):
            cm = ConfigManager(config_dir)
            cfg = cm.get_skill_model_config("some_unknown_skill")
            assert cfg.provider == "deepseek"
            assert cfg.model_id is None

    def test_partial_config(self, config_dir):
        with patch.dict(os.environ, {}, clear=True):
            cm = ConfigManager(config_dir)
            cfg = cm.get_skill_model_config("technical_analyst")
            assert cfg.provider == "deepseek"  # uses primary
            assert cfg.temperature == 0.5


class TestConfigManagerProviderConfig:
    def test_get_provider_config(self, config_dir):
        with patch.dict(os.environ, {}, clear=True):
            cm = ConfigManager(config_dir)
            cfg = cm.get_provider_config("openai")
            assert cfg["default_model"] == "gpt-4o-mini"

    def test_get_provider_api_key(self, config_dir):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}, clear=True):
            cm = ConfigManager(config_dir)
            assert cm.get_provider_api_key("deepseek") == "sk-test"

    def test_get_provider_api_key_missing(self, config_dir):
        with patch.dict(os.environ, {}, clear=True):
            cm = ConfigManager(config_dir)
            assert cm.get_provider_api_key("deepseek") is None

    def test_get_provider_default_model(self, config_dir):
        with patch.dict(os.environ, {}, clear=True):
            cm = ConfigManager(config_dir)
            assert cm.get_provider_default_model("openai") == "gpt-4o-mini"


class TestConfigManagerMissingFiles:
    def test_missing_yaml_uses_defaults(self, tmp_path):
        with patch.dict(os.environ, {}, clear=True):
            cm = ConfigManager(tmp_path)
            assert cm.primary_provider == "deepseek"
            assert cm.fallback_providers == []

    def test_repr(self, config_dir):
        with patch.dict(os.environ, {}, clear=True):
            cm = ConfigManager(config_dir)
            r = repr(cm)
            assert "ConfigManager" in r
            assert "deepseek" in r
