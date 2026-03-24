"""ModelFactory v2 tests."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from stocksage.llm.factory import (
    AllProvidersUnavailableError,
    ModelFactory,
    ProviderUnavailableError,
    create_llm,
    list_providers,
)


class TestModelFactoryBasic:
    def test_create_model_with_explicit_provider(self):
        factory = ModelFactory()
        llm = factory.create_model(provider="ollama")
        assert llm.provider_name == "ollama"

    def test_create_model_deepseek_with_key(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=True):
            factory = ModelFactory()
            llm = factory.create_model(provider="deepseek")
            assert llm.provider_name == "deepseek"

    def test_create_model_missing_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            factory = ModelFactory()
            with pytest.raises(AllProvidersUnavailableError):
                factory.create_model(provider="deepseek")

    def test_create_model_unknown_provider_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            factory = ModelFactory()
            with pytest.raises((ValueError, AllProvidersUnavailableError)):
                factory.create_model(provider="nonexistent")


class TestModelFactoryFallback:
    def test_fallback_on_primary_failure(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            factory = ModelFactory()
            # deepseek will fail (no key), should fallback to openai
            llm = factory.create_model(provider="deepseek")
            assert llm.provider_name == "openai"

    def test_all_providers_fail_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            factory = ModelFactory()
            with pytest.raises(AllProvidersUnavailableError):
                factory.create_model(provider="deepseek")


class TestModelFactoryWithConfig:
    @pytest.fixture
    def config_dir(self, tmp_path: Path) -> Path:
        providers = {
            "primary_provider": "openai",
            "auto_detect": False,
            "providers": {
                "openai": {
                    "enabled": True,
                    "api_key_env": "OPENAI_API_KEY",
                    "default_model": "gpt-4o-mini",
                },
                "deepseek": {
                    "enabled": True,
                    "api_key_env": "DEEPSEEK_API_KEY",
                    "default_model": "deepseek-chat",
                },
            },
            "fallback_chain": ["deepseek"],
        }
        skill_models = {
            "judge": {"provider": "openai", "model": "gpt-4o", "temperature": 0.3},
            "fetch_price_data": {"provider": "none"},
        }
        with open(tmp_path / "providers.yaml", "w") as f:
            yaml.dump(providers, f)
        with open(tmp_path / "skill_models.yaml", "w") as f:
            yaml.dump(skill_models, f)
        return tmp_path

    def test_create_model_for_skill(self, config_dir):
        from stocksage.config.manager import ConfigManager
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            cm = ConfigManager(config_dir)
            factory = ModelFactory(config=cm)
            llm = factory.create_model_for_skill("judge")
            assert llm.provider_name == "openai"

    def test_create_model_for_none_skill(self, config_dir):
        from stocksage.config.manager import ConfigManager
        with patch.dict(os.environ, {}, clear=True):
            cm = ConfigManager(config_dir)
            factory = ModelFactory(config=cm)
            with pytest.raises(ProviderUnavailableError, match="不使用 LLM"):
                factory.create_model_for_skill("fetch_price_data")

    def test_discover_providers(self, config_dir):
        from stocksage.config.manager import ConfigManager
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}, clear=True):
            cm = ConfigManager(config_dir)
            factory = ModelFactory(config=cm)
            available = factory.discover_providers()
            assert "openai" in available


class TestBackwardCompat:
    """Ensure create_llm() and list_providers() still work."""

    def test_create_llm_ollama(self):
        llm = create_llm("ollama")
        assert hasattr(llm, "call")

    def test_create_llm_bad_provider(self):
        with pytest.raises(ValueError):
            create_llm("nonexistent")

    def test_list_providers_sorted(self):
        providers = list_providers()
        assert providers == sorted(providers)
        assert "deepseek" in providers
