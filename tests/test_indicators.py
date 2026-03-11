"""Indicator computation tests."""

from __future__ import annotations

from stocksage.data.indicators import (
    _ma,
    _pct_diff,
    _rsi,
    _safe_float,
    _bollinger,
    _max_drawdown,
    _annualized_volatility,
    _ensure_dict,
    compute_all_indicators,
)


class TestHelpers:
    def test_safe_float_normal(self):
        assert _safe_float(3.14) == 3.14
        assert _safe_float("2.5") == 2.5
        assert _safe_float(0) == 0.0

    def test_safe_float_invalid(self):
        assert _safe_float(None) is None
        assert _safe_float("abc") is None
        assert _safe_float(float("nan")) is None
        assert _safe_float(float("inf")) is None

    def test_ma(self):
        series = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _ma(series, 3) == round((3 + 4 + 5) / 3, 4)
        assert _ma(series, 5) == round(sum(series) / 5, 4)
        assert _ma(series, 10) is None  # Not enough data

    def test_pct_diff(self):
        assert _pct_diff(110, 100) == 10.0
        assert _pct_diff(90, 100) == -10.0
        assert _pct_diff(100, 0) is None
        assert _pct_diff(None, 100) is None

    def test_ensure_dict(self):
        assert _ensure_dict({"a": 1}) == {"a": 1}
        assert _ensure_dict([1, 2]) == {"data": [1, 2]}
        assert _ensure_dict("x") == {}
        assert _ensure_dict(None) == {}


class TestTechnicalIndicators:
    def test_rsi(self):
        # Monotonically increasing -> RSI close to 100
        closes = [float(i) for i in range(1, 25)]
        rsi = _rsi(closes, 14)
        assert rsi is not None
        assert rsi > 90

    def test_rsi_insufficient_data(self):
        assert _rsi([1.0, 2.0], 14) is None

    def test_bollinger(self):
        closes = [100.0 + i * 0.1 for i in range(20)]
        boll = _bollinger(closes, 20)
        assert "boll_upper" in boll
        assert "boll_mid" in boll
        assert "boll_lower" in boll
        assert "boll_pct_position" in boll
        assert boll["boll_upper"] > boll["boll_mid"] > boll["boll_lower"]

    def test_bollinger_insufficient(self):
        assert _bollinger([1.0, 2.0], 20) == {}

    def test_max_drawdown(self):
        # Peak at 100, drop to 80 -> 20% drawdown
        closes = [100.0, 95.0, 80.0, 85.0, 90.0]
        dd = _max_drawdown(closes)
        assert dd == 20.0

    def test_max_drawdown_no_drawdown(self):
        closes = [1.0, 2.0, 3.0, 4.0]
        assert _max_drawdown(closes) == 0.0

    def test_annualized_volatility(self):
        closes = [100.0 + i for i in range(10)]
        vol = _annualized_volatility(closes)
        assert vol is not None
        assert vol > 0

    def test_annualized_volatility_insufficient(self):
        assert _annualized_volatility([1.0, 2.0]) is None


class TestComputeAllIndicators:
    def test_empty_data(self):
        result = compute_all_indicators({})
        assert result == {}

    def test_with_klines(self, sample_klines):
        data = {"price_data": {"klines": sample_klines}}
        result = compute_all_indicators(data)
        assert "technical" in result
        tech = result["technical"]
        assert "ma5" in tech
        assert "rsi_14" in tech
        assert "latest_price" in tech

    def test_with_stock_info(self):
        data = {"stock_info": {"市盈率(动态)": "25.5", "市净率": "3.2"}}
        result = compute_all_indicators(data)
        assert "fundamental" in result
        assert result["fundamental"]["pe_ttm"] == 25.5
        assert result["fundamental"]["pb"] == 3.2
