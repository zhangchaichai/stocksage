"""数据工具：包装 DataFetcher 方法为 Agent 可调用的 Tool。

每个工具：
1. 接收参数（symbol, 可选周期等）
2. 调用 DataFetcher 对应方法
3. 格式化结果为人类可读的字符串返回

内置 TTL 缓存：同一 symbol 同一数据类型在 TTL 内不重复请求 API。
"""

from __future__ import annotations

import asyncio
import datetime
import json
import time
from typing import Any

from stocksage.agent.tools.base import Tool
from stocksage.data.fetcher import DataFetcher


class _SafeEncoder(json.JSONEncoder):
    """JSON encoder that handles date/datetime/Timestamp objects."""

    def default(self, o: Any) -> Any:
        if isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()
        # Handle pandas Timestamp
        if hasattr(o, "isoformat"):
            return o.isoformat()
        if hasattr(o, "item"):
            # numpy scalar → python scalar
            return o.item()
        return super().default(o)


class DataToolBase(Tool):
    """数据工具基类，统一缓存和格式化逻辑。"""

    def __init__(self, fetcher: DataFetcher, cache_ttl: int = 3600):
        self._fetcher = fetcher
        self._cache: dict[str, tuple[float, Any]] = {}
        self._ttl = cache_ttl

    def _get_cached(self, key: str) -> Any | None:
        if key in self._cache:
            ts, data = self._cache[key]
            if time.time() - ts < self._ttl:
                return data
            del self._cache[key]
        return None

    def _set_cached(self, key: str, data: Any) -> None:
        self._cache[key] = (time.time(), data)

    async def _fetch(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """在线程中调用 DataFetcher 的同步方法，避免阻塞事件循环。"""
        method = getattr(self._fetcher, method_name)
        return await asyncio.to_thread(method, *args, **kwargs)

    def _format(self, data: dict | list, max_chars: int = 8000) -> str:
        """将数据格式化为可读字符串。"""
        if not data:
            return "无数据"
        text = json.dumps(data, ensure_ascii=False, indent=2, cls=_SafeEncoder)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n...(数据过长已截断)"
        return text


class FetchPriceDataTool(DataToolBase):
    """获取股票历史价格数据。"""

    @property
    def name(self) -> str:
        return "fetch_price_data"

    @property
    def description(self) -> str:
        return "获取股票历史价格数据（日期、开盘、最高、最低、收盘、成交量）"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码，如 600519",
                },
                "days": {
                    "type": "integer",
                    "description": "获取最近 N 个交易日数据，默认 120",
                    "minimum": 1,
                    "maximum": 500,
                },
            },
            "required": ["symbol"],
        }

    async def execute(self, symbol: str, days: int = 120, **kwargs: Any) -> str:
        cache_key = f"price:{symbol}:{days}"
        if cached := self._get_cached(cache_key):
            return self._format(cached)
        data = await self._fetch("fetch_price_data", symbol, days=days)
        if not data:
            return f"无法获取 {symbol} 的价格数据，请检查股票代码"
        self._set_cached(cache_key, data)
        return self._format(data)


class FetchStockInfoTool(DataToolBase):
    """获取股票基本信息。"""

    @property
    def name(self) -> str:
        return "fetch_stock_info"

    @property
    def description(self) -> str:
        return "获取股票基本信息（公司名称、行业、总市值、市盈率等）"

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
        cache_key = f"info:{symbol}"
        if cached := self._get_cached(cache_key):
            return self._format(cached)
        data = await self._fetch("fetch_stock_info", symbol)
        if not data:
            return f"无法获取 {symbol} 的基本信息"
        self._set_cached(cache_key, data)
        return self._format(data)


class FetchFinancialTool(DataToolBase):
    """获取财务分析指标。"""

    @property
    def name(self) -> str:
        return "fetch_financial"

    @property
    def description(self) -> str:
        return "获取股票财务分析指标（营收、利润、ROE、毛利率等）"

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
        cache_key = f"financial:{symbol}"
        if cached := self._get_cached(cache_key):
            return self._format(cached)
        data = await self._fetch("fetch_financial", symbol)
        if not data:
            return f"无法获取 {symbol} 的财务数据"
        self._set_cached(cache_key, data)
        return self._format(data)


