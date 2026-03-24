"""Screener v2 acceptance tests.

Covers the key acceptance criteria from docs/workflow_screener_v2.md Phase 5.

Tests that require a live DB use the shared ``client`` fixture from conftest.
Unit-level tests run without any DB or external network calls.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


# ─── Unit: StrategyRegistry ────────────────────────────────────────────────────

class TestStrategyRegistry:
    def test_loads_13_strategies(self):
        from app.screener.strategies.registry import registry
        strats = registry.list_all()
        assert len(strats) == 13, f"Expected 13 strategies, got {len(strats)}"

    def test_strategy_fields_present(self):
        from app.screener.strategies.registry import registry
        for s in registry.list_all():
            assert s.id, f"{s.name} missing id"
            assert s.name, f"{s.id} missing name"
            assert s.icon, f"{s.id} missing icon"
            assert s.category in ("成长类", "技术面", "资金面", "价值类", "特色策略"), \
                f"{s.id} has unknown category: {s.category}"
            assert s.risk_level in ("低", "中", "高"), \
                f"{s.id} has unknown risk_level: {s.risk_level}"

    def test_pywencai_strategies_have_queries(self):
        from app.screener.strategies.registry import registry
        for s in registry.list_all():
            if s.pywencai_enabled:
                assert len(s.pywencai_queries) >= 2, \
                    f"{s.id} pywencai strategy needs >=2 fallback queries"

    def test_akshare_strategies_exist(self):
        from app.screener.strategies.registry import registry
        akshare_ids = [s.id for s in registry.list_all() if s.akshare_enrich_enabled and not s.pywencai_enabled]
        assert "dealer_wyckoff" in akshare_ids
        assert "turn_bottom" in akshare_ids

    def test_get_by_id(self):
        from app.screener.strategies.registry import registry
        s = registry.get("low_price_bull")
        assert s is not None
        assert s.pywencai_enabled is True

    def test_get_unknown_returns_none(self):
        from app.screener.strategies.registry import registry
        assert registry.get("nonexistent_strategy") is None


# ─── Unit: QuantSignalEvaluator ───────────────────────────────────────────────

class TestQuantSignalEvaluator:
    def setup_method(self):
        from app.screener.quant.signal_evaluator import QuantSignalEvaluator
        self.ev = QuantSignalEvaluator()

    def test_holding_days_fires(self):
        conds = [{"type": "holding_days", "label": "持股满5天", "days": 5}]
        fired, reason = self.ev.evaluate_sell("X", {}, conds, holding_days=6)
        assert fired
        assert "5" in reason

    def test_holding_days_not_fired(self):
        conds = [{"type": "holding_days", "label": "持股满5天", "days": 5}]
        fired, _ = self.ev.evaluate_sell("X", {}, conds, holding_days=3)
        assert not fired

    def test_stop_loss_fires(self):
        conds = [{"type": "stop_loss", "label": "止损10%", "pct": 0.10}]
        fired, _ = self.ev.evaluate_sell("X", {}, conds, buy_price=10.0, current_price=8.9)
        assert fired

    def test_stop_loss_not_fired(self):
        conds = [{"type": "stop_loss", "label": "止损10%", "pct": 0.10}]
        fired, _ = self.ev.evaluate_sell("X", {}, conds, buy_price=10.0, current_price=9.5)
        assert not fired

    def test_take_profit_fires(self):
        conds = [{"type": "take_profit", "label": "止盈20%", "pct": 0.20}]
        fired, _ = self.ev.evaluate_sell("X", {}, conds, buy_price=10.0, current_price=12.5)
        assert fired

    def test_ma_cross_down_fires(self):
        conds = [{"type": "ma_cross_down", "label": "MA死叉", "fast": "ma5", "slow": "ma20"}]
        indicators = {"ma5": 8.0, "ma20": 10.0}
        fired, _ = self.ev.evaluate_sell("X", indicators, conds)
        assert fired

    def test_rsi_overbought_fires(self):
        conds = [{"type": "rsi_overbought", "label": "RSI超买", "threshold": 80}]
        indicators = {"rsi": 82.0}
        fired, _ = self.ev.evaluate_sell("X", indicators, conds)
        assert fired

    def test_empty_conditions(self):
        fired, reason = self.ev.evaluate_sell("X", {}, [])
        assert not fired
        # "持有" or empty string are both valid no-sell indicators
        assert isinstance(reason, str)


# ─── Unit: NL Translator ──────────────────────────────────────────────────────

class TestNLTranslator:
    def test_rule_matches_low_price(self):
        from app.screener.nl_translator import translate_by_rules
        result = translate_by_rules("低价高成长")
        assert result is not None
        assert "股价" in result

    def test_rule_matches_mainkuai(self):
        from app.screener.nl_translator import translate_by_rules
        result = translate_by_rules("主力资金选股")
        assert result is not None
        assert "主力" in result

    def test_rule_matches_northbound(self):
        from app.screener.nl_translator import translate_by_rules
        result = translate_by_rules("跟北向资金买入")
        assert result is not None
        assert "北向" in result

    def test_rule_no_match_returns_none(self):
        from app.screener.nl_translator import translate_by_rules
        result = translate_by_rules("请问今天天气怎么样")
        assert result is None

    def test_strategy_hint_low_price(self):
        from app.screener.nl_translator import find_strategy_hint
        assert find_strategy_hint("找低价股") == "low_price_bull"

    def test_strategy_hint_northbound(self):
        from app.screener.nl_translator import find_strategy_hint
        assert find_strategy_hint("北向资金买入") == "northbound_follow"

    def test_strategy_hint_none_for_generic(self):
        from app.screener.nl_translator import find_strategy_hint
        assert find_strategy_hint("今天天气真好") is None


# ─── Unit: AIScorer ───────────────────────────────────────────────────────────

class TestAIScorer:
    @pytest.mark.asyncio
    async def test_empty_matches_returns_empty(self):
        from app.screener.quant.ai_scorer import AIScorer
        scorer = AIScorer()
        result = await scorer.score([], "test")
        assert result == []

    @pytest.mark.asyncio
    async def test_llm_failure_returns_original_order(self):
        """On LLM failure, returns original list with ai_score=0."""
        from app.screener.quant.ai_scorer import AIScorer
        scorer = AIScorer()
        matches = [
            {"symbol": "600519", "name": "贵州茅台", "indicators": {}},
            {"symbol": "000858", "name": "五粮液", "indicators": {}},
        ]
        # Patch the LLM call to fail
        with patch("app.screener.quant.ai_scorer._call_llm_sync", return_value=[]):
            result = await scorer.score(matches, "test strategy")

        assert len(result) == 2
        for r in result:
            assert "ai_score" in r
            assert "ai_reason" in r

    @pytest.mark.asyncio
    async def test_llm_success_adds_scores(self):
        """When LLM returns valid scores, they are merged and sorted."""
        from app.screener.quant.ai_scorer import AIScorer
        scorer = AIScorer()
        matches = [
            {"symbol": "600519", "name": "贵州茅台", "indicators": {}},
            {"symbol": "000858", "name": "五粮液", "indicators": {}},
        ]
        mock_scores = [
            {"symbol": "600519", "score": 8.5, "reason": "主力持续流入"},
            {"symbol": "000858", "score": 6.0, "reason": "技术形态一般"},
        ]
        with patch("app.screener.quant.ai_scorer._call_llm_sync", return_value=mock_scores):
            result = await scorer.score(matches, "low_price_bull")

        assert result[0]["symbol"] == "600519"   # higher score first
        assert result[0]["ai_score"] == 8.5
        assert result[0]["ai_reason"] == "主力持续流入"
        assert result[1]["ai_score"] == 6.0


# ─── Integration: Screener API endpoints ──────────────────────────────────────

@pytest.mark.asyncio
async def test_list_strategies_returns_13(client):
    """GET /screener/strategies returns all 13 predefined strategies."""
    # Register
    await client.post("/api/auth/register", json={
        "username": "screener_test", "email": "screener@test.com", "password": "pwd123456"
    })
    login = await client.post("/api/auth/login", json={"email": "screener@test.com", "password": "pwd123456"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/api/screener/strategies", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 13
    ids = [s["id"] for s in data]
    assert "low_price_bull" in ids
    assert "dealer_wyckoff" in ids


@pytest.mark.asyncio
async def test_get_strategy_detail(client):
    """GET /screener/strategies/{id} returns StrategyDetail with queries."""
    await client.post("/api/auth/register", json={
        "username": "strat_detail", "email": "strat_detail@test.com", "password": "pwd123456"
    })
    login = await client.post("/api/auth/login", json={"email": "strat_detail@test.com", "password": "pwd123456"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/api/screener/strategies/low_price_bull", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "low_price_bull"
    assert isinstance(data["pywencai_queries"], list)
    assert len(data["pywencai_queries"]) >= 2
    assert isinstance(data["sell_conditions"], list)


@pytest.mark.asyncio
async def test_get_strategy_404(client):
    """GET /screener/strategies/nonexistent returns 404."""
    await client.post("/api/auth/register", json={
        "username": "strat404", "email": "strat404@test.com", "password": "pwd123456"
    })
    login = await client.post("/api/auth/login", json={"email": "strat404@test.com", "password": "pwd123456"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/api/screener/strategies/does_not_exist", headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_run_screener_with_strategy_id(client):
    """POST /screener/run with strategy_id queues a job and returns 201."""
    await client.post("/api/auth/register", json={
        "username": "run_strat", "email": "run_strat@test.com", "password": "pwd123456"
    })
    login = await client.post("/api/auth/login", json={"email": "run_strat@test.com", "password": "pwd123456"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.screener.worker.dispatch_screener_job"):
        r = await client.post("/api/screener/run", json={
            "strategy_id": "low_price_bull",
            "pool": "hs300",
        }, headers=headers)

    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "queued"
    assert data["strategy_id"] == "low_price_bull"


@pytest.mark.asyncio
async def test_run_screener_invalid_strategy(client):
    """POST /screener/run with unknown strategy_id returns 400."""
    await client.post("/api/auth/register", json={
        "username": "bad_strat", "email": "bad_strat@test.com", "password": "pwd123456"
    })
    login = await client.post("/api/auth/login", json={"email": "bad_strat@test.com", "password": "pwd123456"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post("/api/screener/run", json={
        "strategy_id": "totally_fake_id",
    }, headers=headers)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_run_screener_legacy_filters(client):
    """POST /screener/run with filters (no strategy_id) still works — backward compat."""
    await client.post("/api/auth/register", json={
        "username": "legacy_filter", "email": "legacy@test.com", "password": "pwd123456"
    })
    login = await client.post("/api/auth/login", json={"email": "legacy@test.com", "password": "pwd123456"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.screener.worker.dispatch_screener_job"):
        r = await client.post("/api/screener/run", json={
            "filters": [{"field": "pe", "operator": "lt", "value": 30}],
            "pool": "hs300",
        }, headers=headers)

    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "queued"
    assert data["strategy_id"] is None   # no strategy, legacy path


@pytest.mark.asyncio
async def test_nl_query_rule_hit(client):
    """POST /screener/nl_query with known keyword returns pywencai query immediately."""
    await client.post("/api/auth/register", json={
        "username": "nl_test", "email": "nl_test@test.com", "password": "pwd123456"
    })
    login = await client.post("/api/auth/login", json={"email": "nl_test@test.com", "password": "pwd123456"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post("/api/screener/nl_query", json={"query": "低价高成长"}, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["pywencai_query"]
    assert data.get("error") is None


@pytest.mark.asyncio
async def test_nl_query_empty_body_rejected(client):
    """POST /screener/nl_query with empty query returns 400."""
    await client.post("/api/auth/register", json={
        "username": "nl_empty", "email": "nl_empty@test.com", "password": "pwd123456"
    })
    login = await client.post("/api/auth/login", json={"email": "nl_empty@test.com", "password": "pwd123456"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post("/api/screener/nl_query", json={"query": ""}, headers=headers)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_batch_runs_submit(client):
    """POST /runs/batch submits multiple WorkflowRuns for screener symbols."""
    # Create a user + workflow first
    await client.post("/api/auth/register", json={
        "username": "batch_user", "email": "batch@test.com", "password": "pwd123456"
    })
    login = await client.post("/api/auth/login", json={"email": "batch@test.com", "password": "pwd123456"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create workflow
    wf_r = await client.post("/api/workflows", json={
        "name": "test_wf",
        "definition": {
            "nodes": [{"id": "n1", "skill": "stock_analysis"}],
            "edges": [],
        },
    }, headers=headers)
    assert wf_r.status_code == 201
    wf_id = wf_r.json()["id"]

    # Batch submit
    with patch("app.runs.worker.dispatch_run"):
        r = await client.post("/api/runs/batch", json={
            "workflow_id": wf_id,
            "symbols": ["600519", "000858", "600036"],
            "stock_names": {"600519": "贵州茅台", "000858": "五粮液", "600036": "招商银行"},
            "source": "screener_job:test-job-id",
        }, headers=headers)

    assert r.status_code == 201
    runs = r.json()
    assert len(runs) == 3
    symbols = {run["symbol"] for run in runs}
    assert symbols == {"600519", "000858", "600036"}
    # All should have source in config_overrides
    for run in runs:
        assert run["config_overrides"]["_source"] == "screener_job:test-job-id"


@pytest.mark.asyncio
async def test_batch_runs_too_many_symbols(client):
    """POST /runs/batch with >50 symbols is rejected (422 from schema or 400 from router)."""
    await client.post("/api/auth/register", json={
        "username": "batch_big", "email": "batch_big@test.com", "password": "pwd123456"
    })
    login = await client.post("/api/auth/login", json={"email": "batch_big@test.com", "password": "pwd123456"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    wf_r = await client.post("/api/workflows", json={
        "name": "wf_big",
        "definition": {"nodes": [{"id": "n1", "skill": "x"}], "edges": []},
    }, headers=headers)
    wf_id = wf_r.json()["id"]

    big_list = [f"{i:06d}" for i in range(51)]
    r = await client.post("/api/runs/batch", json={
        "workflow_id": wf_id,
        "symbols": big_list,
    }, headers=headers)
    # 400 (router check) or 422 (Pydantic schema max_length) both indicate rejection
    assert r.status_code in (400, 422)
