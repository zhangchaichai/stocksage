"""SkillExecutor streaming tests."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, AsyncMock

import pytest

from stocksage.skill_engine.executor import SkillExecutor
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
    prompt: str = "分析 {{ symbol }}",
    output_target: str = "state.analysis.test",
) -> SkillDef:
    return SkillDef(
        name=name,
        type=skill_type,
        interface=SkillInterface(
            inputs=[InputField(name="symbol", source="state.meta.symbol")],
            outputs=[OutputField(name="result", target=output_target)],
        ),
        execution=ExecutionConfig(model="test-model", temperature=0.5, max_tokens=100),
        prompt_template=prompt,
    )


class TestExecuteStreaming:
    @pytest.mark.asyncio
    async def test_streaming_yields_chunks_and_returns_result(self):
        """execute_streaming should call on_chunk for each token and return full result."""
        # Mock LLM with async stream
        mock_llm = MagicMock()
        mock_llm.provider_name = "test"

        async def mock_stream(messages, **kwargs):
            for chunk in ['{"action":', ' "buy",', ' "confidence":', ' 0.8}']:
                yield chunk

        mock_llm.stream = mock_stream
        mock_llm.call = MagicMock(return_value='{"action": "buy", "confidence": 0.8}')

        fetcher = MagicMock()
        executor = SkillExecutor(mock_llm, fetcher)
        skill = _make_skill()

        chunks_received: list[str] = []

        async def on_chunk(chunk: str) -> None:
            chunks_received.append(chunk)

        state = {"meta": {"symbol": "600519", "stock_name": "贵州茅台"}, "data": {}, "analysis": {}}
        result = await executor.execute_streaming(skill, state, on_chunk=on_chunk)

        # Verify chunks were received
        assert len(chunks_received) == 4
        assert ''.join(chunks_received) == '{"action": "buy", "confidence": 0.8}'

        # Verify result is properly routed
        assert "analysis" in result
        assert result["analysis"]["test"]["action"] == "buy"

    @pytest.mark.asyncio
    async def test_streaming_data_skill_no_chunks(self):
        """Data skills should not stream, just return result directly."""
        mock_llm = MagicMock()
        mock_llm.provider_name = "test"
        fetcher = MagicMock()
        fetcher.fetch_stock_info = MagicMock(return_value={"name": "贵州茅台"})

        executor = SkillExecutor(mock_llm, fetcher)
        skill = _make_skill(
            name="fetch_stock_info",
            skill_type="data",
            output_target="state.data.stock_info",
        )

        chunks_received: list[str] = []

        async def on_chunk(chunk: str) -> None:
            chunks_received.append(chunk)

        state = {"meta": {"symbol": "600519"}, "data": {}}
        result = await executor.execute_streaming(skill, state, on_chunk=on_chunk)

        # No chunks for data skills
        assert len(chunks_received) == 0
        # Result still returned
        assert "data" in result

    @pytest.mark.asyncio
    async def test_streaming_without_callback(self):
        """execute_streaming should work even without on_chunk callback."""
        mock_llm = MagicMock()
        mock_llm.provider_name = "test"

        async def mock_stream(messages, **kwargs):
            yield '{"result": "ok"}'

        mock_llm.stream = mock_stream

        fetcher = MagicMock()
        executor = SkillExecutor(mock_llm, fetcher)
        skill = _make_skill()

        state = {"meta": {"symbol": "600519", "stock_name": "贵州茅台"}, "data": {}, "analysis": {}}
        result = await executor.execute_streaming(skill, state, on_chunk=None)

        assert "analysis" in result

    @pytest.mark.asyncio
    async def test_streaming_coordinator_extracts_round3(self):
        """Coordinator streaming should extract round3_decision."""
        mock_llm = MagicMock()
        mock_llm.provider_name = "test"

        async def mock_stream(messages, **kwargs):
            yield '{"round3_decision": {"need_round3": true}, "summary": "ok"}'

        mock_llm.stream = mock_stream

        fetcher = MagicMock()
        executor = SkillExecutor(mock_llm, fetcher)
        skill = _make_skill(
            name="panel_coordinator",
            skill_type="coordinator",
            output_target="state.expert_panel.coordinator",
        )

        state = {"meta": {"symbol": "600519", "stock_name": "test"}, "data": {}, "analysis": {}, "expert_panel": {}}
        result = await executor.execute_streaming(skill, state, on_chunk=None)

        assert "round3_decision" in result
        assert result["round3_decision"]["need_round3"] is True


class TestExecutorWithLlm:
    def test_with_llm_returns_new_instance(self):
        """with_llm should return a new executor with different LLM."""
        mock_llm1 = MagicMock()
        mock_llm1.provider_name = "deepseek"
        mock_llm2 = MagicMock()
        mock_llm2.provider_name = "openai"
        fetcher = MagicMock()

        executor1 = SkillExecutor(mock_llm1, fetcher)
        executor2 = executor1.with_llm(mock_llm2)

        assert executor1._llm is mock_llm1
        assert executor2._llm is mock_llm2
        assert executor1._fetcher is executor2._fetcher  # shared
        assert executor1 is not executor2

    def test_existing_execute_still_works(self):
        """Existing execute() method unchanged."""
        mock_llm = MagicMock()
        mock_llm.provider_name = "test"
        mock_llm.call = MagicMock(return_value='{"result": "ok"}')
        fetcher = MagicMock()

        executor = SkillExecutor(mock_llm, fetcher)
        skill = _make_skill()

        state = {"meta": {"symbol": "600519", "stock_name": "test"}, "data": {}, "analysis": {}}
        result = executor.execute(skill, state)

        assert "analysis" in result
        mock_llm.call.assert_called_once()
