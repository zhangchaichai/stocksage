"""为指定角色构建 ToolRegistry 实例。"""

from __future__ import annotations

import logging
from typing import Any, Callable

from stocksage.agent.tools.registry import ToolRegistry

try:
    from nanobot.agent.tools.web import WebFetchTool, WebSearchTool
except ImportError:
    WebFetchTool = None  # type: ignore[assignment,misc]
    WebSearchTool = None  # type: ignore[assignment,misc]

from stocksage.agent.tools.compute_tools import CalcIndicatorTool, CalcValuationTool
from stocksage.agent.tools.data_tools import (
    FetchBalanceSheetTool,
    FetchFinancialTool,
    FetchFundFlowTool,
    FetchMarginDataTool,
    FetchNewsTool,
    FetchNorthboundTool,
    FetchPriceDataTool,
    FetchQuarterlyTool,
    FetchSentimentTool,
    FetchStockInfoTool,
)
from stocksage.agent.tools.presets import get_allowed_tools
from stocksage.agent.tools.state_tools import (
    AskUserTool,
    ReadAnalysisTool,
    ReadDebateRecordTool,
    ReadMemoryTool,
)
from stocksage.data.fetcher import DataFetcher

logger = logging.getLogger(__name__)


def build_tool_registry(
    skill_name: str,
    state: dict[str, Any],
    fetcher: DataFetcher,
    *,
    skill_constraints: object = None,
    web_search_config: Any = None,
    web_proxy: str | None = None,
    interaction_callback: Callable | None = None,
) -> ToolRegistry:
    """为指定角色构建工具注册表。

    只注册该角色被允许使用的工具。
    """
    allowed = get_allowed_tools(skill_name, skill_constraints)
    if not allowed:
        return ToolRegistry()

    registry = ToolRegistry()

    # All available tools and their factories
    tool_factories: dict[str, Callable] = {
        "fetch_price_data": lambda: FetchPriceDataTool(fetcher),
        "fetch_stock_info": lambda: FetchStockInfoTool(fetcher),
        "fetch_financial": lambda: FetchFinancialTool(fetcher),
        "fetch_quarterly": lambda: FetchQuarterlyTool(fetcher),
        "fetch_news": lambda: FetchNewsTool(fetcher),
        "fetch_fund_flow": lambda: FetchFundFlowTool(fetcher),
        "fetch_sentiment": lambda: FetchSentimentTool(fetcher),
        "fetch_margin_data": lambda: FetchMarginDataTool(fetcher),
        "fetch_northbound": lambda: FetchNorthboundTool(fetcher),
        "fetch_balance_sheet": lambda: FetchBalanceSheetTool(fetcher),
        "calc_indicator": lambda: CalcIndicatorTool(fetcher),
        "calc_valuation": lambda: CalcValuationTool(fetcher),
        **({"web_search": lambda: WebSearchTool(config=web_search_config, proxy=web_proxy)} if WebSearchTool else {}),
        **({"web_fetch": lambda: WebFetchTool(proxy=web_proxy)} if WebFetchTool else {}),
        "read_analysis": lambda: ReadAnalysisTool(state),
        "read_debate_record": lambda: ReadDebateRecordTool(state),
        "read_memory": lambda: ReadMemoryTool(state),
        "ask_user": lambda: AskUserTool(interaction_callback),
    }

    for tool_name in allowed:
        factory = tool_factories.get(tool_name)
        if factory:
            registry.register(factory())
        else:
            logger.warning("未知工具: %s (skill=%s)", tool_name, skill_name)

    return registry