class FetchQuarterlyTool(DataToolBase):
    """获取季度财报数据。"""

    @property
    def name(self) -> str:
        return "fetch_quarterly"

    @property
    def description(self) -> str:
        return "获取股票季度财报数据（单季营收、利润、同比增速）"

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
        cache_key = f"quarterly:{symbol}"
        if cached := self._get_cached(cache_key):
            return self._format(cached)
        data = await self._fetch("fetch_quarterly", symbol)
        if not data:
            return f"无法获取 {symbol} 的季报数据"
        self._set_cached(cache_key, data)
        return self._format(data)


class FetchNewsTool(DataToolBase):
    """获取股票相关新闻。"""

    def __init__(self, fetcher: DataFetcher, cache_ttl: int = 1800):
        super().__init__(fetcher, cache_ttl)

    @property
    def name(self) -> str:
        return "fetch_news"

    @property
    def description(self) -> str:
        return "获取股票相关新闻和公告"

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
        cache_key = f"news:{symbol}"
        if cached := self._get_cached(cache_key):
            return self._format(cached)
        data = await self._fetch("fetch_news", symbol)
        if not data:
            return f"无法获取 {symbol} 的新闻数据"
        self._set_cached(cache_key, data)
        return self._format(data)


class FetchFundFlowTool(DataToolBase):
    """获取资金流向数据。"""

    @property
    def name(self) -> str:
        return "fetch_fund_flow"

    @property
    def description(self) -> str:
        return "获取股票资金流向数据（主力净流入、散户流向等）"

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
        cache_key = f"fund_flow:{symbol}"
        if cached := self._get_cached(cache_key):
            return self._format(cached)
        data = await self._fetch("fetch_fund_flow", symbol)
        if not data:
            return f"无法获取 {symbol} 的资金流向数据"
        self._set_cached(cache_key, data)
        return self._format(data)


class FetchSentimentTool(DataToolBase):
    """获取市场情绪数据。"""

    @property
    def name(self) -> str:
        return "fetch_sentiment"

    @property
    def description(self) -> str:
        return "获取市场情绪数据（涨跌比、涨停板数量等）"

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
        cache_key = f"sentiment:{symbol}"
        if cached := self._get_cached(cache_key):
            return self._format(cached)
        data = await self._fetch("fetch_sentiment", symbol)
        if not data:
            return f"无法获取 {symbol} 的情绪数据"
        self._set_cached(cache_key, data)
        return self._format(data)


class FetchMarginDataTool(DataToolBase):
    """获取融资融券数据。"""

    @property
    def name(self) -> str:
        return "fetch_margin_data"

    @property
    def description(self) -> str:
        return "获取融资融券数据（融资余额、融券余额、变化趋势）"

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
        cache_key = f"margin:{symbol}"
        if cached := self._get_cached(cache_key):
            return self._format(cached)
        data = await self._fetch("fetch_margin_data", symbol)
        if not data:
            return f"无法获取 {symbol} 的融资融券数据"
        self._set_cached(cache_key, data)
        return self._format(data)


class FetchNorthboundTool(DataToolBase):
    """获取北向资金流向数据。"""

    @property
    def name(self) -> str:
        return "fetch_northbound"

    @property
    def description(self) -> str:
        return "获取北向资金流向（沪股通/深股通净买入、持仓变化）"

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
        cache_key = f"northbound:{symbol}"
        if cached := self._get_cached(cache_key):
            return self._format(cached)
        data = await self._fetch("fetch_northbound_flow", symbol)
        if not data:
            return f"无法获取 {symbol} 的北向资金数据"
        self._set_cached(cache_key, data)
        return self._format(data)


class FetchBalanceSheetTool(DataToolBase):
    """获取资产负债表数据。"""

    @property
    def name(self) -> str:
        return "fetch_balance_sheet"

    @property
    def description(self) -> str:
        return "获取资产负债表数据（总资产、总负债、股东权益等）"

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
        cache_key = f"balance_sheet:{symbol}"
        if cached := self._get_cached(cache_key):
            return self._format(cached)
        data = await self._fetch("fetch_balance_sheet", symbol)
        if not data:
            return f"无法获取 {symbol} 的资产负债表"
        self._set_cached(cache_key, data)
        return self._format(data)
