"""NL → pywencai query translator.

Two-tier approach:
  1. Rule layer (keyword matching) — zero cost, instant response
  2. DeepSeek fallback — for queries that don't match any rule
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ── Rule layer ─────────────────────────────────────────────────────────────────
#
# Maps keyword patterns to ready-to-use pywencai query strings.
# Listed in priority order (first match wins).

_RULE_MAP: list[tuple[list[str], str]] = [
    # 低价类
    (["低价", "低股价", "便宜", "价格低"],
     "股价<10元，非ST，沪深A股，成交额由小至大排名"),
    # 高成长
    (["高成长", "高增长", "净利润增长", "业绩增长"],
     "净利润增长率≥50%，非ST，沪深A股，净利润增长率由大至小排名"),
    # 低价高成长（组合）
    (["低价高成长", "低价成长", "低价高增"],
     "股价<15元，净利润增长率≥50%，非ST，沪深A股，净利润增长率由大至小排名"),
    # 主力资金
    (["主力资金", "主力净流入", "资金流入", "主力流入"],
     "近5日主力资金净流入，市值50-500亿，非ST，主力净流入额由大至小排名"),
    # 北向资金
    (["北向", "北向资金", "外资", "沪深股通"],
     "北向资金连续5日净买入，净买入额>1亿，市值>50亿"),
    # 均线金叉
    (["金叉", "均线金叉", "ma金叉", "均线突破"],
     "MA5上穿MA20，MACD金叉，RSI在40-70，非ST"),
    # 超跌反弹
    (["超跌", "超跌反弹", "低位反弹", "跌多了"],
     "RSI<25，近20日跌幅>20%，非ST，沪深A股"),
    # 高股息
    (["高股息", "高分红", "股息率", "分红多"],
     "股息率>3%，PE<20，ROE>10%，非ST"),
    # 小市值
    (["小市值", "小盘", "小盘股"],
     "总市值≤50亿，非ST，沪深A股，总市值由小至大排名"),
    # 创新高
    (["创新高", "新高", "突破新高", "52周新高"],
     "今日创52周新高，成交量是20日均量1.5倍，非ST"),
    # 量比大
    (["量比", "量比大", "放量", "成交量放大"],
     "量比>3，换手率>5%，非ST，沪深A股，量比由大至小排名"),
    # 换手率
    (["换手率高", "高换手", "活跃"],
     "换手率>10%，市值<200亿，非ST，换手率由大至小排名"),
]


def translate_by_rules(query: str) -> str | None:
    """Try to match query to a rule. Returns pywencai query string or None."""
    text = query.strip().lower()
    for keywords, pywencai_q in _RULE_MAP:
        for kw in keywords:
            if kw in text:
                return pywencai_q
    return None


async def translate_by_llm(query: str) -> str | None:
    """Use DeepSeek to translate natural language to a pywencai query."""
    try:
        from app.config import settings
        from stocksage.llm.factory import create_llm

        provider = settings.DEFAULT_LLM_PROVIDER or "deepseek"
        llm = create_llm(provider)

        prompt = f"""你是一位 A 股量化选股专家，熟悉同花顺问财(pywencai)的查询语法。

用户输入了如下自然语言选股需求：
「{query}」

请将其转换为一条合法的同花顺问财查询语句，要求：
1. 使用中文，格式类似：「股价<10元，非ST，沪深A股，成交额由小至大排名」
2. 条件尽量精确，包含排序字段
3. 如果需求不清晰，给出最合理的解释
4. 只输出查询语句本身，不要其他解释文字"""

        response = llm.invoke(prompt)
        content = response.content.strip() if hasattr(response, "content") else str(response).strip()
        # Remove surrounding quotes if any
        content = content.strip("「」\"'")
        return content if content else None

    except Exception as exc:
        logger.warning("NL translator LLM call failed: %s", exc)
        return None


def find_strategy_hint(query: str) -> str | None:
    """Return a matching strategy id if the query closely matches one."""
    text = query.strip().lower()
    hints = {
        "低价": "low_price_bull",
        "主力": "mainkuai",
        "小市值": "small_cap",
        "北向": "northbound_follow",
        "金叉": "golden_cross",
        "高股息": "high_dividend",
        "新高": "breakout_new_high",
        "超跌": "oversold_rebound",
        "roe": "roe_moat",
        "净利": "profit_growth",
    }
    for kw, strat_id in hints.items():
        if kw in text:
            return strat_id
    return None
