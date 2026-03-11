"""AI Analyst Team: multi-perspective analysis with pre-aggregation.

Instead of scoring individual stocks, the analyst team:
1. Pre-aggregates 1000+ candidates into compact statistics (pure Python, ~10ms)
2. Sends ~1400 tokens per analyst (3 analysts run in parallel)
3. A synthesis analyst reads all 3 reports and produces top_n picks

Token budget: ~23K tokens/job (4 LLM calls).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from functools import partial
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="analyst")

_BEIJING_TZ = timezone(timedelta(hours=8))


def _now_beijing_str() -> str:
    """Return current Beijing time as 'YYYY年MM月DD日 HH:MM'."""
    now = datetime.now(_BEIJING_TZ)
    return now.strftime("%Y年%m月%d日 %H:%M")


# ── Indicator key normalization (Chinese pywencai → canonical English) ────────

# Maps Chinese label variants from pywencai display_fields to canonical keys.
# The aggregation functions use canonical keys; this map bridges the gap.
_KEY_ALIASES: dict[str, list[str]] = {
    "close":               ["最新价", "收盘价", "close"],
    "change_pct":          ["涨跌幅", "涨跌幅%", "最新涨跌幅", "change_pct"],
    "pe":                  ["PE", "pe", "市盈率", "市盈率-动态"],
    "pb":                  ["PB", "pb", "市净率"],
    "market_cap":          ["总市值", "总市值(亿)", "市值(亿)", "market_cap"],
    "turnover_rate":       ["换手率", "换手率%", "turnover_rate"],
    "vol_ratio":           ["量比", "vol_ratio"],
    "main_net_flow_total": ["主力净流入", "主力净流入额", "main_net_flow_total"],
    "volume":              ["成交额", "成交量", "volume"],
    "roe":                 ["ROE", "ROE%", "roe"],
    "rsi":                 ["RSI", "rsi"],
    "profit_growth":       ["净利增长%", "净利润增长率", "归属于母公司所有者的净利润同比增长率"],
    "revenue_growth":      ["营收增长%", "营业收入增长率"],
    "dividend_yield":      ["股息率", "股息率%"],
    "north_net_buy":       ["北向净买入(亿)", "净买入额"],
}

# Reverse map: Chinese label → canonical key (built once at import time)
_LABEL_TO_KEY: dict[str, str] = {}
for _canon, _aliases in _KEY_ALIASES.items():
    for _alias in _aliases:
        _LABEL_TO_KEY[_alias] = _canon


def _get_indicator(inds: dict[str, Any], canonical_key: str) -> Any:
    """Get indicator value by canonical key, trying all known aliases.

    Also handles pywencai keys with date suffixes like '净利润同比增长率[20250930]'.
    """
    # Direct hit
    v = inds.get(canonical_key)
    if v is not None:
        return v
    # Try aliases (exact match)
    for alias in _KEY_ALIASES.get(canonical_key, []):
        v = inds.get(alias)
        if v is not None:
            return v
    # Try prefix/substring match for aliases (handles date-suffixed pywencai keys)
    for alias in _KEY_ALIASES.get(canonical_key, []):
        if len(alias) >= 4:  # only for non-trivial aliases
            for k, val in inds.items():
                if k.startswith(alias) or alias in k:
                    return val
    return None


def _normalize_indicators(inds: dict[str, Any]) -> dict[str, Any]:
    """Normalize indicator dict: add canonical keys alongside originals."""
    result = dict(inds)  # keep originals
    for key, value in inds.items():
        canon = _LABEL_TO_KEY.get(key)
        if canon and canon not in result:
            result[canon] = value
    return result


# ── Pre-aggregation functions (pure Python, no LLM) ──────────────────────────


def _safe_float(v: Any) -> float | None:
    """Convert value to float, return None on failure."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _quantiles(values: list[float]) -> dict[str, float]:
    """Compute quartile stats for a list of floats."""
    if not values:
        return {}
    arr = np.array(values)
    return {
        "min": round(float(np.min(arr)), 2),
        "q25": round(float(np.percentile(arr, 25)), 2),
        "median": round(float(np.median(arr)), 2),
        "q75": round(float(np.percentile(arr, 75)), 2),
        "max": round(float(np.max(arr)), 2),
        "mean": round(float(np.mean(arr)), 2),
    }


