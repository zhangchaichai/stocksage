"""SkillExecutor tests (Task 1.4).

Tests cover:
- deep_set utility function
- _route_outputs with declared targets vs fallback
- _extract_inputs from state
- execute() dispatching to correct path
- _fallback_route backward compat
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from stocksage.skill_engine.executor import SkillExecutor, deep_set, _DATA_SKILL_MAP
from stocksage.skill_engine.models import (
    ExecutionConfig,
    InputField,
    OutputField,
    SkillDef,
    SkillInterface,
)


# ============================================================
# Helpers
# ============================================================


def _make_skill(
    name: str = "test_skill",
    type: str = "agent",
    inputs: list[InputField] | None = None,
    outputs: list[OutputField] | None = None,
    prompt_template: str = "Analyze {{ symbol }}",
) -> SkillDef:
    """Create a SkillDef for testing."""
    return SkillDef(
        name=name,
        type=type,
        interface=SkillInterface(
            inputs=inputs or [],
            outputs=outputs or [],
        ),
        execution=ExecutionConfig(model="test-model", temperature=0.5, max_tokens=100),
        prompt_template=prompt_template,
    )


def _make_executor(llm_response: str = '{"result": "ok"}') -> tuple[SkillExecutor, MagicMock, MagicMock]:
    """Create a SkillExecutor with mocked LLM and DataFetcher."""
    mock_llm = MagicMock()
    mock_llm.call.return_value = llm_response

    mock_fetcher = MagicMock()
    mock_fetcher.fetch_stock_info.return_value = {"name": "Test Stock"}
    mock_fetcher.fetch_price_data.return_value = {"klines": []}

    executor = SkillExecutor(llm=mock_llm, data_fetcher=mock_fetcher)
    return executor, mock_llm, mock_fetcher


# ============================================================
# deep_set tests
# ============================================================


class TestDeepSet:
    def test_single_level(self):
        d = deep_set({}, "state.decision", {"action": "buy"})
        assert d == {"decision": {"action": "buy"}}

    def test_two_levels(self):
        d = deep_set({}, "state.analysis.technical", {"ma5": 100})
        assert d == {"analysis": {"technical": {"ma5": 100}}}

    def test_three_levels(self):
        d = deep_set({}, "state.data.price.klines", [1, 2, 3])
        assert d == {"data": {"price": {"klines": [1, 2, 3]}}}

    def test_without_state_prefix(self):
        d = deep_set({}, "analysis.technical", {"rsi": 50})
        assert d == {"analysis": {"technical": {"rsi": 50}}}

    def test_preserves_existing_keys(self):
        d = {"analysis": {"fundamental": {"pe": 20}}}
        deep_set(d, "state.analysis.technical", {"rsi": 50})
        assert d["analysis"]["fundamental"] == {"pe": 20}
        assert d["analysis"]["technical"] == {"rsi": 50}

    def test_empty_path_after_stripping(self):
        d = {"x": 1}
        result = deep_set(d, "state", "value")
        # "state" stripped → no parts → unchanged
        assert result == {"x": 1}

    def test_overwrites_non_dict_intermediate(self):
        d = {"analysis": "old_string"}
        deep_set(d, "state.analysis.technical", {"rsi": 50})
        assert d["analysis"] == {"technical": {"rsi": 50}}

    def test_mutates_in_place(self):
        d = {}
        result = deep_set(d, "state.x", 1)
        assert result is d
        assert d == {"x": 1}


# ============================================================
# _route_outputs tests
# ============================================================


class TestRouteOutputs:
    def test_declared_target(self):
        executor, _, _ = _make_executor()
        skill = _make_skill(
            type="agent",
            outputs=[OutputField(name="result", target="state.analysis.technical_analyst")],
        )
        result = {"score": 8}
        update = executor._route_outputs(skill, result)
        assert update == {"analysis": {"technical_analyst": {"score": 8}}}

    def test_declared_target_with_trace(self):
        executor, _, _ = _make_executor()
        skill = _make_skill(
            name="tech",
            type="agent",
            outputs=[OutputField(name="result", target="state.analysis.tech")],
        )
        update = executor._route_outputs(skill, {"x": 1}, raw_response='```json\n{"x":1}\n```')
        assert update["analysis"]["tech"] == {"x": 1}
        assert update["llm_traces"]["tech"] == '{"x":1}'

    def test_fallback_agent(self):
        executor, _, _ = _make_executor()
        skill = _make_skill(name="my_agent", type="agent", outputs=[])
        update = executor._route_outputs(skill, {"a": 1})
        assert update == {"analysis": {"my_agent": {"a": 1}}}

    def test_fallback_decision(self):
        executor, _, _ = _make_executor()
        skill = _make_skill(name="judge", type="decision", outputs=[])
        update = executor._route_outputs(skill, {"verdict": "buy"})
        assert update == {"decision": {"verdict": "buy"}}

    def test_fallback_debate(self):
        executor, _, _ = _make_executor()
        skill = _make_skill(name="bull_advocate", type="debate", outputs=[])
        update = executor._route_outputs(skill, {"stance": "bull"})
        assert update == {"debate": {"bull_advocate": {"stance": "bull"}}}

    def test_fallback_expert(self):
        executor, _, _ = _make_executor()
        skill = _make_skill(name="quality_checker", type="expert", outputs=[])
        update = executor._route_outputs(skill, {"quality": "high"})
        assert update == {"expert_panel": {"quality_checker": {"quality": "high"}}}

    def test_fallback_data(self):
        executor, _, _ = _make_executor()
        skill = _make_skill(name="fetch_news", type="data", outputs=[])
        update = executor._route_outputs(skill, [{"title": "news"}])
        assert update == {"data": {"news": [{"title": "news"}]}}

    def test_no_target_no_outputs(self):
        executor, _, _ = _make_executor()
        skill = _make_skill(
            type="agent",
            outputs=[OutputField(name="result", target=None)],
        )
        # target is None → not in declared list → fallback
        update = executor._route_outputs(skill, {"x": 1})
        assert "analysis" in update


# ============================================================
# execute() dispatch tests
# ============================================================


class TestExecuteDispatch:
    def test_data_skill(self):
        executor, _, mock_fetcher = _make_executor()
        skill = _make_skill(
            name="fetch_stock_info",
            type="data",
            outputs=[OutputField(name="info", target="state.data.stock_info")],
        )
        state = {"meta": {"symbol": "600519"}}
        result = executor.execute(skill, state)
        mock_fetcher.fetch_stock_info.assert_called_once_with("600519")
        assert result["data"]["stock_info"] == {"name": "Test Stock"}

    def test_agent_skill(self):
        executor, mock_llm, _ = _make_executor('{"score": 8}')
        skill = _make_skill(
            name="technical_analyst",
            type="agent",
            outputs=[OutputField(name="result", target="state.analysis.technical_analyst")],
            prompt_template="Analyze {{ symbol }}",
        )
        state = {"meta": {"symbol": "600519", "stock_name": "贵州茅台"}}
        result = executor.execute(skill, state)
        mock_llm.call.assert_called_once()
        assert result["analysis"]["technical_analyst"] == {"score": 8}
        assert "llm_traces" in result

    def test_debate_skill(self):
        executor, mock_llm, _ = _make_executor('{"stance": "bull"}')
        skill = _make_skill(
            name="bull_advocate",
            type="debate",
            outputs=[OutputField(name="result", target="state.debate.bull_advocate")],
            prompt_template="Debate {{ symbol }}",
        )
        state = {"meta": {"symbol": "600519"}, "debate": {}}
        result = executor.execute(skill, state)
        assert result["debate"]["bull_advocate"] == {"stance": "bull"}

    def test_coordinator_extracts_round3(self):
        r3_response = '{"expert_panel_summary": {}, "round3_decision": {"need_round3": true}}'
        executor, mock_llm, _ = _make_executor(r3_response)
        skill = _make_skill(
            name="panel_coordinator",
            type="coordinator",
            outputs=[OutputField(name="result", target="state.expert_panel.coordinator")],
            prompt_template="Coordinate {{ symbol }}",
        )
        state = {"meta": {"symbol": "600519"}, "expert_panel": {}, "debate": {}}
        result = executor.execute(skill, state)
        assert result["round3_decision"]["need_round3"] is True
        assert "expert_panel" in result

    def test_unknown_type_returns_empty(self):
        executor, _, _ = _make_executor()
        skill = _make_skill(type="unknown_type")
        result = executor.execute(skill, {"meta": {}})
        assert result == {}


# ============================================================
# _extract_inputs tests
# ============================================================


class TestExtractInputs:
    def test_basic_meta_injection(self):
        executor, _, _ = _make_executor()
        skill = _make_skill(inputs=[])
        state = {"meta": {"symbol": "600519", "stock_name": "贵州茅台"}, "data": {"x": 1}, "analysis": {}}
        ctx = executor._extract_inputs(skill, state)
        assert ctx["symbol"] == "600519"
        assert ctx["stock_name"] == "贵州茅台"
        assert ctx["data"] == {"x": 1}

    def test_declared_source(self):
        executor, _, _ = _make_executor()
        skill = _make_skill(
            inputs=[InputField(name="price_data", source="state.data.price_data")],
        )
        state = {"meta": {}, "data": {"price_data": {"klines": [1, 2]}}, "analysis": {}}
        ctx = executor._extract_inputs(skill, state)
        assert ctx["price_data"] == {"klines": [1, 2]}

    def test_fallback_to_state_key(self):
        executor, _, _ = _make_executor()
        skill = _make_skill(
            inputs=[InputField(name="debate", source=None)],
        )
        state = {"meta": {}, "data": {}, "analysis": {}, "debate": {"round1": "data"}}
        ctx = executor._extract_inputs(skill, state)
        assert ctx["debate"] == {"round1": "data"}


# ============================================================
# _parse_response / _strip_code_fences tests
# ============================================================


class TestParseResponse:
    def test_valid_json(self):
        executor, _, _ = _make_executor()
        assert executor._parse_response('{"a": 1}') == {"a": 1}

    def test_json_in_code_fence(self):
        executor, _, _ = _make_executor()
        assert executor._parse_response('```json\n{"a": 1}\n```') == {"a": 1}

    def test_empty_response(self):
        executor, _, _ = _make_executor()
        result = executor._parse_response("")
        assert result["error"] == "empty_response"

    def test_invalid_json(self):
        executor, _, _ = _make_executor()
        result = executor._parse_response("not json at all")
        assert result["error"] == "json_decode_error"


class TestStripCodeFences:
    def test_no_fences(self):
        assert SkillExecutor._strip_code_fences('{"a": 1}') == '{"a": 1}'

    def test_json_fence(self):
        assert SkillExecutor._strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_plain_fence(self):
        assert SkillExecutor._strip_code_fences('```\n{"a": 1}\n```') == '{"a": 1}'
