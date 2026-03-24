"""角色 → 工具白名单映射。

每种角色的 Agent 只能使用白名单中的工具。
通过 AgentConstraints.allowed_tools 实现。
"""

from __future__ import annotations

TOOL_PRESETS: dict[str, list[str]] = {
    # ── 分析师类 ─ 有数据获取和计算能力 ──
    "technical_analyst": [
        "fetch_price_data",
        "fetch_stock_info",
        "calc_indicator",
        "web_search",
    ],
    "fundamental_analyst": [
        "fetch_financial",
        "fetch_quarterly",
        "fetch_balance_sheet",
        "fetch_stock_info",
        "calc_valuation",
        "web_search",
        "web_fetch",
    ],
    "risk_analyst": [
        "fetch_price_data",
        "fetch_financial",
        "fetch_margin_data",
        "fetch_fund_flow",
        "calc_indicator",
        "web_search",
    ],
    "sentiment_analyst": [
        "fetch_sentiment",
        "fetch_news",
        "web_search",
    ],
    "news_analyst": [
        "fetch_news",
        "web_search",
        "web_fetch",
    ],
    "fund_flow_analyst": [
        "fetch_fund_flow",
        "fetch_northbound",
        "fetch_margin_data",
        "web_search",
    ],
    "capital_flow_analyst": [
        "fetch_fund_flow",
        "fetch_northbound",
        "fetch_margin_data",
        "web_search",
    ],
    "macro_analyst": [
        "fetch_stock_info",
        "web_search",
        "web_fetch",
    ],
    "valuation_analyst": [
        "fetch_financial",
        "fetch_quarterly",
        "fetch_stock_info",
        "calc_valuation",
        "web_search",
    ],
    "moat_analyst": [
        "fetch_financial",
        "fetch_stock_info",
        "web_search",
        "web_fetch",
    ],
    "industry_analyst": [
        "fetch_stock_info",
        "fetch_financial",
        "web_search",
        "web_fetch",
    ],
    "sector_strategist": [
        "fetch_stock_info",
        "web_search",
        "web_fetch",
    ],
    "dragon_tiger_analyst": [
        "fetch_price_data",
        "fetch_fund_flow",
        "web_search",
    ],
    "dealer_behavior_analyst": [
        "fetch_price_data",
        "fetch_fund_flow",
        "fetch_margin_data",
        "calc_indicator",
        "web_search",
    ],
    "theme_lifecycle_analyst": [
        "fetch_stock_info",
        "web_search",
        "web_fetch",
    ],

    # ── 辩论类 ─ 有状态读取和信息搜索能力 ──
    "bull_advocate": [
        "read_analysis",
        "web_search",
        "fetch_fund_flow",
        "fetch_northbound",
    ],
    "bear_advocate": [
        "read_analysis",
        "web_search",
        "fetch_margin_data",
        "fetch_news",
    ],
    "debate_r1_bull_challenge": [
        "read_analysis",
        "read_debate_record",
        "web_search",
    ],
    "debate_r1_bear_response": [
        "read_analysis",
        "read_debate_record",
        "web_search",
    ],
    "debate_r2_bull_revise": [
        "read_analysis",
        "read_debate_record",
        "web_search",
    ],
    "debate_r2_bear_revise": [
        "read_analysis",
        "read_debate_record",
        "web_search",
    ],
    "debate_r3_bull": [
        "read_analysis",
        "read_debate_record",
    ],
    "debate_r3_bear": [
        "read_analysis",
        "read_debate_record",
    ],

    # ── 专家类 ──
    "blind_spot_detector": [
        "read_analysis",
        "web_search",
    ],
    "consensus_analyzer": [
        "read_analysis",
        "read_debate_record",
    ],
    "decision_tree_builder": [
        "read_analysis",
        "read_debate_record",
    ],
    "quality_checker": [
        "read_analysis",
    ],
    "evidence_validator": [
        "read_analysis",
        "web_search",
        "web_fetch",
    ],

    # ── 决策类 ──
    "judge": [
        "read_analysis",
        "read_debate_record",
        "read_memory",
        "calc_valuation",
        "web_search",
        "ask_user",
    ],
    "reflection_module": [
        "read_analysis",
        "read_debate_record",
        "read_memory",
    ],
    "coordinator": [
        "read_analysis",
        "read_debate_record",
    ],

    # ── 研究员 ──
    "blind_spot_researcher": [
        "read_analysis",
        "web_search",
        "web_fetch",
    ],
}


def get_allowed_tools(skill_name: str, skill_constraints: object = None) -> list[str]:
    """获取指定 Skill 的允许工具列表。

    优先使用 Skill .md 中声明的 constraints.allowed_tools，
    回退到 TOOL_PRESETS 预设。
    """
    if skill_constraints and getattr(skill_constraints, "allowed_tools", None):
        return skill_constraints.allowed_tools
    return TOOL_PRESETS.get(skill_name, [])
