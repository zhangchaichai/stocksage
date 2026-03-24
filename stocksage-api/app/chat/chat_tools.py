"""ChatAgent 的专属工具。

这些工具面向用户对话场景，与 SkillAgent 的分析工具不同：
- SkillAgent 工具: fetch_price_data, calc_indicator — 分析过程使用
- ChatAgent 工具: run_analysis, screen_stocks, navigate — 对话交互使用

两者可以共享部分工具（如 web_search）。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from stocksage.agent.tools.base import Tool
from stocksage.agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class RunAnalysisTool(Tool):
    """启动股票分析工作流。"""

    def __init__(self, create_run_fn: Callable | None = None):
        self._create_run = create_run_fn

    @property
    def name(self) -> str:
        return "run_analysis"

    @property
    def description(self) -> str:
        return (
            "对指定股票启动深度分析工作流。"
            "支持三种模式: quick(快速), standard(标准), deep(深度)"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码，如 600519",
                },
                "stock_name": {
                    "type": "string",
                    "description": "股票名称（可选）",
                },
                "mode": {
                    "type": "string",
                    "enum": ["quick", "standard", "deep"],
                    "description": "分析模式，默认 standard",
                },
            },
            "required": ["symbol"],
        }

    async def execute(
        self,
        symbol: str,
        stock_name: str = "",
        mode: str = "standard",
        **kwargs: Any,
    ) -> str:
        if self._create_run:
            try:
                run_id = await self._create_run(symbol, stock_name, mode)
                if run_id:
                    return json.dumps(
                        {
                            "status": "started",
                            "run_id": run_id,
                            "symbol": symbol,
                            "mode": mode,
                            "message": f"已启动 {mode} 模式分析",
                        },
                        ensure_ascii=False,
                    )
            except Exception as e:
                logger.error("启动分析失败: %s", e)
        return f"启动分析失败，请检查股票代码 {symbol} 是否正确"


class ScreenStocksTool(Tool):
    """调用选股器筛选股票。"""

    def __init__(self, screen_fn: Callable | None = None):
        self._screen = screen_fn

    @property
    def name(self) -> str:
        return "screen_stocks"

    @property
    def description(self) -> str:
        return "根据策略筛选股票。支持: 低估值、高分红、成长股、趋势突破等策略"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "strategy": {
                    "type": "string",
                    "description": "筛选策略描述，如 '低PE高分红' 或 '均线多头排列'",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回几只股票",
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": ["strategy"],
        }

    async def execute(
        self,
        strategy: str,
        limit: int = 10,
        **kwargs: Any,
    ) -> str:
        if self._screen:
            try:
                results = await self._screen(strategy, limit)
                return json.dumps(results, ensure_ascii=False)
            except Exception as e:
                logger.error("选股失败: %s", e)
        return json.dumps(
            {"message": f"选股功能暂不可用。策略: {strategy}"},
            ensure_ascii=False,
        )


class NavigateTool(Tool):
    """导航到前端页面。"""

    @property
    def name(self) -> str:
        return "navigate"

    @property
    def description(self) -> str:
        return (
            "导航到指定功能页面。可用路由: "
            "/screener(选股), /indicators(指标), /backtest(回测), "
            "/portfolio(持仓), /memory(记忆), /evolution(进化)"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "route": {
                    "type": "string",
                    "description": "目标路由路径",
                },
                "params": {
                    "type": "object",
                    "description": '路由参数，如 {"symbol": "600519"}',
                },
            },
            "required": ["route"],
        }

    async def execute(
        self,
        route: str,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            if query:
                route = f"{route}?{query}"
        return json.dumps({"navigated": True, "route": route}, ensure_ascii=False)


class QueryStockInfoTool(Tool):
    """快速查询股票基本信息。"""

    def __init__(self, fetcher: Any = None):
        self._fetcher = fetcher

    @property
    def name(self) -> str:
        return "query_stock"

    @property
    def description(self) -> str:
        return "快速查询股票的基本信息、最新价格、涨跌幅等"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "股票代码"},
            },
            "required": ["symbol"],
        }

    async def execute(self, symbol: str, **kwargs: Any) -> str:
        if self._fetcher:
            try:
                import asyncio

                info = await asyncio.to_thread(
                    self._fetcher.fetch_stock_info, symbol,
                )
                if info:
                    return json.dumps(info, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error("查询股票信息失败: %s", e)
        return f"未能获取 {symbol} 的信息"


def build_chat_tool_registry(
    *,
    create_run_fn: Callable | None = None,
    screen_fn: Callable | None = None,
    fetcher: Any = None,
    web_search_config: Any = None,
    web_proxy: str | None = None,
) -> ToolRegistry:
    """构建 ChatAgent 的工具注册表。"""
    registry = ToolRegistry()

    # Chat-specific tools
    registry.register(RunAnalysisTool(create_run_fn))
    registry.register(ScreenStocksTool(screen_fn))
    registry.register(NavigateTool())
    registry.register(QueryStockInfoTool(fetcher))

    # Data & compute tools — give ChatAgent access to real market data
    if fetcher:
        from stocksage.agent.tools.compute_tools import (
            CalcIndicatorTool,
            CalcValuationTool,
        )
        from stocksage.agent.tools.data_tools import (
            FetchFinancialTool,
            FetchFundFlowTool,
            FetchNewsTool,
            FetchPriceDataTool,
            FetchStockInfoTool,
        )

        registry.register(FetchPriceDataTool(fetcher))
        registry.register(FetchStockInfoTool(fetcher))
        registry.register(FetchFinancialTool(fetcher))
        registry.register(FetchNewsTool(fetcher))
        registry.register(FetchFundFlowTool(fetcher))
        registry.register(CalcIndicatorTool(fetcher))
        registry.register(CalcValuationTool(fetcher))

    # Shared tools
    try:
        from nanobot.agent.tools.web import WebSearchTool

        registry.register(WebSearchTool(config=web_search_config, proxy=web_proxy))
    except ImportError:
        pass

    return registry
