"""量化指标预计算模块。

在数据获取后、分析师调用前，将原始数据预处理为结构化的量化指标，
让 LLM 分析师能基于精确数值而非自行推算。
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


def _ensure_dict(val: Any) -> dict:
    """确保值为 dict，非 dict 类型包装或返回空 dict。"""
    if isinstance(val, dict):
        return val
    if isinstance(val, list):
        return {"data": val}
    return {}


def compute_all_indicators(data: dict) -> dict:
    """根据已获取的原始数据，计算所有量化指标。

    Args:
        data: WorkflowState 中的 data 字典

    Returns:
        indicators 字典，包含各维度的预计算指标
    """
    indicators: dict[str, Any] = {}

    # 技术指标
    price_data = _ensure_dict(data.get("price_data", {}))
    klines = price_data.get("klines", [])
    if klines:
        indicators["technical"] = _compute_technical(klines)
        indicators["kbar"] = _compute_kbar_features(klines)
        indicators["rolling"] = _compute_rolling_features(klines)
        indicators["ashare"] = _compute_ashare_factors(klines)
        indicators["risk"] = _compute_risk_metrics(klines)

    # 财务指标
    stock_info = _ensure_dict(data.get("stock_info", {}))
    financial = _ensure_dict(data.get("financial", {}))
    quarterly = _ensure_dict(data.get("quarterly", {}))
    balance_sheet = _ensure_dict(data.get("balance_sheet", {}))
    if stock_info or financial:
        indicators["fundamental"] = _compute_fundamental(
            stock_info, financial, quarterly, balance_sheet
        )

    # 资金流指标
    fund_flow = _ensure_dict(data.get("fund_flow", {}))
    if fund_flow:
        indicators["fund_flow"] = _compute_fund_flow(fund_flow)

    # 融资融券趋势
    margin = _ensure_dict(data.get("margin", {}))
    if margin:
        indicators["margin"] = _compute_margin_trend(margin)

    # 庄家行为指标 (Phase 2)
    if klines:
        closes = _extract_series(klines, "收盘")
        volumes = _extract_series(klines, "成交量")
        dealer: dict[str, Any] = {}
        wyckoff = _compute_wyckoff(klines)
        if wyckoff:
            dealer.update(wyckoff)
        obv_div = _compute_obv_divergence(closes, volumes)
        if obv_div:
            dealer.update(obv_div)
        chip = _compute_chip_distribution(klines)
        if chip:
            dealer.update({f"chip_{k}": v for k, v in chip.items()})
        dist_sig = _compute_distribution_signals(klines)
        if dist_sig:
            dealer.update({f"dist_{k}": v for k, v in dist_sig.items()})
        if dealer:
            indicators["dealer"] = dealer

    return indicators


# ============================================================
# 技术指标
# ============================================================

def _compute_technical(klines: list[dict]) -> dict:
    """计算技术分析指标。"""
    closes = _extract_series(klines, "收盘")
    highs = _extract_series(klines, "最高")
    lows = _extract_series(klines, "最低")
    volumes = _extract_series(klines, "成交量")
    turnover_rates = _extract_series(klines, "换手率")
    opens = _extract_series(klines, "开盘")

    if not closes or len(closes) < 5:
        return {"error": "价格数据不足"}

    result = {}

    # 均线
    result["ma5"] = _ma(closes, 5)
    result["ma10"] = _ma(closes, 10)
    result["ma20"] = _ma(closes, 20)
    result["ma60"] = _ma(closes, 60)

    # 均线排列
    latest = closes[-1]
    ma5, ma10, ma20 = result["ma5"], result["ma10"], result["ma20"]
    if all(v is not None for v in [ma5, ma10, ma20]):
        if ma5 > ma10 > ma20:
            result["ma_arrangement"] = "多头排列"
        elif ma5 < ma10 < ma20:
            result["ma_arrangement"] = "空头排列"
        else:
            result["ma_arrangement"] = "交叉纠缠"

    # 股价相对均线位置
    result["price_vs_ma20"] = _pct_diff(latest, result["ma20"])
    result["price_vs_ma60"] = _pct_diff(latest, result["ma60"])

    # RSI(14)
    result["rsi_14"] = _rsi(closes, 14)

    # MACD
    macd_data = _macd(closes)
    result.update(macd_data)

    # 布林带
    boll = _bollinger(closes, 20)
    result.update(boll)

    # 成交量分析
    if volumes:
        vol5 = _ma(volumes, 5)
        vol20 = _ma(volumes, 20)
        result["vol_ma5"] = vol5
        result["vol_ma20"] = vol20
        result["vol_ratio"] = round(vol5 / vol20, 2) if vol5 and vol20 and vol20 > 0 else None
        result["latest_volume"] = volumes[-1]

    # 换手率
    if turnover_rates:
        result["avg_turnover_5d"] = _ma(turnover_rates, 5)
        result["avg_turnover_20d"] = _ma(turnover_rates, 20)

    # 最大回撤
    result["max_drawdown"] = _max_drawdown(closes)

    # 波动率（年化）
    result["volatility_annual"] = _annualized_volatility(closes)

    # 近期涨跌幅
    if len(closes) >= 5:
        result["change_5d"] = _pct_diff(closes[-1], closes[-5])
    if len(closes) >= 20:
        result["change_20d"] = _pct_diff(closes[-1], closes[-20])

    # 最新价格
    result["latest_price"] = latest
    if highs and lows:
        result["period_high"] = max(highs)
        result["period_low"] = min(lows)

    # --- 新增技术指标 (Phase 1.3) ---

    # VWAP
    if volumes and highs and lows:
        result["vwap"] = _vwap(closes, volumes, highs, lows)

    # ADX
    if highs and lows:
        adx_data = _adx(highs, lows, closes)
        if adx_data:
            result.update({f"adx_{k}": v for k, v in adx_data.items()})

    # MFI
    if highs and lows and volumes:
        result["mfi_14"] = _mfi(highs, lows, closes, volumes, 14)

    # KDJ
    if highs and lows:
        kdj_data = _kdj(highs, lows, closes)
        if kdj_data:
            result.update({f"kdj_{k}": v for k, v in kdj_data.items()})

    # OBV
    if volumes:
        obv_data = _obv(closes, volumes)
        if obv_data:
            result.update(obv_data)

    # PPO
    ppo_data = _ppo(closes)
    if ppo_data:
        result.update(ppo_data)

    # Williams %R
    if highs and lows:
        result["williams_r_14"] = _williams_r(highs, lows, closes, 14)

    # CCI
    if highs and lows:
        result["cci_20"] = _cci(highs, lows, closes, 20)

    # ARBR
    arbr_data = _compute_arbr(klines)
    if arbr_data:
        result.update({f"arbr_{k}": v for k, v in arbr_data.items()})

    return result


# ============================================================
# 财务指标
# ============================================================

def _compute_fundamental(
    stock_info: dict,
    financial: dict,
    quarterly: dict,
    balance_sheet: dict,
) -> dict:
    """提取和计算关键财务比率。"""
    result = {}

    # 从 stock_info 中提取常见指标
    key_map = {
        "市盈率(动态)": "pe_ttm",
        "市净率": "pb",
        "总市值": "market_cap",
        "流通市值": "float_market_cap",
        "每股收益": "eps",
        "每股净资产": "bps",
        "股息率": "dividend_yield",
    }
    if isinstance(stock_info, dict):
        for cn_key, en_key in key_map.items():
            if cn_key in stock_info:
                result[en_key] = _safe_float(stock_info[cn_key])

    # 从 financial indicators 中提取
    indicators = financial.get("indicators", []) if isinstance(financial, dict) else []
    if indicators and isinstance(indicators, list):
        latest = indicators[0]
        if isinstance(latest, dict):
            fin_keys = {
                "净资产收益率(%)": "roe",
                "销售毛利率(%)": "gross_margin",
                "销售净利率(%)": "net_margin",
                "资产负债率(%)": "debt_ratio",
                "流动比率": "current_ratio",
                "速动比率": "quick_ratio",
            }
            for cn_key, en_key in fin_keys.items():
                if cn_key in latest:
                    result[en_key] = _safe_float(latest[cn_key])

            # 计算增速（如果有前期数据）
            if len(indicators) >= 2 and isinstance(indicators[1], dict):
                prev = indicators[1]
                for metric, label in [("净资产收益率(%)", "roe_growth")]:
                    curr_v = _safe_float(latest.get(metric))
                    prev_v = _safe_float(prev.get(metric))
                    if curr_v is not None and prev_v is not None and prev_v != 0:
                        result[label] = round((curr_v - prev_v) / abs(prev_v) * 100, 2)

    # 季报利润增速
    quarters = quarterly.get("quarterly", []) if isinstance(quarterly, dict) else []
    if isinstance(quarters, list) and len(quarters) >= 2:
        q0, q1 = quarters[0], quarters[1]
        if isinstance(q0, dict) and isinstance(q1, dict):
            curr_profit = _safe_float(q0.get("NETPROFIT"))
            prev_profit = _safe_float(q1.get("NETPROFIT"))
            if curr_profit is not None and prev_profit is not None and prev_profit != 0:
                result["profit_growth_qoq"] = round(
                    (curr_profit - prev_profit) / abs(prev_profit) * 100, 2
                )
            curr_rev = _safe_float(q0.get("TOTAL_OPERATE_INCOME"))
            prev_rev = _safe_float(q1.get("TOTAL_OPERATE_INCOME"))
            if curr_rev is not None and prev_rev is not None and prev_rev != 0:
                result["revenue_growth_qoq"] = round(
                    (curr_rev - prev_rev) / abs(prev_rev) * 100, 2
                )

    return result


# ============================================================
# 资金流指标
# ============================================================

def _compute_fund_flow(fund_flow_data: dict) -> dict:
    """计算资金流统计指标。"""
    records = fund_flow_data.get("fund_flow", [])
    if not records or not isinstance(records, list):
        return {}

    result = {}

    # 提取主力净流入数据
    main_flows = []
    for r in records:
        if not isinstance(r, dict):
            continue
        val = _safe_float(r.get("主力净流入-净额"))
        if val is not None:
            main_flows.append(val)

    if main_flows:
        result["main_net_flow_total"] = round(sum(main_flows), 2)
        result["main_net_flow_avg"] = round(sum(main_flows) / len(main_flows), 2)
        result["main_inflow_days"] = sum(1 for x in main_flows if x > 0)
        result["main_outflow_days"] = sum(1 for x in main_flows if x < 0)
        result["main_flow_days_total"] = len(main_flows)

        # 近5日趋势
        recent5 = main_flows[-5:] if len(main_flows) >= 5 else main_flows
        result["main_net_flow_5d"] = round(sum(recent5), 2)
        result["main_inflow_days_5d"] = sum(1 for x in recent5 if x > 0)

    # 超大单
    super_flows = []
    for r in records:
        if not isinstance(r, dict):
            continue
        val = _safe_float(r.get("超大单净流入-净额"))
        if val is not None:
            super_flows.append(val)
    if super_flows:
        result["super_large_net_total"] = round(sum(super_flows), 2)

    return result


# ============================================================
# 融资融券趋势
# ============================================================

def _compute_margin_trend(margin_data: dict) -> dict:
    """计算融资融券趋势指标。"""
    records = margin_data.get("margin", [])
    if not records or not isinstance(records, list):
        return {}

    result = {"days": len(records)}

    # 提取融资余额序列
    rz_balances = []
    for r in records:
        if not isinstance(r, dict):
            continue
        for k, v in r.items():
            if "融资余额" in str(k):
                val = _safe_float(v)
                if val is not None:
                    rz_balances.append(val)
                break

    if rz_balances:
        result["rz_balance_latest"] = rz_balances[-1]
        result["rz_balance_earliest"] = rz_balances[0]
        if rz_balances[0] != 0:
            result["rz_balance_change_pct"] = round(
                (rz_balances[-1] - rz_balances[0]) / rz_balances[0] * 100, 2
            )
        if rz_balances[-1] > rz_balances[0]:
            result["rz_trend"] = "融资余额增加（看多情绪增强）"
        elif rz_balances[-1] < rz_balances[0]:
            result["rz_trend"] = "融资余额减少（看多情绪减弱）"
        else:
            result["rz_trend"] = "融资余额持平"

    return result


# ============================================================
# 辅助函数
# ============================================================

def _extract_series(klines: list[dict], key: str) -> list[float]:
    """从 K 线数据中提取某个字段的序列。"""
    series = []
    for k in klines:
        val = _safe_float(k.get(key))
        if val is not None:
            series.append(val)
    return series


def _safe_float(val) -> float | None:
    """安全转换为 float。"""
    if val is None:
        return None
    try:
        f = float(val)
        return f if not math.isnan(f) and not math.isinf(f) else None
    except (ValueError, TypeError):
        return None


def _ma(series: list[float], period: int) -> float | None:
    """计算移动平均。"""
    if len(series) < period:
        return None
    window = series[-period:]
    return round(sum(window) / period, 4)


def _pct_diff(current: float | None, base: float | None) -> float | None:
    """计算百分比差异。"""
    if current is None or base is None or base == 0:
        return None
    return round((current - base) / base * 100, 2)


def _rsi(closes: list[float], period: int = 14) -> float | None:
    """计算 RSI。"""
    if len(closes) < period + 1:
        return None

    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(0, diff))
        losses.append(max(0, -diff))

    # 使用 EMA 平滑
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


def _macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict:
    """计算 MACD。"""
    if len(closes) < slow + signal:
        return {}

    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)

    if ema_fast is None or ema_slow is None:
        return {}

    # 计算 DIF 序列
    dif_series = []
    for i in range(len(closes)):
        f = _ema_at(closes, fast, i)
        s = _ema_at(closes, slow, i)
        if f is not None and s is not None:
            dif_series.append(f - s)

    if len(dif_series) < signal:
        return {}

    # DEA = DIF 的 EMA(signal)
    dea = _ema(dif_series, signal)
    dif = dif_series[-1]

    if dif is None or dea is None:
        return {}

    macd_val = 2 * (dif - dea)

    return {
        "macd_dif": round(dif, 4),
        "macd_dea": round(dea, 4),
        "macd_histogram": round(macd_val, 4),
        "macd_signal": "金叉（DIF上穿DEA）" if dif > dea else "死叉（DIF下穿DEA）",
    }


def _ema(series: list[float], period: int) -> float | None:
    """计算 EMA 的最新值。"""
    return _ema_at(series, period, len(series) - 1)


def _ema_at(series: list[float], period: int, index: int) -> float | None:
    """计算序列在指定位置的 EMA 值。"""
    if index < period - 1 or len(series) <= index:
        return None
    multiplier = 2 / (period + 1)
    ema_val = sum(series[:period]) / period
    for i in range(period, index + 1):
        ema_val = (series[i] - ema_val) * multiplier + ema_val
    return ema_val


def _bollinger(closes: list[float], period: int = 20, num_std: float = 2) -> dict:
    """计算布林带。"""
    if len(closes) < period:
        return {}
    window = closes[-period:]
    mid = sum(window) / period
    variance = sum((x - mid) ** 2 for x in window) / period
    std = variance ** 0.5
    upper = mid + num_std * std
    lower = mid - num_std * std
    latest = closes[-1]
    # 百分比位置 (0=下轨, 100=上轨)
    boll_pct = (latest - lower) / (upper - lower) * 100 if upper != lower else 50

    return {
        "boll_upper": round(upper, 4),
        "boll_mid": round(mid, 4),
        "boll_lower": round(lower, 4),
        "boll_pct_position": round(boll_pct, 1),
    }


def _max_drawdown(closes: list[float]) -> float | None:
    """计算最大回撤（百分比）。"""
    if len(closes) < 2:
        return None
    peak = closes[0]
    max_dd = 0
    for price in closes:
        if price > peak:
            peak = price
        dd = (peak - price) / peak * 100
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 2)


def _annualized_volatility(closes: list[float]) -> float | None:
    """计算年化波动率。"""
    if len(closes) < 5:
        return None
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            returns.append(math.log(closes[i] / closes[i - 1]))
    if not returns:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    daily_vol = variance ** 0.5
    annual_vol = daily_vol * (252 ** 0.5) * 100
    return round(annual_vol, 2)


def _daily_returns(closes: list[float]) -> list[float]:
    """计算日收益率序列（对数收益率）。"""
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            returns.append(math.log(closes[i] / closes[i - 1]))
        else:
            returns.append(0.0)
    return returns


def _std(series: list[float], period: int) -> float | None:
    """计算窗口标准差。"""
    if len(series) < period:
        return None
    window = series[-period:]
    mean = sum(window) / period
    var = sum((x - mean) ** 2 for x in window) / period
    return round(var ** 0.5, 6)


def _rank_pct(series: list[float], period: int) -> float | None:
    """计算当前值在 N 日窗口中的百分位排名 (0-100)。"""
    if len(series) < period:
        return None
    window = series[-period:]
    current = window[-1]
    rank = sum(1 for x in window if x <= current)
    return round(rank / period * 100, 2)


def _correlation(series_a: list[float], series_b: list[float], period: int) -> float | None:
    """计算两个序列在窗口内的皮尔逊相关系数。"""
    if len(series_a) < period or len(series_b) < period:
        return None
    a = series_a[-period:]
    b = series_b[-period:]
    n = period
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n)) / n
    std_a = (sum((x - mean_a) ** 2 for x in a) / n) ** 0.5
    std_b = (sum((x - mean_b) ** 2 for x in b) / n) ** 0.5
    if std_a == 0 or std_b == 0:
        return None
    return round(cov / (std_a * std_b), 4)


# ============================================================
# Phase 1.1: K-Bar 形态特征 (Alpha158)
# ============================================================

def _compute_kbar_features(klines: list[dict]) -> dict:
    """计算 K-Bar 形态特征 (Alpha158 风格)。

    KMID = (close - open) / open
    KLEN = (high - low) / open
    KUP  = (high - max(open, close)) / open
    KLOW = (min(open, close) - low) / open
    KSFT = (2*close - high - low) / open
    """
    if not klines:
        return {}

    last = klines[-1]
    o = _safe_float(last.get("开盘"))
    c = _safe_float(last.get("收盘"))
    h = _safe_float(last.get("最高"))
    lo = _safe_float(last.get("最低"))

    if any(v is None or v == 0 for v in [o, c, h, lo]):
        return {}

    result = {
        "kmid": round((c - o) / o, 6),
        "klen": round((h - lo) / o, 6),
        "kup": round((h - max(o, c)) / o, 6),
        "klow": round((min(o, c) - lo) / o, 6),
        "ksft": round((2 * c - h - lo) / o, 6),
    }

    # K 线形态判断
    body = abs(c - o)
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - lo
    total_len = h - lo

    if total_len > 0:
        body_ratio = body / total_len
        if body_ratio < 0.1:
            result["pattern"] = "十字星"
        elif upper_shadow > 2 * body and lower_shadow < body * 0.3:
            result["pattern"] = "射击之星" if c < o else "倒锤头"
        elif lower_shadow > 2 * body and upper_shadow < body * 0.3:
            result["pattern"] = "锤头" if c > o else "上吊线"
        elif c > o:
            result["pattern"] = "阳线" if body_ratio > 0.6 else "小阳线"
        else:
            result["pattern"] = "阴线" if body_ratio > 0.6 else "小阴线"

    return result


# ============================================================
# Phase 1.2: 滚动窗口因子
# ============================================================

WINDOWS = [5, 10, 20, 30, 60]


def _compute_rolling_features(klines: list[dict]) -> dict:
    """计算滚动窗口因子: ROC, STD, MAX, MIN, RANK, RSV, CORR, CNTP, SUMP, SUMD, VMA, VSTD。"""
    closes = _extract_series(klines, "收盘")
    volumes = _extract_series(klines, "成交量")

    if not closes or len(closes) < 5:
        return {}

    returns = _daily_returns(closes)
    result = {}

    for w in WINDOWS:
        if len(closes) < w:
            continue

        suffix = f"_{w}"
        window_c = closes[-w:]
        window_max = max(window_c)
        window_min = min(window_c)

        # ROC: N 日收益率
        result[f"roc{suffix}"] = round(
            (closes[-1] - closes[-w]) / closes[-w] * 100, 4
        ) if closes[-w] != 0 else None

        # STD: N 日标准差 (收益率)
        if len(returns) >= w:
            window_r = returns[-w:]
            mean_r = sum(window_r) / w
            var_r = sum((x - mean_r) ** 2 for x in window_r) / w
            result[f"std{suffix}"] = round(var_r ** 0.5, 6)

        # MAX: N 日最高价
        result[f"max{suffix}"] = round(window_max, 4)

        # MIN: N 日最低价
        result[f"min{suffix}"] = round(window_min, 4)

        # RANK: 当前价格在 N 日窗口的百分位
        result[f"rank{suffix}"] = _rank_pct(closes, w)

        # RSV: (price - min) / (max - min) * 100
        if window_max != window_min:
            result[f"rsv{suffix}"] = round(
                (closes[-1] - window_min) / (window_max - window_min) * 100, 2
            )
        else:
            result[f"rsv{suffix}"] = 50.0

        # CORR: N 日价量相关性
        if volumes and len(volumes) >= w and len(closes) >= w:
            result[f"corr{suffix}"] = _correlation(closes, volumes, w)

        # CNTP: N 日正收益天数占比
        if len(returns) >= w:
            window_r = returns[-w:]
            pos_count = sum(1 for x in window_r if x > 0)
            result[f"cntp{suffix}"] = round(pos_count / w, 4)

            # SUMP: N 日正收益之和
            pos_sum = sum(x for x in window_r if x > 0)
            result[f"sump{suffix}"] = round(pos_sum, 6)

            # SUMD: N 日正负收益差 (正收益和 - 负收益绝对值和)
            neg_sum = sum(abs(x) for x in window_r if x < 0)
            result[f"sumd{suffix}"] = round(pos_sum - neg_sum, 6)

        # VMA: N 日量均线
        if volumes and len(volumes) >= w:
            result[f"vma{suffix}"] = _ma(volumes, w)

            # VSTD: N 日量标准差
            result[f"vstd{suffix}"] = _std(volumes, w)

    return result


# ============================================================
# Phase 1.3: 新增关键技术指标
# ============================================================

def _vwap(closes: list[float], volumes: list[float],
          highs: list[float], lows: list[float]) -> float | None:
    """计算 VWAP（成交量加权平均价格）。"""
    n = min(len(closes), len(volumes), len(highs), len(lows))
    if n == 0:
        return None
    # 典型价格 = (H + L + C) / 3
    total_pv = 0.0
    total_v = 0.0
    for i in range(n):
        tp = (highs[i] + lows[i] + closes[i]) / 3
        total_pv += tp * volumes[i]
        total_v += volumes[i]
    if total_v == 0:
        return None
    return round(total_pv / total_v, 4)


def _adx(highs: list[float], lows: list[float],
         closes: list[float], period: int = 14) -> dict:
    """计算 ADX（平均趋向指标）。

    Returns:
        {"adx": float, "plus_di": float, "minus_di": float, "trend_strength": str}
    """
    n = len(closes)
    if n < period * 2 + 1 or len(highs) < n or len(lows) < n:
        return {}

    # 计算 +DM, -DM, TR
    plus_dm = []
    minus_dm = []
    tr_list = []

    for i in range(1, n):
        high_diff = highs[i] - highs[i - 1]
        low_diff = lows[i - 1] - lows[i]

        pdm = high_diff if high_diff > low_diff and high_diff > 0 else 0
        mdm = low_diff if low_diff > high_diff and low_diff > 0 else 0
        plus_dm.append(pdm)
        minus_dm.append(mdm)

        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr_list.append(tr)

    if len(tr_list) < period:
        return {}

    # Wilder 平滑
    atr = sum(tr_list[:period]) / period
    plus_dm_smooth = sum(plus_dm[:period]) / period
    minus_dm_smooth = sum(minus_dm[:period]) / period

    plus_di_list = []
    minus_di_list = []
    dx_list = []

    for i in range(period, len(tr_list)):
        atr = (atr * (period - 1) + tr_list[i]) / period
        plus_dm_smooth = (plus_dm_smooth * (period - 1) + plus_dm[i]) / period
        minus_dm_smooth = (minus_dm_smooth * (period - 1) + minus_dm[i]) / period

        plus_di = (plus_dm_smooth / atr * 100) if atr > 0 else 0
        minus_di = (minus_dm_smooth / atr * 100) if atr > 0 else 0
        plus_di_list.append(plus_di)
        minus_di_list.append(minus_di)

        di_sum = plus_di + minus_di
        dx = abs(plus_di - minus_di) / di_sum * 100 if di_sum > 0 else 0
        dx_list.append(dx)

    if len(dx_list) < period:
        return {}

    # ADX = DX 的 Wilder 平滑
    adx_val = sum(dx_list[:period]) / period
    for i in range(period, len(dx_list)):
        adx_val = (adx_val * (period - 1) + dx_list[i]) / period

    latest_plus_di = plus_di_list[-1] if plus_di_list else 0
    latest_minus_di = minus_di_list[-1] if minus_di_list else 0

    # 趋势强度判断
    if adx_val > 50:
        strength = "极强趋势"
    elif adx_val > 25:
        strength = "强趋势"
    elif adx_val > 20:
        strength = "弱趋势"
    else:
        strength = "无趋势/盘整"

    return {
        "adx": round(adx_val, 2),
        "plus_di": round(latest_plus_di, 2),
        "minus_di": round(latest_minus_di, 2),
        "trend_strength": strength,
    }


def _mfi(highs: list[float], lows: list[float],
         closes: list[float], volumes: list[float],
         period: int = 14) -> float | None:
    """计算 MFI（资金流指标）。"""
    n = min(len(highs), len(lows), len(closes), len(volumes))
    if n < period + 1:
        return None

    # 典型价格
    tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(n)]

    pos_flow = 0.0
    neg_flow = 0.0

    for i in range(n - period, n):
        raw_flow = tp[i] * volumes[i]
        if tp[i] > tp[i - 1]:
            pos_flow += raw_flow
        elif tp[i] < tp[i - 1]:
            neg_flow += raw_flow

    if neg_flow == 0:
        return 100.0
    mfr = pos_flow / neg_flow
    return round(100 - 100 / (1 + mfr), 2)


def _kdj(highs: list[float], lows: list[float],
         closes: list[float], n: int = 9,
         m1: int = 3, m2: int = 3) -> dict:
    """计算 KDJ 指标。"""
    length = min(len(highs), len(lows), len(closes))
    if length < n:
        return {}

    k_val = 50.0
    d_val = 50.0

    for i in range(n - 1, length):
        window_h = highs[i - n + 1: i + 1]
        window_l = lows[i - n + 1: i + 1]
        highest = max(window_h)
        lowest = min(window_l)

        if highest == lowest:
            rsv = 50.0
        else:
            rsv = (closes[i] - lowest) / (highest - lowest) * 100

        k_val = (m1 - 1) / m1 * k_val + 1 / m1 * rsv
        d_val = (m2 - 1) / m2 * d_val + 1 / m2 * k_val

    j_val = 3 * k_val - 2 * d_val

    signal = ""
    if k_val > d_val and j_val > k_val:
        signal = "金叉看多"
    elif k_val < d_val and j_val < k_val:
        signal = "死叉看空"
    elif j_val > 100:
        signal = "超买区域"
    elif j_val < 0:
        signal = "超卖区域"
    else:
        signal = "中性"

    return {
        "k": round(k_val, 2),
        "d": round(d_val, 2),
        "j": round(j_val, 2),
        "signal": signal,
    }


def _obv(closes: list[float], volumes: list[float]) -> dict:
    """计算 OBV（能量潮）及趋势判断。"""
    n = min(len(closes), len(volumes))
    if n < 5:
        return {}

    obv_series = [0.0]
    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            obv_series.append(obv_series[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv_series.append(obv_series[-1] - volumes[i])
        else:
            obv_series.append(obv_series[-1])

    latest_obv = obv_series[-1]

    # OBV 趋势判断 (5 日)
    obv_5 = obv_series[-5:]
    obv_trend = "上升" if obv_5[-1] > obv_5[0] else "下降" if obv_5[-1] < obv_5[0] else "持平"

    # 价量背离检测
    price_up = closes[-1] > closes[-5] if len(closes) >= 5 else None
    obv_up = obv_5[-1] > obv_5[0]

    divergence = None
    if price_up is not None:
        if price_up and not obv_up:
            divergence = "顶背离（价涨量缩，警示）"
        elif not price_up and obv_up:
            divergence = "底背离（价跌量增，关注）"

    return {
        "obv": round(latest_obv, 0),
        "obv_trend": obv_trend,
        "obv_divergence": divergence,
    }


def _ppo(closes: list[float], fast: int = 12, slow: int = 26,
         signal: int = 9) -> dict:
    """计算 PPO（价格百分比振荡器）。"""
    if len(closes) < slow + signal:
        return {}

    ema_f = _ema(closes, fast)
    ema_s = _ema(closes, slow)
    if ema_f is None or ema_s is None or ema_s == 0:
        return {}

    ppo_val = (ema_f - ema_s) / ema_s * 100

    # 计算 PPO 序列以得到信号线
    ppo_series = []
    for i in range(slow - 1, len(closes)):
        f = _ema_at(closes, fast, i)
        s = _ema_at(closes, slow, i)
        if f is not None and s is not None and s != 0:
            ppo_series.append((f - s) / s * 100)

    if len(ppo_series) < signal:
        return {}

    ppo_signal = _ema(ppo_series, signal)
    if ppo_signal is None:
        return {}

    ppo_hist = ppo_val - ppo_signal

    return {
        "ppo": round(ppo_val, 4),
        "ppo_signal": round(ppo_signal, 4),
        "ppo_histogram": round(ppo_hist, 4),
    }


def _williams_r(highs: list[float], lows: list[float],
                closes: list[float], period: int = 14) -> float | None:
    """计算 Williams %R 指标。范围 -100 ~ 0。"""
    n = min(len(highs), len(lows), len(closes))
    if n < period:
        return None

    window_h = highs[-period:]
    window_l = lows[-period:]
    highest = max(window_h)
    lowest = min(window_l)

    if highest == lowest:
        return -50.0

    wr = (highest - closes[-1]) / (highest - lowest) * -100
    return round(wr, 2)


def _cci(highs: list[float], lows: list[float],
         closes: list[float], period: int = 20) -> float | None:
    """计算 CCI（顺势指标）。"""
    n = min(len(highs), len(lows), len(closes))
    if n < period:
        return None

    tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(n)]
    tp_window = tp[-period:]
    tp_mean = sum(tp_window) / period

    # 平均绝对偏差
    mad = sum(abs(x - tp_mean) for x in tp_window) / period
    if mad == 0:
        return 0.0

    cci_val = (tp[-1] - tp_mean) / (0.015 * mad)
    return round(cci_val, 2)


def _compute_arbr(klines: list[dict], period: int = 26) -> dict:
    """计算 AR (人气指标) 和 BR (意愿指标)。

    AR = SUM(high - open, N) / SUM(open - low, N) * 100
    BR = SUM(max(0, high - prev_close), N) / SUM(max(0, prev_close - low), N) * 100
    """
    if len(klines) < period + 1:
        return {}

    opens = _extract_series(klines, "开盘")
    closes = _extract_series(klines, "收盘")
    highs = _extract_series(klines, "最高")
    lows = _extract_series(klines, "最低")

    n = min(len(opens), len(closes), len(highs), len(lows))
    if n < period + 1:
        return {}

    # AR
    ar_num = 0.0
    ar_den = 0.0
    for i in range(n - period, n):
        ar_num += highs[i] - opens[i]
        ar_den += opens[i] - lows[i]

    ar = round(ar_num / ar_den * 100, 2) if ar_den != 0 else 100.0

    # BR
    br_num = 0.0
    br_den = 0.0
    for i in range(n - period, n):
        prev_c = closes[i - 1]
        br_num += max(0, highs[i] - prev_c)
        br_den += max(0, prev_c - lows[i])

    br = round(br_num / br_den * 100, 2) if br_den != 0 else 100.0

    # 状态判断
    ar_status = "超买" if ar > 180 else "超卖" if ar < 50 else "正常"
    br_status = "极度超买" if br > 400 else "超买" if br > 300 else "极度超卖" if br < 40 else "超卖" if br < 70 else "正常"

    # 综合解读
    if ar > 180 and br > 300:
        interpretation = "市场过热，人气和意愿均处于高位，注意回调风险"
    elif ar < 50 and br < 70:
        interpretation = "市场低迷，人气和意愿均不足，关注超跌反弹机会"
    elif ar > 180 and br < 100:
        interpretation = "人气旺但追涨意愿不强，可能短期滞涨"
    elif ar < 80 and br > 200:
        interpretation = "人气不足但意愿强烈，可能有主力资金介入"
    else:
        interpretation = "市场情绪正常，ARBR 无明显异常信号"

    return {
        "ar": ar,
        "br": br,
        "ar_status": ar_status,
        "br_status": br_status,
        "interpretation": interpretation,
    }


# ============================================================
# Phase 1.4: A 股特色因子
# ============================================================

def _compute_ashare_factors(klines: list[dict]) -> dict:
    """计算 A 股特色因子: 换手率溢价、短期反转、涨跌停、量价异动。"""
    closes = _extract_series(klines, "收盘")
    volumes = _extract_series(klines, "成交量")
    turnover_rates = _extract_series(klines, "换手率")
    changes = _extract_series(klines, "涨跌幅")

    if not closes or len(closes) < 5:
        return {}

    result = {}

    # --- 换手率因子 ---
    if turnover_rates and len(turnover_rates) >= 60:
        tr_60 = turnover_rates[-60:]
        tr_mean = sum(tr_60) / 60
        tr_var = sum((x - tr_mean) ** 2 for x in tr_60) / 60
        tr_std = tr_var ** 0.5 if tr_var > 0 else 1.0
        latest_tr = turnover_rates[-1]
        z_score = (latest_tr - tr_mean) / tr_std if tr_std > 0 else 0
        result["turnover_premium"] = round(z_score, 4)

        if z_score > 2:
            result["turnover_regime"] = "异常高换手"
        elif z_score > 1:
            result["turnover_regime"] = "高换手"
        elif z_score < -1:
            result["turnover_regime"] = "低换手"
        else:
            result["turnover_regime"] = "正常"
    elif turnover_rates and len(turnover_rates) >= 20:
        tr_20 = turnover_rates[-20:]
        tr_mean = sum(tr_20) / 20
        tr_var = sum((x - tr_mean) ** 2 for x in tr_20) / 20
        tr_std = tr_var ** 0.5 if tr_var > 0 else 1.0
        z_score = (turnover_rates[-1] - tr_mean) / tr_std if tr_std > 0 else 0
        result["turnover_premium"] = round(z_score, 4)
        result["turnover_regime"] = "高换手" if z_score > 1.5 else "低换手" if z_score < -1.5 else "正常"

    # --- 短期反转因子 ---
    if len(closes) >= 5 and closes[-5] != 0:
        result["reversal_5d"] = round(-(closes[-1] - closes[-5]) / closes[-5] * 100, 4)
    if len(closes) >= 20 and closes[-20] != 0:
        result["reversal_20d"] = round(-(closes[-1] - closes[-20]) / closes[-20] * 100, 4)

    # --- 涨跌停因子 ---
    if changes:
        recent = changes[-20:] if len(changes) >= 20 else changes
        # 主板 ±10%，科创板/创业板 ±20%；此处使用 9.5% / 19.5% 作为近似涨跌停判断
        limit_up_count = sum(1 for x in recent if x >= 9.5)
        limit_down_count = sum(1 for x in recent if x <= -9.5)
        result["limit_up_count_20d"] = limit_up_count
        result["limit_down_count_20d"] = limit_down_count

        if changes[-1] is not None:
            result["near_limit_up"] = changes[-1] >= 9.0
            result["near_limit_down"] = changes[-1] <= -9.0

    # --- 量价异动因子 ---
    if volumes and len(volumes) >= 20 and closes and len(closes) >= 5:
        vol_ma20 = _ma(volumes, 20)
        vol_ma5 = _ma(volumes, 5)

        if vol_ma20 and vol_ma20 > 0 and vol_ma5:
            vol_ratio = vol_ma5 / vol_ma20
            price_change = (closes[-1] - closes[-5]) / closes[-5] * 100 if closes[-5] != 0 else 0

            # 放量滞涨: vol_ratio > 2 且涨幅 < 2%
            result["stagnation_signal"] = vol_ratio > 2 and abs(price_change) < 2

            # 量价背离指数 (简化版: vol_change 和 price_change 方向不一致的程度)
            vol_change = (vol_ma5 - vol_ma20) / vol_ma20 * 100
            if (vol_change > 0 and price_change < 0) or (vol_change < 0 and price_change > 0):
                result["volume_price_divergence"] = round(abs(vol_change - price_change), 2)
            else:
                result["volume_price_divergence"] = 0.0

    return result


# ============================================================
# Phase 1.5: 标准风险指标体系
# ============================================================

def _compute_risk_metrics(klines: list[dict]) -> dict:
    """计算风险指标: VaR, CVaR, Sharpe, Sortino, Calmar, 胜率, 盈亏比。"""
    closes = _extract_series(klines, "收盘")
    if not closes or len(closes) < 20:
        return {}

    returns = _daily_returns(closes)
    if len(returns) < 10:
        return {}

    mean_r = sum(returns) / len(returns)
    var_r = sum((x - mean_r) ** 2 for x in returns) / len(returns)
    std_r = var_r ** 0.5

    result = {}

    # --- VaR (参数法, 正态分布假设) ---
    if std_r > 0:
        result["var_95"] = round((mean_r - 1.645 * std_r) * 100, 4)
        result["var_99"] = round((mean_r - 2.326 * std_r) * 100, 4)

        # CVaR: 取所有超过 VaR 损失的均值
        var_95_threshold = mean_r - 1.645 * std_r
        tail_losses = [r for r in returns if r < var_95_threshold]
        if tail_losses:
            result["cvar_95"] = round(sum(tail_losses) / len(tail_losses) * 100, 4)
        else:
            # 如果没有超过 VaR 的损失，用 VaR 本身
            result["cvar_95"] = result["var_95"]

    # --- Sharpe 比率 (无风险利率 3%/年) ---
    rf_daily = 0.03 / 252
    if std_r > 0:
        sharpe = (mean_r - rf_daily) / std_r * (252 ** 0.5)
        result["sharpe_ratio"] = round(sharpe, 4)

    # --- Sortino 比率 (仅下行波动率) ---
    downside = [r for r in returns if r < 0]
    if downside:
        downside_var = sum(r ** 2 for r in downside) / len(returns)
        downside_std = downside_var ** 0.5
        if downside_std > 0:
            sortino = (mean_r - rf_daily) / downside_std * (252 ** 0.5)
            result["sortino_ratio"] = round(sortino, 4)

    # --- Calmar 比率 (年化收益 / 最大回撤) ---
    max_dd = _max_drawdown(closes)
    if max_dd and max_dd > 0:
        ann_return = mean_r * 252 * 100
        calmar = ann_return / max_dd
        result["calmar_ratio"] = round(calmar, 4)

    # --- 胜率 ---
    pos_days = sum(1 for r in returns if r > 0)
    result["win_rate"] = round(pos_days / len(returns) * 100, 2)

    # --- 盈亏比 ---
    gains = [r for r in returns if r > 0]
    losses = [abs(r) for r in returns if r < 0]
    if gains and losses:
        avg_gain = sum(gains) / len(gains)
        avg_loss = sum(losses) / len(losses)
        if avg_loss > 0:
            result["profit_loss_ratio"] = round(avg_gain / avg_loss, 4)

    # --- 最大回撤 (重用) ---
    result["max_drawdown"] = max_dd

    return result


# ============================================================
# Phase 2: 庄家行为识别模块
# ============================================================


def _compute_wyckoff(klines: list[dict], window: int = 60) -> dict:
    """基于 Wyckoff 方法论识别当前市场阶段。

    Returns:
        {
            "phase": "accumulation|markup|distribution|markdown",
            "sub_phase": "A|B|C|D|E",
            "confidence": 0.0-1.0,
            "signals": [...],
            "support_level": float,
            "resistance_level": float,
        }
    """
    closes = _extract_series(klines, "收盘")
    highs = _extract_series(klines, "最高")
    lows = _extract_series(klines, "最低")
    volumes = _extract_series(klines, "成交量")

    n = min(len(closes), len(highs), len(lows), len(volumes))
    if n < 20:
        return {}

    # 使用最近 window 日数据（不足则用全部）
    w = min(window, n)
    c = closes[-w:]
    h = highs[-w:]
    lo = lows[-w:]
    v = volumes[-w:]

    # --- 1. 支撑/阻力识别 ---
    # 使用 20 日滚动 high/low 的聚类确定
    pivot_window = min(20, w // 3)
    resistance_candidates: list[float] = []
    support_candidates: list[float] = []

    for i in range(pivot_window, w - pivot_window):
        # 局部高点
        if h[i] == max(h[i - pivot_window: i + pivot_window + 1]):
            resistance_candidates.append(h[i])
        # 局部低点
        if lo[i] == min(lo[i - pivot_window: i + pivot_window + 1]):
            support_candidates.append(lo[i])

    # 回退: 如果没有找到 pivot，使用窗口内的极值
    if not resistance_candidates:
        resistance_candidates = [max(h)]
    if not support_candidates:
        support_candidates = [min(lo)]

    # 聚类: 取中位数附近的均值作为关键水平
    resistance_candidates.sort()
    support_candidates.sort()

    resistance = sum(resistance_candidates) / len(resistance_candidates)
    support = sum(support_candidates) / len(support_candidates)

    # --- 2. OBV 趋势 ---
    obv_series = [0.0]
    for i in range(1, w):
        if c[i] > c[i - 1]:
            obv_series.append(obv_series[-1] + v[i])
        elif c[i] < c[i - 1]:
            obv_series.append(obv_series[-1] - v[i])
        else:
            obv_series.append(obv_series[-1])

    obv_slope = _linear_slope(obv_series[-min(20, w):])

    # --- 3. 均线排列 ---
    ma5 = _ma(c, 5) if len(c) >= 5 else None
    ma10 = _ma(c, 10) if len(c) >= 10 else None
    ma20 = _ma(c, 20) if len(c) >= 20 else None
    bullish_ma = ma5 is not None and ma10 is not None and ma20 is not None and ma5 > ma10 > ma20
    bearish_ma = ma5 is not None and ma10 is not None and ma20 is not None and ma5 < ma10 < ma20

    # --- 4. 成交量趋势 ---
    vol_slope = _linear_slope(v[-min(20, w):])

    # --- 5. 价格位置 ---
    latest = c[-1]
    price_range = resistance - support if resistance > support else 1.0
    price_position = (latest - support) / price_range  # 0=支撑, 1=阻力

    # --- 6. 价格趋势 ---
    price_slope = _linear_slope(c[-min(20, w):])

    # --- 7. 横盘检测 ---
    recent_range = max(h[-20:]) - min(lo[-20:]) if w >= 20 else max(h) - min(lo)
    avg_price = sum(c[-20:]) / min(20, w)
    is_sideways = (recent_range / avg_price) < 0.15 if avg_price > 0 else False

    # --- 8. Spring/UTAD 检测 ---
    signals: list[str] = []

    # Spring: 价格短暂跌破支撑后快速回升
    if w >= 5:
        recent_low = min(lo[-5:])
        if recent_low < support * 0.98 and latest > support:
            signals.append("Spring（假跌破支撑后回升）")

    # UTAD: 价格短暂突破阻力后回落
    if w >= 5:
        recent_high = max(h[-5:])
        if recent_high > resistance * 1.02 and latest < resistance:
            signals.append("UTAD（假突破阻力后回落）")

    # --- 9. 阶段判定 + 打分 ---
    scores = {"accumulation": 0.0, "markup": 0.0, "distribution": 0.0, "markdown": 0.0}

    # Accumulation: 底部横盘 + OBV 上升 + 成交量萎缩
    if is_sideways and price_position < 0.4:
        scores["accumulation"] += 0.3
    if obv_slope > 0:
        scores["accumulation"] += 0.25
    if vol_slope < 0:
        scores["accumulation"] += 0.15
    if any("Spring" in s for s in signals):
        scores["accumulation"] += 0.3

    # Distribution: 高位横盘 + OBV 下降 + 放量滞涨
    if is_sideways and price_position > 0.6:
        scores["distribution"] += 0.3
    if obv_slope < 0:
        scores["distribution"] += 0.25
    if vol_slope > 0 and price_slope <= 0:
        scores["distribution"] += 0.15
    if any("UTAD" in s for s in signals):
        scores["distribution"] += 0.3

    # Markup: 均线多头排列 + 价格突破阻力
    if bullish_ma:
        scores["markup"] += 0.35
    if latest > resistance:
        scores["markup"] += 0.25
    if price_slope > 0:
        scores["markup"] += 0.2
    if obv_slope > 0:
        scores["markup"] += 0.2

    # Markdown: 均线空头排列 + 价格跌破支撑
    if bearish_ma:
        scores["markdown"] += 0.35
    if latest < support:
        scores["markdown"] += 0.25
    if price_slope < 0:
        scores["markdown"] += 0.2
    if obv_slope < 0:
        scores["markdown"] += 0.2

    # 选择最高分阶段
    phase = max(scores, key=lambda k: scores[k])
    confidence = min(scores[phase], 1.0)

    # 子阶段推断
    sub_phase_map = {
        "accumulation": "B" if is_sideways else ("C" if any("Spring" in s for s in signals) else "A"),
        "markup": "D" if price_position > 0.8 else "C",
        "distribution": "B" if is_sideways else ("C" if any("UTAD" in s for s in signals) else "A"),
        "markdown": "D" if price_position < 0.2 else "C",
    }
    sub_phase = sub_phase_map.get(phase, "A")

    # 补充信号描述
    if bullish_ma:
        signals.append("均线多头排列")
    if bearish_ma:
        signals.append("均线空头排列")
    if is_sideways:
        signals.append("横盘震荡")
    if obv_slope > 0 and price_slope < 0:
        signals.append("OBV底背离（吸筹迹象）")
    if obv_slope < 0 and price_slope > 0:
        signals.append("OBV顶背离（出货迹象）")

    return {
        "wyckoff_phase": phase,
        "wyckoff_sub_phase": sub_phase,
        "wyckoff_confidence": round(confidence, 2),
        "wyckoff_signals": signals,
        "support_level": round(support, 4),
        "resistance_level": round(resistance, 4),
    }


def _compute_obv_divergence(closes: list[float], volumes: list[float],
                            window: int = 20) -> dict:
    """检测 OBV 与价格的背离（增强版，使用线性回归）。

    Returns:
        {
            "obv_current": float,
            "obv_trend": "up|down|flat",
            "price_trend": "up|down|flat",
            "divergence_type": "bullish|bearish|none",
            "divergence_strength": 0.0-1.0,
            "interpretation": "...",
        }
    """
    n = min(len(closes), len(volumes))
    if n < 10:
        return {}

    # 计算 OBV 序列
    obv_series = [0.0]
    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            obv_series.append(obv_series[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv_series.append(obv_series[-1] - volumes[i])
        else:
            obv_series.append(obv_series[-1])

    w = min(window, n)
    obv_window = obv_series[-w:]
    price_window = closes[-w:]

    # 线性回归斜率判断趋势
    obv_slope = _linear_slope(obv_window)
    price_slope = _linear_slope(price_window)

    # 归一化斜率以判断方向
    obv_range = max(obv_window) - min(obv_window) if max(obv_window) != min(obv_window) else 1.0
    price_range = max(price_window) - min(price_window) if max(price_window) != min(price_window) else 1.0

    obv_slope_norm = obv_slope * w / obv_range if obv_range > 0 else 0
    price_slope_norm = price_slope * w / price_range if price_range > 0 else 0

    # 趋势判定 (阈值 0.1)
    threshold = 0.1
    if obv_slope_norm > threshold:
        obv_trend = "up"
    elif obv_slope_norm < -threshold:
        obv_trend = "down"
    else:
        obv_trend = "flat"

    if price_slope_norm > threshold:
        price_trend = "up"
    elif price_slope_norm < -threshold:
        price_trend = "down"
    else:
        price_trend = "flat"

    # 背离检测
    divergence_type = "none"
    divergence_strength = 0.0
    interpretation = "OBV与价格趋势一致，无背离"

    if price_trend == "down" and obv_trend == "up":
        divergence_type = "bullish"
        divergence_strength = min(abs(obv_slope_norm) + abs(price_slope_norm), 1.0)
        interpretation = "看涨背离：价格下跌但OBV上升，表明有资金在低位吸筹，可能反转上涨"
    elif price_trend == "up" and obv_trend == "down":
        divergence_type = "bearish"
        divergence_strength = min(abs(obv_slope_norm) + abs(price_slope_norm), 1.0)
        interpretation = "看跌背离：价格上涨但OBV下降，表明上涨缺乏成交量支撑，可能见顶回落"
    elif price_trend == "flat" and obv_trend == "up":
        divergence_type = "bullish"
        divergence_strength = min(abs(obv_slope_norm) * 0.6, 1.0)
        interpretation = "潜在看涨：价格横盘但OBV上升，主力可能在暗中吸筹"
    elif price_trend == "flat" and obv_trend == "down":
        divergence_type = "bearish"
        divergence_strength = min(abs(obv_slope_norm) * 0.6, 1.0)
        interpretation = "潜在看跌：价格横盘但OBV下降，资金可能在悄然撤离"

    return {
        "obv_current": round(obv_series[-1], 0),
        "obv_trend": obv_trend,
        "price_trend": price_trend,
        "divergence_type": divergence_type,
        "divergence_strength": round(divergence_strength, 2),
        "interpretation": interpretation,
    }


def _compute_chip_distribution(klines: list[dict], window: int = 60) -> dict:
    """估算筹码分布和集中度。

    基于成交量分布的简化估算，非精确 Level-2 数据。
    使用加权衰减（近期权重更大）构建价格-成交量分布直方图。

    Returns:
        {
            "concentration": float,
            "peak_type": "single|double|dispersed",
            "cost_center": float,
            "profit_ratio": float,
            "trapped_ratio": float,
            "support_from_chips": float,
            "pressure_from_chips": float,
        }
    """
    closes = _extract_series(klines, "收盘")
    volumes = _extract_series(klines, "成交量")

    n = min(len(closes), len(volumes))
    if n < 10:
        return {}

    w = min(window, n)
    c = closes[-w:]
    v = volumes[-w:]

    # --- 1. 构建价格-成交量分布直方图 ---
    price_min = min(c)
    price_max = max(c)
    if price_max == price_min:
        return {}

    num_bins = 30
    bin_width = (price_max - price_min) / num_bins
    bins = [0.0] * num_bins

    for i in range(w):
        # 加权衰减: 近期权重更大 (指数衰减, 半衰期=window/3)
        half_life = max(w / 3, 5)
        weight = 2.0 ** ((i - w + 1) / half_life)
        # 将成交量分配到对应的价格 bin
        bin_idx = int((c[i] - price_min) / bin_width)
        bin_idx = min(bin_idx, num_bins - 1)
        bins[bin_idx] += v[i] * weight

    total_weighted_vol = sum(bins)
    if total_weighted_vol == 0:
        return {}

    # --- 2. 成本中心 (加权平均价) ---
    cost_center = 0.0
    for i in range(num_bins):
        bin_center = price_min + (i + 0.5) * bin_width
        cost_center += bin_center * bins[i]
    cost_center /= total_weighted_vol

    # --- 3. 筹码集中度 (使用标准差 / 均价) ---
    variance = 0.0
    for i in range(num_bins):
        bin_center = price_min + (i + 0.5) * bin_width
        variance += bins[i] * (bin_center - cost_center) ** 2
    variance /= total_weighted_vol
    chip_std = variance ** 0.5
    concentration = 1.0 - min(chip_std / cost_center, 1.0) if cost_center > 0 else 0.0

    # --- 4. 峰值检测 (单峰/双峰/分散) ---
    # 平滑 bins 用 3 点移动平均
    smoothed = list(bins)
    for i in range(1, num_bins - 1):
        smoothed[i] = (bins[i - 1] + bins[i] + bins[i + 1]) / 3

    # 找局部最大值
    peaks: list[int] = []
    peak_threshold = total_weighted_vol * 0.05  # 至少占总量 5%
    for i in range(1, num_bins - 1):
        if smoothed[i] > smoothed[i - 1] and smoothed[i] > smoothed[i + 1]:
            if smoothed[i] > peak_threshold:
                peaks.append(i)

    if len(peaks) == 0:
        # 没有明显峰值，取最大 bin
        peaks = [smoothed.index(max(smoothed))]

    if len(peaks) >= 2:
        peak_type = "double"
    elif len(peaks) == 1 and concentration > 0.7:
        peak_type = "single"
    else:
        peak_type = "dispersed"

    # --- 5. 获利盘/套牢盘比例 ---
    latest_price = c[-1]
    profit_vol = 0.0
    trapped_vol = 0.0
    for i in range(num_bins):
        bin_center = price_min + (i + 0.5) * bin_width
        if bin_center <= latest_price:
            profit_vol += bins[i]
        else:
            trapped_vol += bins[i]

    profit_ratio = profit_vol / total_weighted_vol
    trapped_ratio = trapped_vol / total_weighted_vol

    # --- 6. 筹码支撑位/压力位 ---
    # 支撑位: 当前价格下方最大成交量集中区的中心
    # 压力位: 当前价格上方最大成交量集中区的中心
    latest_bin = int((latest_price - price_min) / bin_width)
    latest_bin = min(latest_bin, num_bins - 1)

    support_from_chips = price_min
    pressure_from_chips = price_max
    max_support_vol = 0.0
    max_pressure_vol = 0.0

    for i in range(num_bins):
        bin_center = price_min + (i + 0.5) * bin_width
        if i < latest_bin and smoothed[i] > max_support_vol:
            max_support_vol = smoothed[i]
            support_from_chips = bin_center
        elif i > latest_bin and smoothed[i] > max_pressure_vol:
            max_pressure_vol = smoothed[i]
            pressure_from_chips = bin_center

    return {
        "concentration": round(concentration, 4),
        "peak_type": peak_type,
        "cost_center": round(cost_center, 4),
        "profit_ratio": round(profit_ratio, 4),
        "trapped_ratio": round(trapped_ratio, 4),
        "support_from_chips": round(support_from_chips, 4),
        "pressure_from_chips": round(pressure_from_chips, 4),
    }


def _compute_distribution_signals(klines: list[dict]) -> dict:
    """检测 7 种经典出货模式。

    基于《散户快跑》中的经典出货模式识别。

    Returns:
        {
            "signals": [{
                "type": "sawtooth|dump|slow_press|oscillate|pull_sell|staircase|wash_trade",
                "confidence": 0.0-1.0,
                "description": "...",
            }],
            "overall_risk": "high|medium|low",
            "risk_score": 0-100,
        }
    """
    closes = _extract_series(klines, "收盘")
    opens = _extract_series(klines, "开盘")
    highs = _extract_series(klines, "最高")
    lows = _extract_series(klines, "最低")
    volumes = _extract_series(klines, "成交量")
    changes = _extract_series(klines, "涨跌幅")

    n = min(len(closes), len(opens), len(highs), len(lows), len(volumes))
    if n < 10:
        return {}

    signals: list[dict] = []

    # 最近 20 日数据用于模式检测
    w = min(20, n)
    c = closes[-w:]
    o = opens[-w:]
    h = highs[-w:]
    lo = lows[-w:]
    v = volumes[-w:]
    chg = changes[-w:] if len(changes) >= w else changes

    avg_price = sum(c) / w
    avg_vol = sum(v) / w if sum(v) > 0 else 1.0

    # 价格位置: 是否在高位 (近 60 日 70% 以上)
    if n >= 60:
        long_high = max(highs[-60:])
        long_low = min(lows[-60:])
        long_range = long_high - long_low if long_high > long_low else 1.0
        price_pct = (c[-1] - long_low) / long_range
        at_high = price_pct > 0.7
    else:
        at_high = False
        price_pct = 0.5

    # ATR (近 w 日)
    atr_list = []
    for i in range(1, w):
        tr = max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1]))
        atr_list.append(tr)
    atr = sum(atr_list) / len(atr_list) if atr_list else 0
    avg_atr = atr / avg_price * 100 if avg_price > 0 else 0  # ATR 百分比

    # --- 1. 锯齿形出货 ---
    # 高位 + 窄幅震荡 (ATR < avg*0.5) + 成交量不规则
    if at_high and avg_atr < 2.0:
        vol_std = (sum((x - avg_vol) ** 2 for x in v) / w) ** 0.5
        vol_cv = vol_std / avg_vol if avg_vol > 0 else 0
        if vol_cv > 0.5:  # 成交量变异系数大 = 不规则
            conf = min(0.3 + (1.0 - avg_atr / 2.0) * 0.3 + vol_cv * 0.2, 1.0)
            signals.append({
                "type": "sawtooth",
                "confidence": round(conf, 2),
                "description": "锯齿形出货：高位窄幅震荡，成交量不规则，主力以小幅锯齿方式出货",
            })

    # --- 2. 打低出货 ---
    # 日内冲高 > 3% 然后回落 > 5%
    if w >= 3:
        for i in range(-3, 0):
            if len(o) + i < 0:
                continue
            intraday_high = (h[i] - o[i]) / o[i] * 100 if o[i] > 0 else 0
            intraday_drop = (h[i] - c[i]) / h[i] * 100 if h[i] > 0 else 0
            if intraday_high > 3 and intraday_drop > 5:
                signals.append({
                    "type": "dump",
                    "confidence": round(min(0.5 + intraday_drop / 20, 1.0), 2),
                    "description": f"打低出货：日内冲高{intraday_high:.1f}%后回落{intraday_drop:.1f}%，疑似拉高出货",
                })
                break

    # --- 3. 缓压出货 ---
    # 连续 5+ 日小阴线 (跌幅 < 1%) + OBV 下行
    if w >= 5:
        consecutive_small_down = 0
        for i in range(-1, -w, -1):
            if len(chg) + i >= 0 and -1.0 <= chg[i] < 0:
                consecutive_small_down += 1
            else:
                break
        if consecutive_small_down >= 5:
            # 检查 OBV 是否下行
            obv_check = [0.0]
            for i in range(1, w):
                if c[i] > c[i - 1]:
                    obv_check.append(obv_check[-1] + v[i])
                elif c[i] < c[i - 1]:
                    obv_check.append(obv_check[-1] - v[i])
                else:
                    obv_check.append(obv_check[-1])
            if obv_check[-1] < obv_check[0]:
                conf = min(0.4 + consecutive_small_down * 0.08, 1.0)
                signals.append({
                    "type": "slow_press",
                    "confidence": round(conf, 2),
                    "description": f"缓压出货：连续{consecutive_small_down}日小阴线，OBV持续下行，阴跌出货",
                })

    # --- 4. 震荡式出货 ---
    # 高位 + 宽幅震荡 + 量能萎缩 + 高点递降
    if at_high and avg_atr > 2.0:
        # 高点递降检测
        if w >= 10:
            first_half_high = max(h[:w // 2])
            second_half_high = max(h[w // 2:])
            highs_declining = second_half_high < first_half_high

            # 量能萎缩
            first_half_vol = sum(v[:w // 2]) / (w // 2)
            second_half_vol = sum(v[w // 2:]) / (w - w // 2)
            vol_shrinking = second_half_vol < first_half_vol * 0.8

            if highs_declining and vol_shrinking:
                conf = min(0.4 + (first_half_high - second_half_high) / avg_price * 5, 1.0)
                signals.append({
                    "type": "oscillate",
                    "confidence": round(conf, 2),
                    "description": "震荡式出货：高位宽幅震荡，高点递降，量能萎缩，主力借震荡出货",
                })

    # --- 5. 边拉边出 ---
    # vol_ratio > 2 + price_change < 2% (放量滞涨)
    if w >= 5:
        vol_ma5 = sum(v[-5:]) / 5
        vol_ma20 = sum(v) / w
        if vol_ma20 > 0:
            vol_ratio = vol_ma5 / vol_ma20
            price_change_5d = (c[-1] - c[-5]) / c[-5] * 100 if c[-5] > 0 else 0
            if vol_ratio > 2 and abs(price_change_5d) < 2:
                conf = min(0.3 + (vol_ratio - 2) * 0.2 + (2 - abs(price_change_5d)) * 0.1, 1.0)
                signals.append({
                    "type": "pull_sell",
                    "confidence": round(conf, 2),
                    "description": f"边拉边出：量比{vol_ratio:.1f}倍放量但涨幅仅{price_change_5d:.1f}%，放量滞涨",
                })

    # --- 6. 台阶式出货 ---
    # 阶梯下降 + 每个台阶缩量 + 支撑位下移
    if w >= 15:
        # 分 3 段检测阶梯
        seg_len = w // 3
        segs = [c[i * seg_len: (i + 1) * seg_len] for i in range(3)]
        seg_avgs = [sum(s) / len(s) for s in segs if s]
        seg_vols = [
            sum(v[i * seg_len: (i + 1) * seg_len]) / seg_len
            for i in range(3)
        ]

        if len(seg_avgs) == 3:
            price_descending = seg_avgs[0] > seg_avgs[1] > seg_avgs[2]
            vol_descending = seg_vols[0] > seg_vols[1] > seg_vols[2]

            if price_descending and vol_descending:
                drop_pct = (seg_avgs[0] - seg_avgs[2]) / seg_avgs[0] * 100 if seg_avgs[0] > 0 else 0
                conf = min(0.4 + drop_pct / 30, 1.0)
                signals.append({
                    "type": "staircase",
                    "confidence": round(conf, 2),
                    "description": f"台阶式出货：价格呈阶梯下降（累计跌{drop_pct:.1f}%），每个台阶缩量",
                })

    # --- 7. 对敲 (wash_trade) ---
    # 量升价平 + 连续 3-5 天
    if w >= 5:
        wash_count = 0
        for i in range(-5, 0):
            if len(v) + i >= 1 and len(c) + i >= 0:
                vol_up = v[i] > v[i - 1] * 1.2 if v[i - 1] > 0 else False
                price_flat = abs(c[i] - c[i - 1]) / c[i - 1] * 100 < 1.0 if c[i - 1] > 0 else False
                if vol_up and price_flat:
                    wash_count += 1

        if wash_count >= 3:
            conf = min(0.3 + wash_count * 0.15, 1.0)
            signals.append({
                "type": "wash_trade",
                "confidence": round(conf, 2),
                "description": f"对敲嫌疑：连续{wash_count}天量升价平，可能存在对敲制造虚假成交量",
            })

    # --- 综合风险评分 ---
    if not signals:
        risk_score = 0
    else:
        risk_score = int(min(sum(s["confidence"] for s in signals) / len(signals) * 80 + len(signals) * 10, 100))

    if risk_score >= 60:
        overall_risk = "high"
    elif risk_score >= 30:
        overall_risk = "medium"
    else:
        overall_risk = "low"

    return {
        "signals": signals,
        "overall_risk": overall_risk,
        "risk_score": risk_score,
    }


def _linear_slope(series: list[float]) -> float:
    """计算序列的线性回归斜率 (最小二乘法)。"""
    n = len(series)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(series) / n
    numerator = sum((i - x_mean) * (series[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return 0.0
    return numerator / denominator
