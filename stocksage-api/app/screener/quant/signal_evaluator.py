"""Quantitative sell/buy signal evaluator.

Ported and generalised from aiagents-stock/low_price_bull_strategy.py
LowPriceBullStrategy.should_sell().
"""

from __future__ import annotations

from typing import Any


class QuantSignalEvaluator:
    """Evaluate buy/sell signals defined in a strategy's quant_signals section."""

    def evaluate_sell(
        self,
        symbol: str,
        indicators: dict[str, Any],
        sell_conditions: list,
        holding_days: int = 0,
        buy_price: float | None = None,
        current_price: float | None = None,
    ) -> tuple[bool, str]:
        """Check whether any sell condition is triggered.

        Returns:
            (should_sell, reason)
        """
        for cond in sell_conditions:
            ctype = cond.type if hasattr(cond, "type") else cond.get("type", "")
            label = cond.label if hasattr(cond, "label") else cond.get("label", ctype)
            params = cond.params if hasattr(cond, "params") else {
                k: v for k, v in cond.items() if k not in ("type", "label")
            }

            if ctype == "ma_cross_down":
                fast_key = params.get("fast_ma", "ma5")
                slow_key = params.get("slow_ma", "ma20")
                fast = self._get(indicators, fast_key)
                slow = self._get(indicators, slow_key)
                if fast is not None and slow is not None:
                    try:
                        if float(fast) < float(slow):
                            return True, label
                    except (TypeError, ValueError):
                        pass

            elif ctype == "holding_days":
                days_limit = int(params.get("days", 5))
                if holding_days >= days_limit:
                    return True, f"持股满{days_limit}天"

            elif ctype == "stop_loss":
                pct = float(params.get("pct", 0.08))
                if buy_price and current_price:
                    try:
                        change = (float(current_price) - float(buy_price)) / float(buy_price)
                        if change <= -pct:
                            return True, f"止损{pct * 100:.0f}%"
                    except (TypeError, ValueError, ZeroDivisionError):
                        pass

            elif ctype == "take_profit":
                pct = float(params.get("pct", 0.20))
                if buy_price and current_price:
                    try:
                        change = (float(current_price) - float(buy_price)) / float(buy_price)
                        if change >= pct:
                            return True, f"止盈{pct * 100:.0f}%"
                    except (TypeError, ValueError, ZeroDivisionError):
                        pass

            elif ctype == "rsi_overbought":
                threshold = float(params.get("threshold", 80))
                rsi_val = self._get(indicators, "rsi") or self._get(indicators, "rsi14")
                if rsi_val is not None:
                    try:
                        if float(rsi_val) >= threshold:
                            return True, f"RSI超买({float(rsi_val):.1f}≥{threshold:.0f})"
                    except (TypeError, ValueError):
                        pass

        return False, "持有"

    def evaluate_buy(
        self,
        symbol: str,
        indicators: dict[str, Any],
        buy_conditions: list,
    ) -> tuple[bool, list[str]]:
        """Check all buy conditions (for display/annotation only — not blocking).

        Returns:
            (all_pass, list_of_matched_labels)
        """
        matched: list[str] = []
        for cond in buy_conditions:
            field = cond.get("field", "") if isinstance(cond, dict) else getattr(cond, "field", "")
            op = cond.get("operator", "") if isinstance(cond, dict) else getattr(cond, "operator", "")
            value = cond.get("value") if isinstance(cond, dict) else getattr(cond, "value", None)
            label = cond.get("label", field) if isinstance(cond, dict) else getattr(cond, "label", field)

            actual = self._get(indicators, field)
            if actual is None or value is None:
                continue
            try:
                a, v = float(actual), float(value)
                hit = (
                    (op == "lt" and a < v) or
                    (op == "lte" and a <= v) or
                    (op == "gt" and a > v) or
                    (op == "gte" and a >= v) or
                    (op == "eq" and a == v) or
                    (op == "ne" and a != v)
                )
                if hit:
                    matched.append(label)
            except (TypeError, ValueError):
                pass

        all_pass = len(matched) > 0
        return all_pass, matched

    @staticmethod
    def _get(indicators: dict[str, Any], key: str) -> Any:
        """Flat or nested dict lookup."""
        if key in indicators:
            return indicators[key]
        for v in indicators.values():
            if isinstance(v, dict) and key in v:
                return v[key]
        return None