def _top_bottom(
    candidates: list[dict], key: str, n: int = 10
) -> tuple[list[dict], list[dict]]:
    """Get top-n and bottom-n candidates by a numeric indicator (uses alias lookup)."""
    valid = []
    for c in candidates:
        inds = c.get("indicators", {})
        v = _safe_float(_get_indicator(inds, key))
        if v is not None:
            valid.append((v, c))
    valid.sort(key=lambda x: x[0], reverse=True)
    top = [
        {"symbol": c["symbol"], "name": c.get("name", ""), key: round(v, 2)}
        for v, c in valid[:n]
    ]
    bottom = [
        {"symbol": c["symbol"], "name": c.get("name", ""), key: round(v, 2)}
        for v, c in valid[-n:]
    ]
    return top, bottom


def _aggregate_capital_flow(candidates: list[dict]) -> dict[str, Any]:
    """Aggregate capital flow statistics across all candidates."""
    flows = []
    turnovers = []
    vol_ratios = []
    change_pcts = []
    volumes = []

    for c in candidates:
        inds = c.get("indicators", {})
        v = _safe_float(_get_indicator(inds, "main_net_flow_total"))
        if v is not None:
            flows.append(v)
        v = _safe_float(_get_indicator(inds, "turnover_rate"))
        if v is not None:
            turnovers.append(v)
        v = _safe_float(_get_indicator(inds, "vol_ratio"))
        if v is not None:
            vol_ratios.append(v)
        v = _safe_float(_get_indicator(inds, "change_pct"))
        if v is not None:
            change_pcts.append(v)
        v = _safe_float(_get_indicator(inds, "volume"))
        if v is not None:
            volumes.append(v)

    top_flow, bottom_flow = _top_bottom(candidates, "main_net_flow_total", 10)
    top_turnover, _ = _top_bottom(candidates, "turnover_rate", 10)
    top_vol, _ = _top_bottom(candidates, "vol_ratio", 10)

    net_inflow_count = sum(1 for f in flows if f > 0)
    net_outflow_count = sum(1 for f in flows if f < 0)

    result: dict[str, Any] = {
        "total_candidates": len(candidates),
        "change_pct": _quantiles(change_pcts),
    }
    # Only include sections that have data
    if flows:
        result["main_net_flow"] = _quantiles(flows)
        result["net_inflow_count"] = net_inflow_count
        result["net_outflow_count"] = net_outflow_count
        result["top_inflow"] = top_flow
        result["top_outflow"] = bottom_flow
    if turnovers:
        result["turnover_rate"] = _quantiles(turnovers)
        result["top_turnover"] = top_turnover
    if vol_ratios:
        result["vol_ratio"] = _quantiles(vol_ratios)
        result["top_vol_ratio"] = top_vol
    if volumes:
        result["volume"] = _quantiles(volumes)

    # Add a sample of top candidates by change_pct for the LLM
    top_change, bottom_change = _top_bottom(candidates, "change_pct", 10)
    if top_change:
        result["top_gainers"] = top_change
    if bottom_change:
        result["top_losers"] = bottom_change

    return result


def _aggregate_sector_industry(candidates: list[dict]) -> dict[str, Any]:
    """Aggregate by stock code prefix (market board) and sector statistics."""

    boards: dict[str, list[dict]] = defaultdict(list)
    for c in candidates:
        sym = c.get("symbol", "")
        board = "其他"
        if sym.startswith("688"):
            board = "科创板"
        elif sym.startswith("60"):
            board = "沪主板"
        elif sym.startswith("00"):
            board = "深主板"
        elif sym.startswith("30"):
            board = "创业板"
        boards[board].append(c)

    board_stats = {}
    for board_name, stocks in boards.items():
        pcts = [
            _safe_float(_get_indicator(s.get("indicators", {}), "change_pct"))
            for s in stocks
        ]
        pcts = [p for p in pcts if p is not None]
        pes = [
            _safe_float(_get_indicator(s.get("indicators", {}), "pe"))
            for s in stocks
        ]
        pes = [p for p in pes if p is not None and 0 < p < 1000]
        caps = [
            _safe_float(_get_indicator(s.get("indicators", {}), "market_cap"))
            for s in stocks
        ]
        caps = [mv for mv in caps if mv is not None]

        board_stats[board_name] = {
            "count": len(stocks),
            "avg_change_pct": round(sum(pcts) / len(pcts), 2) if pcts else None,
            "avg_pe": round(sum(pes) / len(pes), 1) if pes else None,
            "avg_market_cap_yi": round(sum(caps) / len(caps), 1) if caps else None,
        }

    # Top/bottom by change_pct
    top_change, bottom_change = _top_bottom(candidates, "change_pct", 10)

    # Include a compact stock list with raw indicator names (first 30 stocks)
    compact_stocks = []
    for c in candidates[:30]:
        inds = c.get("indicators", {})
        compact = {"symbol": c["symbol"], "name": c.get("name", "")}
        for k, v in list(inds.items())[:5]:
            fv = _safe_float(v)
            compact[k] = round(fv, 2) if fv is not None else v
        compact_stocks.append(compact)

    return {
        "total_candidates": len(candidates),
        "board_distribution": board_stats,
        "top_gainers": top_change,
        "top_losers": bottom_change,
        "sample_stocks": compact_stocks,
    }


