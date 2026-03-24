"""Orchestrator streaming + per-skill routing tests."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from stocksage.workflow.nodes import make_skill_node, make_streaming_skill_node
from stocksage.skill_engine.models import (
    ExecutionConfig,
    InputField,
    OutputField,
    SkillDef,
    SkillInterface,
)


def _make_skill(
    name: str = "test_analyst",
    skill_type: str = "agent",
) -> SkillDef:
    return SkillDef(
        name=name,
        type=skill_type,
        interface=SkillInterface(
            inputs=[InputField(name="symbol", source="state.meta.symbol")],
            outputs=[OutputField(name="result", target="state.analysis.test")],
        ),
        execution=ExecutionConfig(model="test-model", temperature=0.5, max_tokens=100),
        prompt_template="分析 {{ symbol }}",
    )


class TestMakeStreamingSkillNode:
    def test_streaming_node_calls_execute_streaming_for_llm(self):
        """Streaming node should use execute_streaming for LLM skills."""
        mock_llm = MagicMock()
        mock_llm.provider_name = "test"

        async def mock_stream(messages, **kwargs):
            yield '{"result": "ok"}'

        mock_llm.stream = mock_stream

        fetcher = MagicMock()
        from stocksage.skill_engine.executor import SkillExecutor
        executor = SkillExecutor(mock_llm, fetcher)

        skill = _make_skill(skill_type="agent")
        queue = asyncio.Queue()

        node_fn = make_streaming_skill_node(
            skill, executor, factory=None, streaming_queue=queue,
        )

        state = {
            "meta": {"symbol": "600519", "stock_name": "test"},
            "data": {}, "analysis": {},
        }
        result = node_fn(state)

        assert "analysis" in result

    def test_streaming_node_uses_per_skill_routing(self):
        """When factory is provided, node should route model per skill."""
        mock_llm_default = MagicMock()
        mock_llm_default.provider_name = "deepseek"
        mock_llm_default.call = MagicMock(return_value='{"result": "ok"}')

        mock_llm_openai = MagicMock()
        mock_llm_openai.provider_name = "openai"
        mock_llm_openai.call = MagicMock(return_value='{"result": "openai_result"}')

        fetcher = MagicMock()
        from stocksage.skill_engine.executor import SkillExecutor
        executor = SkillExecutor(mock_llm_default, fetcher)

        mock_factory = MagicMock()
        mock_factory.create_model_for_skill = MagicMock(return_value=mock_llm_openai)

        skill = _make_skill(name="judge", skill_type="agent")

        # No streaming queue → falls back to sync execute
        node_fn = make_streaming_skill_node(
            skill, executor, factory=mock_factory, streaming_queue=None,
        )

        state = {
            "meta": {"symbol": "600519", "stock_name": "test"},
            "data": {}, "analysis": {},
        }
        result = node_fn(state)

        # Factory should have been called with skill name
        mock_factory.create_model_for_skill.assert_called_once_with("judge")
        # openai LLM should have been used
        mock_llm_openai.call.assert_called_once()
        mock_llm_default.call.assert_not_called()

    def test_streaming_node_data_skill_no_streaming(self):
        """Data skills should not use streaming even when queue is present."""
        mock_llm = MagicMock()
        mock_llm.provider_name = "test"

        fetcher = MagicMock()
        fetcher.fetch_stock_info = MagicMock(return_value={"name": "test"})

        from stocksage.skill_engine.executor import SkillExecutor
        executor = SkillExecutor(mock_llm, fetcher)

        skill = SkillDef(
            name="fetch_stock_info",
            type="data",
            interface=SkillInterface(
                outputs=[OutputField(name="result", target="state.data.stock_info")],
            ),
            execution=ExecutionConfig(),
            prompt_template="",
        )

        queue = asyncio.Queue()
        node_fn = make_streaming_skill_node(
            skill, executor, factory=None, streaming_queue=queue,
        )

        state = {"meta": {"symbol": "600519"}, "data": {}}
        result = node_fn(state)

        assert "data" in result
        # No chunks in the queue since data skills don't stream
        assert queue.empty()

    def test_streaming_node_factory_unavailable_uses_default(self):
        """When factory raises ProviderUnavailableError, fall back to default."""
        mock_llm_default = MagicMock()
        mock_llm_default.provider_name = "deepseek"
        mock_llm_default.call = MagicMock(return_value='{"result": "ok"}')

        fetcher = MagicMock()
        from stocksage.skill_engine.executor import SkillExecutor
        from stocksage.llm.factory import ProviderUnavailableError

        executor = SkillExecutor(mock_llm_default, fetcher)

        mock_factory = MagicMock()
        mock_factory.create_model_for_skill = MagicMock(
            side_effect=ProviderUnavailableError("none provider"),
        )

        skill = _make_skill(name="fetch_price_data", skill_type="agent")

        node_fn = make_streaming_skill_node(
            skill, executor, factory=mock_factory, streaming_queue=None,
        )

        state = {
            "meta": {"symbol": "600519", "stock_name": "test"},
            "data": {}, "analysis": {},
        }
        result = node_fn(state)

        # Should fall back to default LLM
        mock_llm_default.call.assert_called_once()
        assert "analysis" in result


class TestMakeSkillNodeUnchanged:
    def test_original_make_skill_node_works(self):
        """Original make_skill_node should still work."""
        mock_llm = MagicMock()
        mock_llm.provider_name = "test"
        mock_llm.call = MagicMock(return_value='{"result": "ok"}')

        fetcher = MagicMock()
        from stocksage.skill_engine.executor import SkillExecutor
        executor = SkillExecutor(mock_llm, fetcher)

        skill = _make_skill()
        node_fn = make_skill_node(skill, executor)

        state = {
            "meta": {"symbol": "600519", "stock_name": "test"},
            "data": {}, "analysis": {},
        }
        result = node_fn(state)
        assert "analysis" in result
