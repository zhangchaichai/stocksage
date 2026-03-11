"""LLM factory tests (Task 1.5)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from stocksage.llm.factory import create_llm, list_providers


class TestListProviders:
    def test_returns_sorted_providers(self):
        providers = list_providers()
        assert "deepseek" in providers
        assert "openai" in providers
        assert "anthropic" in providers
        assert "ollama" in providers
        assert providers == sorted(providers)


class TestCreateLlmFactory:
    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="不支持的 LLM provider"):
            create_llm("nonexistent_provider")

    def test_unknown_provider_shows_available(self):
        with pytest.raises(ValueError, match="anthropic"):
            create_llm("bad_provider")

    def test_deepseek_no_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
                create_llm("deepseek")

    def test_openai_no_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                create_llm("openai")

    def test_anthropic_no_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                create_llm("anthropic")

    def test_deepseek_with_api_key(self):
        llm = create_llm("deepseek", api_key="test-key-123")
        from stocksage.llm.deepseek import DeepSeekLLM
        assert isinstance(llm, DeepSeekLLM)

    def test_openai_with_api_key(self):
        llm = create_llm("openai", api_key="test-key-456")
        from stocksage.llm.openai_llm import OpenAILLM
        assert isinstance(llm, OpenAILLM)

    def test_ollama_no_key_required(self):
        llm = create_llm("ollama")
        from stocksage.llm.ollama_llm import OllamaLLM
        assert isinstance(llm, OllamaLLM)

    def test_ollama_custom_model(self):
        llm = create_llm("ollama", model="mistral")
        assert llm._default_model == "mistral"

    def test_deepseek_from_env(self):
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "env-key"}):
            llm = create_llm("deepseek")
            from stocksage.llm.deepseek import DeepSeekLLM
            assert isinstance(llm, DeepSeekLLM)

    def test_openai_from_env(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}):
            llm = create_llm("openai")
            from stocksage.llm.openai_llm import OpenAILLM
            assert isinstance(llm, OpenAILLM)