def _aggregate_fundamentals(candidates: list[dict]) -> dict[str, Any]:
    """Aggregate PE/PB distributions, market cap stats, and highlight extremes."""
    pes = []
    pbs = []
    caps = []
    profit_growths = []

    for c in candidates:
        inds = c.get("indicators", {})
        pe = _safe_float(_get_indicator(inds, "pe"))
        if pe is not None and 0 < pe < 2000:
            pes.append(pe)
        pb = _safe_float(_get_indicator(inds, "pb"))
        if pb is not None and 0 < pb < 500:
            pbs.append(pb)
        cap = _safe_float(_get_indicator(inds, "market_cap"))
        if cap is not None:
            caps.append(cap)
        pg = _safe_float(_get_indicator(inds, "profit_growth"))
        if pg is not None:
            profit_growths.append(pg)

    # PE range buckets
    pe_buckets = {"<10": 0, "10-20": 0, "20-30": 0, "30-50": 0, "50-100": 0, ">100": 0}
    for pe in pes:
        if pe < 10:
            pe_buckets["<10"] += 1
        elif pe < 20:
            pe_buckets["10-20"] += 1
        elif pe < 30:
            pe_buckets["20-30"] += 1
        elif pe < 50:
            pe_buckets["30-50"] += 1
        elif pe < 100:
            pe_buckets["50-100"] += 1
        else:
            pe_buckets[">100"] += 1

    # Market cap buckets (in 亿)
    cap_buckets = {"<50亿": 0, "50-200亿": 0, "200-1000亿": 0, ">1000亿": 0}
    for cap in caps:
        cap_yi = cap if cap < 10000 else cap / 1e8  # handle both raw and 亿 units
        if cap_yi < 50:
            cap_buckets["<50亿"] += 1
        elif cap_yi < 200:
            cap_buckets["50-200亿"] += 1
        elif cap_yi < 1000:
            cap_buckets["200-1000亿"] += 1
        else:
            cap_buckets[">1000亿"] += 1

    top_pe, bottom_pe = _top_bottom(candidates, "pe", 10)

    result: dict[str, Any] = {
        "total_candidates": len(candidates),
    }
    if pes:
        result["pe"] = _quantiles(pes)
        result["pe_buckets"] = pe_buckets
        result["lowest_pe"] = bottom_pe
        result["highest_pe"] = top_pe
    if pbs:
        result["pb"] = _quantiles(pbs)
    if caps:
        result["market_cap_yi"] = _quantiles(
            [c if c < 10000 else c / 1e8 for c in caps]
        )
        result["cap_buckets"] = cap_buckets
    if profit_growths:
        result["profit_growth"] = _quantiles(profit_growths)

    # Compact stock list for LLM reference (top 20 by profit growth or PE)
    compact_stocks = []
    for c in candidates[:20]:
        inds = c.get("indicators", {})
        compact = {"symbol": c["symbol"], "name": c.get("name", "")}
        for k, v in list(inds.items())[:6]:
            fv = _safe_float(v)
            compact[k] = round(fv, 2) if fv is not None else v
        compact_stocks.append(compact)
    if compact_stocks:
        result["sample_stocks"] = compact_stocks

    return result


# ── Analyst definitions ──────────────────────────────────────────────────────

