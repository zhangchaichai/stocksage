"""计算工具：技术指标计算和估值计算。"""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any

from stocksage.agent.tools.base import Tool
from stocksage.data.fetcher import DataFetcher


class CalcIndicatorTool(Tool):
    """计算技术指标。"""

    def __init__(self, fetcher: DataFetcher):
        self._fetcher = fetcher

    @property
    def name(self) -> str:
        return "calc_indicator"

    @property
    def description(self) -> str:
        return "计算技术指标（MA, RSI, MACD, BOLL, KDJ, OBV, ATR, CCI）"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "股票代码"},
                "indicator": {
                    "type": "string",
                    "enum": ["MA", "RSI", "MACD", "BOLL", "KDJ", "OBV", "ATR", "CCI"],
                    "description": "指标名称",
                },
                "params": {
                    "type": "object",
                    "description": "指标参数，如 {\"period\": 20}",
                },
            },
            "required": ["symbol", "indicator"],
        }

    async def execute(
        self,
        symbol: str,
        indicator: str,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        # Fetch price data in thread to avoid blocking
        price_data = await asyncio.to_thread(
            self._fetcher.fetch_price_data, symbol, days=120,
        )
        if not price_data or "klines" not in price_data:
            return f"无法获取 {symbol} 的价格数据用于计算 {indicator}"

        try:
            from stocksage.data.indicators import compute_indicator

            result = await asyncio.to_thread(
                compute_indicator, price_data["klines"], indicator, params or {},
            )
            return json.dumps(result, ensure_ascii=False, indent=2)
        except ImportError:
            # Fallback: basic indicator calculation inline
            return self._calc_basic(price_data["klines"], indicator, params or {})
        except Exception as e:
            return f"计算 {indicator} 失败: {e!s}"

    def _calc_basic(
        self,
        klines: list[dict],
        indicator: str,
        params: dict[str, Any],
    ) -> str:
        """内联基础指标计算（当 indicators 模块不可用时）。"""
        try:
            closes = [float(k.get("收盘", k.get("close", 0))) for k in klines]
            highs = [float(k.get("最高", k.get("high", 0))) for k in klines]
            lows = [float(k.get("最低", k.get("low", 0))) for k in klines]
            volumes = [float(k.get("成交量", k.get("volume", 0))) for k in klines]

            if not closes:
                return "价格数据为空"

            if indicator == "MA":
                periods = params.get("periods", [5, 10, 20, 60])
                if isinstance(periods, int):
                    periods = [periods]
                result = {}
                for p in periods:
                    if len(closes) >= p:
                        ma = sum(closes[-p:]) / p
                        result[f"MA{p}"] = round(ma, 2)
                return json.dumps(result, ensure_ascii=False)

            if indicator == "RSI":
                period = params.get("period", 14)
                if len(closes) < period + 1:
                    return f"数据不足，需要至少 {period + 1} 天数据"
                gains, losses = [], []
                for i in range(1, len(closes)):
                    diff = closes[i] - closes[i - 1]
                    gains.append(max(0, diff))
                    losses.append(max(0, -diff))
                avg_gain = sum(gains[-period:]) / period
                avg_loss = sum(losses[-period:]) / period
                if avg_loss == 0:
                    rsi = 100.0
                else:
                    rs = avg_gain / avg_loss
                    rsi = 100 - (100 / (1 + rs))
                return json.dumps({"RSI": round(rsi, 2), "period": period}, ensure_ascii=False)

            if indicator == "MACD":
                fast = params.get("fast", 12)
                slow = params.get("slow", 26)
                signal = params.get("signal", 9)
                if len(closes) < slow + signal:
                    return f"数据不足，需要至少 {slow + signal} 天数据"
                ema_fast = self._ema(closes, fast)
                ema_slow = self._ema(closes, slow)
                dif = [f - s for f, s in zip(ema_fast[-len(ema_slow):], ema_slow)]
                dea = self._ema(dif, signal)
                macd_hist = [(d - e) * 2 for d, e in zip(dif[-len(dea):], dea)]
                return json.dumps({
                    "DIF": round(dif[-1], 4),
                    "DEA": round(dea[-1], 4),
                    "MACD": round(macd_hist[-1], 4),
                    "signal": "金叉" if dif[-1] > dea[-1] and dif[-2] <= dea[-2] else
                              "死叉" if dif[-1] < dea[-1] and dif[-2] >= dea[-2] else "持续",
                }, ensure_ascii=False)

            if indicator == "BOLL":
                period = params.get("period", 20)
                std_dev = params.get("std_dev", 2)
                if len(closes) < period:
                    return f"数据不足，需要至少 {period} 天数据"
                ma = sum(closes[-period:]) / period
                variance = sum((c - ma) ** 2 for c in closes[-period:]) / period
                sd = math.sqrt(variance)
                return json.dumps({
                    "中轨(MA)": round(ma, 2),
                    "上轨": round(ma + std_dev * sd, 2),
                    "下轨": round(ma - std_dev * sd, 2),
                    "带宽": round((std_dev * sd * 2) / ma * 100, 2),
                    "当前价位": round(
                        (closes[-1] - (ma - std_dev * sd)) / (std_dev * sd * 2) * 100, 1,
                    ) if sd > 0 else 50.0,
                }, ensure_ascii=False)

            if indicator == "KDJ":
                n = params.get("period", 9)
                if len(closes) < n:
                    return f"数据不足，需要至少 {n} 天数据"
                # RSV → K → D → J
                lowest = min(lows[-n:])
                highest = max(highs[-n:])
                if highest == lowest:
                    rsv = 50.0
                else:
                    rsv = (closes[-1] - lowest) / (highest - lowest) * 100
                # Simple smoothing (first K/D = 50)
                k_val = 2 / 3 * 50 + 1 / 3 * rsv
                d_val = 2 / 3 * 50 + 1 / 3 * k_val
                j_val = 3 * k_val - 2 * d_val
                return json.dumps({
                    "K": round(k_val, 2),
                    "D": round(d_val, 2),
                    "J": round(j_val, 2),
                }, ensure_ascii=False)

            if indicator == "OBV":
                if len(closes) < 2 or len(volumes) < 2:
                    return "数据不足"
                obv = 0.0
                for i in range(1, len(closes)):
                    if closes[i] > closes[i - 1]:
                        obv += volumes[i]
                    elif closes[i] < closes[i - 1]:
                        obv -= volumes[i]
                return json.dumps({
                    "OBV": round(obv, 0),
                    "OBV_MA5": round(obv, 0),  # simplified
                }, ensure_ascii=False)

            if indicator == "ATR":
                period = params.get("period", 14)
                if len(closes) < period + 1:
                    return f"数据不足，需要至少 {period + 1} 天数据"
                trs = []
                for i in range(1, len(closes)):
                    tr = max(
                        highs[i] - lows[i],
                        abs(highs[i] - closes[i - 1]),
                        abs(lows[i] - closes[i - 1]),
                    )
                    trs.append(tr)
                atr = sum(trs[-period:]) / period
                return json.dumps({
                    "ATR": round(atr, 4),
                    "ATR_pct": round(atr / closes[-1] * 100, 2) if closes[-1] else 0,
                }, ensure_ascii=False)

            if indicator == "CCI":
                period = params.get("period", 20)
                if len(closes) < period:
                    return f"数据不足，需要至少 {period} 天数据"
                tps = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
                tp_slice = tps[-period:]
                ma_tp = sum(tp_slice) / period
                md = sum(abs(tp - ma_tp) for tp in tp_slice) / period
                if md == 0:
                    cci = 0.0
                else:
                    cci = (tps[-1] - ma_tp) / (0.015 * md)
                return json.dumps({"CCI": round(cci, 2)}, ensure_ascii=False)

            return f"基础计算不支持 {indicator}，建议安装 stocksage.data.indicators 模块"
        except Exception as e:
            return f"基础计算失败: {e!s}"

    @staticmethod
    def _ema(data: list[float], period: int) -> list[float]:
        """计算 EMA。"""
        if not data:
            return []
        multiplier = 2 / (period + 1)
        ema_values = [data[0]]
        for price in data[1:]:
            ema_values.append(price * multiplier + ema_values[-1] * (1 - multiplier))
        return ema_values


class CalcValuationTool(Tool):
    """计算估值指标。"""

    def __init__(self, fetcher: DataFetcher):
        self._fetcher = fetcher

    @property
    def name(self) -> str:
        return "calc_valuation"

    @property
    def description(self) -> str:
        return "计算估值指标（PE, PB, PS, PEG, DCF 简化估值）"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "股票代码"},
                "method": {
                    "type": "string",
                    "enum": ["PE", "PB", "PS", "PEG", "DCF"],
                    "description": "估值方法",
                },
            },
            "required": ["symbol", "method"],
        }

    async def execute(
        self,
        symbol: str,
        method: str = "PE",
        **kwargs: Any,
    ) -> str:
        info = await asyncio.to_thread(self._fetcher.fetch_stock_info, symbol)
        financial = await asyncio.to_thread(self._fetcher.fetch_financial, symbol)

        if not info and not financial:
            return f"无法获取 {symbol} 的数据用于估值"

        result: dict[str, Any] = {"symbol": symbol, "method": method}

        if method == "PE" and info:
            pe = info.get("市盈率(动态)", info.get("pe_ratio"))
            result["PE_dynamic"] = pe
            result["comment"] = self._pe_comment(pe)
        elif method == "PB" and info:
            pb = info.get("市净率", info.get("pb_ratio"))
            result["PB"] = pb
        elif method == "PS" and info:
            ps = info.get("市销率", info.get("ps_ratio"))
            result["PS"] = ps
        else:
            result["note"] = f"未能获取 {method} 估值所需数据"

        return json.dumps(result, ensure_ascii=False, indent=2)

    @staticmethod
    def _pe_comment(pe: Any) -> str:
        try:
            pe_val = float(pe)
            if pe_val < 0:
                return "亏损，PE 无意义"
            if pe_val < 15:
                return "低估值区间"
            if pe_val < 25:
                return "合理估值区间"
            if pe_val < 40:
                return "偏高估值"
            return "高估值"
        except (TypeError, ValueError):
            return "PE 数据异常"