ANALYSTS = [
    {
        "id": "capital_flow",
        "title": "资金流向分析",
        "icon": "💰",
        "aggregate_fn": _aggregate_capital_flow,
        "system_prompt": (
            "你是一位专业的 A 股资金流向分析师，擅长通过主力资金净流入、换手率、"
            "量比等指标判断市场情绪和资金动向。\n"
            "你的分析风格严谨、数据驱动，善于发现异常资金信号。\n"
            "当前时间：{now}。请在报告中使用正确的日期。"
        ),
        "user_prompt_template": (
            "报告日期：{now}\n"
            "数据日期：{data_date}（选股池数据对应的交易日）\n\n"
            "以下是本次选股池（{total}只候选股）的资金流向统计摘要：\n\n"
            "{stats}\n\n"
            "请撰写一份约2000字的资金流向分析报告，使用 Markdown 格式，包含以下四个部分：\n"
            "## 一、资金面总体趋势\n"
            "## 二、重点发现\n"
            "## 三、风险提示\n"
            "## 四、值得关注的标的（5-8只）\n\n"
            "在第四部分，请从资金面角度列出5-8只最值得关注的股票，说明关注理由。"
        ),
    },
    {
        "id": "sector_industry",
        "title": "行业板块分析",
        "icon": "🏭",
        "aggregate_fn": _aggregate_sector_industry,
        "system_prompt": (
            "你是一位专业的 A 股行业研究分析师，擅长分析不同板块（沪主板、深主板、"
            "创业板、科创板）的轮动规律和行业景气度。\n"
            "你善于从板块分布和涨跌格局中发现结构性机会。\n"
            "当前时间：{now}。请在报告中使用正确的日期。"
        ),
        "user_prompt_template": (
            "报告日期：{now}\n"
            "数据日期：{data_date}（选股池数据对应的交易日）\n\n"
            "以下是本次选股池（{total}只候选股）的板块分布与行业统计摘要：\n\n"
            "{stats}\n\n"
            "请撰写一份约2000字的行业板块分析报告，使用 Markdown 格式，包含以下四个部分：\n"
            "## 一、板块格局概览\n"
            "## 二、重点发现\n"
            "## 三、风险提示\n"
            "## 四、值得关注的标的（5-8只）\n\n"
            "在第四部分，请从行业板块角度列出5-8只最值得关注的股票，说明关注理由。"
        ),
    },
    {
        "id": "fundamentals",
        "title": "财务基本面分析",
        "icon": "📊",
        "aggregate_fn": _aggregate_fundamentals,
        "system_prompt": (
            "你是一位专业的 A 股基本面分析师，擅长通过市盈率（PE）、市净率（PB）、"
            "市值等估值指标评估公司价值。\n"
            "你注重安全边际，善于发现被低估的投资标的。\n"
            "当前时间：{now}。请在报告中使用正确的日期。"
        ),
        "user_prompt_template": (
            "报告日期：{now}\n"
            "数据日期：{data_date}（选股池数据对应的交易日）\n\n"
            "以下是本次选股池（{total}只候选股）的基本面统计摘要：\n\n"
            "{stats}\n\n"
            "请撰写一份约2000字的基本面分析报告，使用 Markdown 格式，包含以下四个部分：\n"
            "## 一、估值面总体特征\n"
            "## 二、重点发现\n"
            "## 三、风险提示\n"
            "## 四、值得关注的标的（5-8只）\n\n"
            "在第四部分，请从基本面角度列出5-8只最值得关注的股票，说明关注理由。"
        ),
    },
]


# ── Synthesis prompt ─────────────────────────────────────────────────────────

_SYNTHESIS_SYSTEM = (
    "你是一位资深的 A 股投资总监，负责综合多位分析师的研究报告，"
    "给出最终的股票推荐。你的推荐注重多维度交叉验证——"
    "一只股票如果同时获得资金面、行业面、基本面的认可，则更值得推荐。\n"
    "当前时间：{now}。请在报告中使用正确的日期。"
)

_SYNTHESIS_USER_TEMPLATE = """报告日期：{now}
数据日期：{data_date}（选股池数据对应的交易日）

以下是三位分析师对「{strategy}」选股池（{total}只候选股）的分析报告摘要：

{report_summaries}

以下是选股池中的部分候选股票（供参考）：
{stock_list}

请完成以下两个任务：

### 任务1：综合推荐报告
撰写一份约1500字的综合推荐 Markdown 报告，包含：
## 一、市场综合判断
## 二、多维度交叉验证结果
## 三、投资建议

### 任务2：Top {top_n} 推荐列表
在报告最后，输出一个 JSON 代码块，格式如下（严格按此格式，不要有其他文字包裹）：
```json
[
  {{"symbol": "600519", "name": "贵州茅台", "score": 9.2, "reason": "资金持续流入+低估值+行业龙头"}},
  ...
]
```

要求：
- 只能从上述选股池中的股票里选择推荐（symbol 必须存在于候选池中）
- 优先推荐被多位分析师同时提及的标的
- score 范围 0-10，基于多维度综合评估
- reason 不超过30字
- 恰好推荐 {top_n} 只"""


# ── LLM call helper ──────────────────────────────────────────────────────────


def _detect_data_date(candidates: list[dict]) -> str:
    """Try to detect the data date from pywencai indicator key suffixes.

    Pywencai often appends dates like [20260306] to column names.
    Returns the detected date string (e.g. '2026-03-06') or today's date.
    """
    date_pattern = re.compile(r"\[(\d{8})\]")
    for c in candidates[:5]:
        for key in c.get("indicators", {}):
            m = date_pattern.search(key)
            if m:
                ds = m.group(1)
                try:
                    return f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}"
                except Exception:
                    pass
    # Fallback: today's date in Beijing timezone
    return datetime.now(_BEIJING_TZ).strftime("%Y-%m-%d")


def _call_llm_sync(
    system: str,
    user: str,
    max_tokens: int = 4000,
    temperature: float = 0.4,
) -> tuple[str, int, int]:
    """Synchronous LLM call. Returns (content, input_tokens, output_tokens)."""
    try:
        from app.config import settings
        from stocksage.llm.factory import create_llm

        provider = settings.DEFAULT_LLM_PROVIDER or "deepseek"
        llm = create_llm(provider)

        # Bypass proxy for domestic API calls
        saved = {}
        for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
            if key in os.environ:
                saved[key] = os.environ.pop(key)
        try:
            content = llm.call(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        finally:
            os.environ.update(saved)

        # Rough token estimate (actual depends on provider)
        input_tokens = len(system + user) // 2
        output_tokens = len(content) // 2
        return content.strip(), input_tokens, output_tokens

    except Exception as exc:
        logger.error("Analyst LLM call failed: %s", exc)
        raise


# ── AnalystTeam class ────────────────────────────────────────────────────────


class AnalystTeam:
    """Multi-perspective AI analyst team for screener candidates."""

    @staticmethod
    async def analyze(
        candidates: list[dict[str, Any]],
        strategy_context: str = "自定义筛选",
        top_n: int = 20,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        """Run the full analyst team pipeline.

        Returns:
            {
                "analysts": [
                    {"id": "...", "title": "...", "icon": "...", "report": "...markdown..."},
                    ...
                ],
                "synthesis": {
                    "report": "...markdown...",
                    "top_picks": [{"symbol", "name", "score", "reason"}, ...],
                },
                "meta": {
                    "candidate_count": int,
                    "strategy": str,
                    "duration_sec": float,
                    "total_input_tokens": int,
                    "total_output_tokens": int,
                }
            }
        """
        t0 = time.time()
        total_input = 0
        total_output = 0
        now_str = _now_beijing_str()

        # ── Step 1: Pre-aggregate (pure Python) ─────────────────────────
        # Determine data reference date range for prompts
        if date_to:
            data_date = date_to
        elif date_from:
            data_date = date_from
        else:
            data_date = _detect_data_date(candidates)

        # Build human-readable date range description for prompts
        if date_from and date_to:
            date_range_desc = f"{date_from} 至 {date_to}"
        elif date_from:
            date_range_desc = f"{date_from} 以来"
        elif date_to:
            date_range_desc = f"截至 {date_to}"
        else:
            date_range_desc = data_date

        aggregations = {}
        for analyst in ANALYSTS:
            agg_fn = analyst["aggregate_fn"]
            aggregations[analyst["id"]] = agg_fn(candidates)

        # ── Step 2: Run 3 analysts in parallel ──────────────────────────
        loop = asyncio.get_event_loop()

        async def _run_one_analyst(analyst: dict) -> dict[str, Any]:
            agg_data = aggregations[analyst["id"]]
            stats_str = json.dumps(agg_data, ensure_ascii=False, indent=2)
            system_msg = analyst["system_prompt"].format(now=now_str)
            user_msg = analyst["user_prompt_template"].format(
                total=len(candidates),
                stats=stats_str,
                now=now_str,
                data_date=date_range_desc,
            )

            try:
                content, inp, out = await loop.run_in_executor(
                    _pool,
                    partial(
                        _call_llm_sync,
                        system_msg,
                        user_msg,
                        4000,
                        0.4,
                    ),
                )
                return {
                    "id": analyst["id"],
                    "title": analyst["title"],
                    "icon": analyst["icon"],
                    "report": content,
                    "input_tokens": inp,
                    "output_tokens": out,
                    "error": None,
                }
            except Exception as exc:
                logger.warning("Analyst %s failed: %s", analyst["id"], exc)
                return {
                    "id": analyst["id"],
                    "title": analyst["title"],
                    "icon": analyst["icon"],
                    "report": f"*分析失败: {exc}*",
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "error": str(exc),
                }

        analyst_results = await asyncio.gather(
            *[_run_one_analyst(a) for a in ANALYSTS]
        )

        for r in analyst_results:
            total_input += r.get("input_tokens", 0)
            total_output += r.get("output_tokens", 0)

        # ── Step 3: Synthesis (sequential, depends on all 3) ────────────
        # Build summaries for synthesis (truncate each report to ~800 chars)
        report_summaries = ""
        for r in analyst_results:
            report_text = r["report"]
            if len(report_text) > 800:
                report_text = report_text[:800] + "...\n（报告已截断）"
            report_summaries += (
                f"### {r['icon']} {r['title']}\n{report_text}\n\n"
            )

        # Build compact stock list for synthesis (symbol + name + key indicators)
        stock_lines = []
        for c in candidates[:80]:  # limit to 80 to stay within token budget
            inds = c.get("indicators", {})
            ind_parts = []
            for k, v in list(inds.items())[:4]:
                fv = _safe_float(v)
                ind_parts.append(f"{k}={round(fv, 2)}" if fv is not None else f"{k}={v}")
            stock_lines.append(
                f"{c.get('symbol', '')} {c.get('name', '')} [{', '.join(ind_parts)}]"
            )
        stock_list_str = "\n".join(stock_lines) if stock_lines else "(无)"

        synthesis_user = _SYNTHESIS_USER_TEMPLATE.format(
            strategy=strategy_context,
            total=len(candidates),
            report_summaries=report_summaries,
            stock_list=stock_list_str,
            top_n=top_n,
            now=now_str,
            data_date=date_range_desc,
        )

        synthesis_system = _SYNTHESIS_SYSTEM.format(now=now_str)

        synthesis_report = ""
        top_picks: list[dict[str, Any]] = []

        try:
            content, inp, out = await loop.run_in_executor(
                _pool,
                partial(
                    _call_llm_sync,
                    synthesis_system,
                    synthesis_user,
                    6000,
                    0.3,
                ),
            )
            total_input += inp
            total_output += out

            # Split content: markdown report + JSON picks
            json_match = re.search(r"```json\s*\n(\[.*?\])\s*\n```", content, re.DOTALL)
            if json_match:
                synthesis_report = content[:json_match.start()].strip()
                try:
                    top_picks = json.loads(json_match.group(1))
                    if not isinstance(top_picks, list):
                        top_picks = []
                except json.JSONDecodeError:
                    logger.warning("Synthesis: failed to parse JSON picks")
                    top_picks = []
            else:
                # Try bare JSON array
                json_match2 = re.search(r"\[.*\]", content, re.DOTALL)
                if json_match2:
                    synthesis_report = content[:json_match2.start()].strip()
                    try:
                        top_picks = json.loads(json_match2.group())
                        if not isinstance(top_picks, list):
                            top_picks = []
                    except json.JSONDecodeError:
                        synthesis_report = content
                else:
                    synthesis_report = content

        except Exception as exc:
            logger.error("Synthesis analyst failed: %s", exc)
            synthesis_report = f"*综合分析失败: {exc}*"

        duration = round(time.time() - t0, 1)
        logger.info(
            "AnalystTeam done: %d candidates, %d picks, %.1fs, ~%d tokens in, ~%d tokens out",
            len(candidates),
            len(top_picks),
            duration,
            total_input,
            total_output,
        )

        return {
            "analysts": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "icon": r["icon"],
                    "report": r["report"],
                }
                for r in analyst_results
            ],
            "synthesis": {
                "report": synthesis_report,
                "top_picks": top_picks,
            },
            "meta": {
                "candidate_count": len(candidates),
                "strategy": strategy_context,
                "date_from": date_from,
                "date_to": date_to,
                "data_date": data_date,
                "date_range_desc": date_range_desc,
                "report_date": now_str,
                "duration_sec": duration,
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
            },
        }
