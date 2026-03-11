"""DataFetcher: 统一封装数据获取，支持 MCP 双轨制 + 多源 fallback。

数据获取优先级：cache → MCP Server → AkShare → YFinance → {}

AkShare 不同 API 使用不同的 symbol 格式：
- 裸码: "000001"（大多数 API）
- 带前缀: "SH600519" / "SZ000001"（财报类 API）
- 带小写前缀+市场: stock="000001", market="sz"（资金流 API）
DataFetcher 统一接收裸码，内部自动转换。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import wraps

import akshare as ak
import pandas as pd

from stocksage.data.cache import TTLCache

logger = logging.getLogger(__name__)

# 缓存 TTL 配置（秒）
_TTL = {
    "stock_info": 86400,
    "price_data": 14400,
    "financial": 86400,
    "quarterly": 86400,
    "news": 1800,
    "fund_flow": 3600,
    "sentiment": 3600,
    "margin": 86400,
    "northbound": 3600,
    "balance_sheet": 86400,
    "dragon_tiger": 3600,
    "industry_pe": 86400,
    "index_data": 14400,
}


def _to_prefixed(symbol: str) -> str:
    """裸码 → 带前缀格式（SH/SZ）。"""
    if symbol.startswith(("6", "9")):
        return f"SH{symbol}"
    return f"SZ{symbol}"


def _guess_market(symbol: str) -> str:
    """根据股票代码猜测市场（sh/sz/bj）。"""
    if symbol.startswith(("6", "9")):
        return "sh"
    if symbol.startswith(("4", "8")):
        return "bj"
    return "sz"


def _to_yfinance_ticker(symbol: str) -> str:
    """裸码 → YFinance ticker（yahoo-finance-mcp 也使用此格式）。"""
    suffix = ".SS" if symbol.startswith(("6", "9")) else ".SZ"
    return f"{symbol}{suffix}"


def _safe_fetch(retries: int = 2, delay: float = 2.0) -> Callable:
    """数据获取安全装饰器：自动重试 + 异常降级为空 dict。"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> dict:
            for attempt in range(retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt < retries:
                        logger.warning("%s 第 %d 次失败，重试中: %s", func.__name__, attempt + 1, e)
                        time.sleep(delay)
                    else:
                        logger.error("%s 最终失败: %s", func.__name__, e)
            return {}
        return wrapper
    return decorator


def _fetch_with_fallback(
    cache: TTLCache,
    cache_key: str,
    ttl: int,
    *fetch_fns: Callable[[], dict],
) -> dict:
    """通用 fallback 链：cache → fn1 → fn2 → ... → {}。"""
    if cached := cache.get(cache_key):
        return cached

    for fn in fetch_fns:
        try:
            result = fn()
            if result:
                cache.set(cache_key, result, ttl)
                return result
        except Exception as e:
            logger.warning("%s fallback 失败: %s", fn.__name__ if hasattr(fn, '__name__') else 'lambda', e)

    return {}


class DataFetcher:
    """数据获取统一入口：MCP 双轨 + AkShare + YFinance fallback。"""

    def __init__(self, mcp_manager=None):
        self._cache = TTLCache()
        self._mcp = mcp_manager

    def _try_mcp(self, capability: str, tool_name: str, arguments: dict) -> dict | None:
        """尝试通过 MCP Server 获取数据。"""
        if not self._mcp:
            return None
        servers = self._mcp.find_servers_for(capability)
        for server_name in servers:
            result = self._mcp.call_tool_sync(server_name, tool_name, arguments)
            if result:
                return result
        return None

    # === stock_info: MCP → AkShare → YFinance ===

    def fetch_stock_info(self, symbol: str) -> dict:
        """获取股票基本信息（含 fallback 链）。"""
        cache_key = f"stock_info:{symbol}"

        def _from_mcp():
            ticker = _to_yfinance_ticker(symbol)
            return self._try_mcp("stock_info", "get_company_info", {"symbol": ticker}) or {}

        return _fetch_with_fallback(
            self._cache, cache_key, _TTL["stock_info"],
            _from_mcp,
            lambda: self._fetch_stock_info_akshare(symbol),
            lambda: self._fetch_stock_info_yfinance(symbol),
        )

    @_safe_fetch(retries=2, delay=2.0)
    def _fetch_stock_info_akshare(self, symbol: str) -> dict:
        df = ak.stock_individual_info_em(symbol=symbol)
        return dict(zip(df["item"], df["value"]))

    @staticmethod
    def _fetch_stock_info_yfinance(symbol: str) -> dict:
        from stocksage.data.sources.yfinance_source import fetch_stock_info_yfinance
        return fetch_stock_info_yfinance(symbol)

    # === price_data: MCP → AkShare → YFinance ===

    def fetch_price_data(
        self,
        symbol: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        """获取历史价格数据（含 fallback 链）。

        优先使用 start_date/end_date（YYYY-MM-DD），否则从 end_date 向前取 days 天。
        end_date 默认为今天，start_date 不传时由 days 推算。
        """
        # Resolve effective date range
        _end = end_date or datetime.now().strftime("%Y-%m-%d")
        if start_date:
            _start = start_date
            # Recalculate days for cache key consistency
            try:
                delta = (
                    datetime.strptime(_end, "%Y-%m-%d")
                    - datetime.strptime(_start, "%Y-%m-%d")
                ).days
                days = max(delta, 1)
            except Exception:
                pass
        else:
            _start = (
                datetime.strptime(_end, "%Y-%m-%d") - timedelta(days=days * 2)
            ).strftime("%Y-%m-%d")

        cache_key = f"price_data:{symbol}:{_start}:{_end}"

        def _from_mcp():
            ticker = _to_yfinance_ticker(symbol)
            return self._try_mcp("price_data", "get_historical_data", {
                "symbol": ticker, "period1": _start, "period2": _end, "interval": "1d",
            }) or {}

        return _fetch_with_fallback(
            self._cache, cache_key, _TTL["price_data"],
            _from_mcp,
            lambda: self._fetch_price_akshare(symbol, days, _start, _end),
            lambda: self._fetch_price_yfinance(symbol, days),
        )

    @_safe_fetch(retries=2, delay=2.0)
    def _fetch_price_akshare(
        self,
        symbol: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        _end = (end_date or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
        _start = (
            start_date.replace("-", "") if start_date
            else (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")
        )
        df = ak.stock_zh_a_hist(
            symbol=symbol, period="daily",
            start_date=_start, end_date=_end, adjust="qfq",
        )
        df = df.tail(days)
        return {
            "klines": df.to_dict(orient="records"),
            "latest_price": float(df.iloc[-1]["收盘"]) if len(df) > 0 else 0,
            "days": len(df),
        }

    @staticmethod
    def _fetch_price_yfinance(symbol: str, days: int = 60) -> dict:
        from stocksage.data.sources.yfinance_source import fetch_price_yfinance
        return fetch_price_yfinance(symbol, days)

    # === financial: MCP → AkShare ===

    def fetch_financial(self, symbol: str, end_date: str | None = None) -> dict:
        """获取关键财务指标（含 fallback 链）。

        end_date: YYYY-MM-DD，指定后只拉该日期所在年份及之前2年的数据。
        """
        cache_key = f"financial:{symbol}:{end_date or 'now'}"

        def _from_mcp():
            ticker = _to_yfinance_ticker(symbol)
            return self._try_mcp("financial", "get_quote_summary", {
                "symbol": ticker,
                "modules": ["financialData", "defaultKeyStatistics", "incomeStatementHistory"],
            }) or {}

        return _fetch_with_fallback(
            self._cache, cache_key, _TTL["financial"],
            _from_mcp,
            lambda: self._fetch_financial_akshare(symbol, end_date),
        )

    @_safe_fetch(retries=2, delay=2.0)
    def _fetch_financial_akshare(self, symbol: str, end_date: str | None = None) -> dict:
        # Use year from end_date if given, otherwise current year
        if end_date:
            try:
                ref_year = datetime.strptime(end_date, "%Y-%m-%d").year
            except Exception:
                ref_year = datetime.now().year
        else:
            ref_year = datetime.now().year

        df = ak.stock_financial_analysis_indicator(
            symbol=symbol, start_year=str(ref_year - 2),
        )
        if df.empty:
            return {}
        # Only keep records up to end_date if specified
        if end_date and "日期" in df.columns:
            try:
                df["日期"] = pd.to_datetime(df["日期"])
                df = df[df["日期"] <= pd.to_datetime(end_date)]
            except Exception:
                pass
        records = df.head(4).to_dict(orient="records")
        return {"indicators": records, "periods": len(records)}

    # === quarterly: MCP → AkShare ===

    def fetch_quarterly(self, symbol: str, end_date: str | None = None) -> dict:
        """获取季报数据（利润表摘要）。end_date: YYYY-MM-DD 截止日期。"""
        cache_key = f"quarterly:{symbol}:{end_date or 'now'}"

        return _fetch_with_fallback(
            self._cache, cache_key, _TTL["quarterly"],
            lambda: self._fetch_quarterly_akshare(symbol, end_date),
        )

    @_safe_fetch(retries=2, delay=2.0)
    def _fetch_quarterly_akshare(self, symbol: str, end_date: str | None = None) -> dict:
        prefixed = _to_prefixed(symbol)
        df = ak.stock_profit_sheet_by_report_em(symbol=prefixed)
        if df.empty:
            return {}
        key_cols = [
            "REPORT_DATE", "TOTAL_OPERATE_INCOME", "OPERATE_INCOME",
            "OPERATE_COST", "NETPROFIT",
        ]
        available_cols = [c for c in key_cols if c in df.columns]
        df = df[available_cols]
        # Filter by end_date if specified (REPORT_DATE column)
        if end_date and "REPORT_DATE" in df.columns:
            try:
                df["REPORT_DATE"] = pd.to_datetime(df["REPORT_DATE"])
                df = df[df["REPORT_DATE"] <= pd.to_datetime(end_date)]
            except Exception:
                pass
        records = df.head(8).to_dict(orient="records")
        return {"quarterly": records, "periods": len(records)}

    # === news: MCP → AkShare ===

    def fetch_news(self, symbol: str, limit: int = 10) -> dict:
        """获取个股新闻（AkShare 优先，返回中文相关新闻）。"""
        cache_key = f"news:{symbol}"

        return _fetch_with_fallback(
            self._cache, cache_key, _TTL["news"],
            lambda: self._fetch_news_akshare(symbol, limit),
        )

    @_safe_fetch(retries=2, delay=2.0)
    def _fetch_news_akshare(self, symbol: str, limit: int = 10) -> dict:
        df = ak.stock_news_em(symbol=symbol)
        df = df.head(limit)
        records = df.to_dict(orient="records")
        return {"news": records, "count": len(records)}

    # === market_news: 财联社快讯（市场热点新闻）===

    @_safe_fetch(retries=2, delay=2.0)
    def fetch_market_news(self, symbol: str) -> dict:
        """获取市场热点新闻（财联社快讯，最近50条）。"""
        cache_key = "market_news:global"
        if cached := self._cache.get(cache_key):
            return cached
        df = ak.stock_info_global_cls()
        if isinstance(df, pd.DataFrame) and not df.empty:
            records = df.head(50).to_dict(orient="records")
        else:
            records = []
        result = {"market_news": records, "count": len(records)}
        self._cache.set(cache_key, result, _TTL["news"])
        return result

    # === fund_flow: MCP → AkShare ===

    def fetch_fund_flow(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        """获取个股资金流向，按 start_date~end_date 时间段过滤（YYYY-MM-DD）。
        不传则取最近20个交易日。
        """
        cache_key = f"fund_flow:{symbol}:{start_date or ''}:{end_date or 'now'}"

        return _fetch_with_fallback(
            self._cache, cache_key, _TTL["fund_flow"],
            lambda: self._fetch_fund_flow_akshare(symbol, start_date, end_date),
        )

    @_safe_fetch(retries=2, delay=2.0)
    def _fetch_fund_flow_akshare(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        market = _guess_market(symbol)
        df = ak.stock_individual_fund_flow(stock=symbol, market=market)
        if "日期" in df.columns:
            try:
                df["日期"] = pd.to_datetime(df["日期"])
                if start_date:
                    df = df[df["日期"] >= pd.to_datetime(start_date)]
                if end_date:
                    df = df[df["日期"] <= pd.to_datetime(end_date)]
            except Exception:
                pass
        df = df.tail(20)
        records = df.to_dict(orient="records")
        return {"fund_flow": records, "days": len(records)}

    # === sentiment: AkShare only（无 MCP 源）===

    @_safe_fetch(retries=2, delay=2.0)
    def fetch_sentiment(self, symbol: str) -> dict:
        """获取市场情绪数据（综合评价历史评分）。"""
        cache_key = f"sentiment:{symbol}"
        if cached := self._cache.get(cache_key):
            return cached
        df = ak.stock_comment_detail_zhpj_lspf_em(symbol=symbol)
        if isinstance(df, pd.DataFrame) and not df.empty:
            records = df.tail(30).to_dict(orient="records")
        else:
            records = []
        result = {"sentiment_scores": records, "count": len(records)}
        self._cache.set(cache_key, result, _TTL["sentiment"])
        return result

    # === 新增数据源：margin / northbound / balance_sheet ===

    @_safe_fetch(retries=2, delay=2.0)
    def fetch_margin_data(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        """获取融资融券数据，按 start_date~end_date 时间段回溯10个交易日。

        start_date/end_date: YYYY-MM-DD。不传则从今天向前回溯。
        """
        cache_key = f"margin:{symbol}:{start_date or ''}:{end_date or 'now'}"
        if cached := self._cache.get(cache_key):
            return cached

        is_sh = symbol.startswith(("6", "9"))
        all_records = []
        collected_dates = set()

        # 确定回溯基准日期（从 end_date 开始向前）
        base_date = (
            datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
        )
        start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None

        # 回溯最多60天（时间段可能较长），尝试收集10个交易日的数据
        for days_back in range(1, 61):
            if len(collected_dates) >= 10:
                break
            check_date = base_date - timedelta(days=days_back)
            # 不超出 start_date
            if start_dt and check_date < start_dt:
                break
            date_str = check_date.strftime("%Y%m%d")
            try:
                if is_sh:
                    df = ak.stock_margin_detail_sse(date=date_str)
                else:
                    df = ak.stock_margin_detail_szse(date=date_str)

                if not isinstance(df, pd.DataFrame) or df.empty:
                    continue

                code_col = next((c for c in df.columns if "代码" in c), None)
                if code_col:
                    stock_df = df[df[code_col].astype(str).str.strip() == symbol]
                else:
                    continue

                if stock_df.empty:
                    continue

                if date_str not in collected_dates:
                    collected_dates.add(date_str)
                    record = stock_df.to_dict(orient="records")[0]
                    record["date"] = date_str
                    all_records.append(record)

            except Exception:
                continue

        if not all_records:
            return {}

        all_records.sort(key=lambda x: x.get("date", ""))
        result = {"margin": all_records, "count": len(all_records), "days": len(all_records)}
        self._cache.set(cache_key, result, _TTL["margin"])
        return result

    @_safe_fetch(retries=2, delay=2.0)
    def fetch_northbound_flow(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        """获取北向资金流向数据，按 start_date~end_date 时间段过滤。"""
        cache_key = f"northbound:{symbol}:{start_date or ''}:{end_date or 'now'}"
        if cached := self._cache.get(cache_key):
            return cached

        def _filter_date_range(df: pd.DataFrame) -> pd.DataFrame:
            date_cols = [c for c in df.columns if "日期" in c or "date" in c.lower()]
            if date_cols:
                try:
                    df = df.copy()
                    df[date_cols[0]] = pd.to_datetime(df[date_cols[0]])
                    if start_date:
                        df = df[df[date_cols[0]] >= pd.to_datetime(start_date)]
                    if end_date:
                        df = df[df[date_cols[0]] <= pd.to_datetime(end_date)]
                except Exception:
                    pass
            return df

        # 方案1：个股级别北向持股数据
        try:
            df = ak.stock_hsgt_individual_em(symbol=symbol)
            if isinstance(df, pd.DataFrame) and not df.empty:
                df = _filter_date_range(df)
                records = df.tail(20).to_dict(orient="records")
                result = {
                    "northbound_flow": records,
                    "days": len(records),
                    "data_type": "individual_stock",
                }
                self._cache.set(cache_key, result, _TTL["northbound"])
                return result
        except Exception as e:
            logger.debug("个股北向数据获取失败: %s, 尝试整体数据", e)

        # 方案2：沪/深股通整体数据（回退）
        channel = "沪股通" if symbol.startswith(("6", "9")) else "深股通"
        df = ak.stock_hsgt_hist_em(symbol=channel)
        if isinstance(df, pd.DataFrame) and not df.empty:
            df = _filter_date_range(df)
            key_col = "当日成交净买额"
            if key_col in df.columns:
                df = df.dropna(subset=[key_col])
            records = df.tail(20).to_dict(orient="records")
        else:
            records = []
        result = {
            "northbound_flow": records,
            "days": len(records),
            "data_type": "channel_level",
        }
        self._cache.set(cache_key, result, _TTL["northbound"])
        return result

    @_safe_fetch(retries=2, delay=2.0)
    def fetch_balance_sheet(self, symbol: str, end_date: str | None = None) -> dict:
        """获取资产负债表数据。end_date: YYYY-MM-DD 截止期报告。"""
        cache_key = f"balance_sheet:{symbol}:{end_date or 'now'}"
        if cached := self._cache.get(cache_key):
            return cached
        prefixed = _to_prefixed(symbol)
        df = ak.stock_balance_sheet_by_report_em(symbol=prefixed)
        if df.empty:
            return {}
        # Filter by end_date (REPORT_DATE or 报告期 column)
        if end_date:
            date_col = next((c for c in df.columns if "REPORT" in c.upper() or "报告" in c), None)
            if date_col:
                try:
                    df[date_col] = pd.to_datetime(df[date_col])
                    df = df[df[date_col] <= pd.to_datetime(end_date)]
                except Exception:
                    pass
        records = df.head(4).to_dict(orient="records")
        result = {"balance_sheet": records, "periods": len(records)}
        self._cache.set(cache_key, result, _TTL["balance_sheet"])
        return result

    # === dragon_tiger: AkShare only ===

    def fetch_dragon_tiger(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        days: int = 30,
    ) -> dict:
        """获取龙虎榜数据。优先使用 start_date/end_date，否则取近 days 天。"""
        cache_key = f"dragon_tiger:{symbol}:{start_date or ''}:{end_date or 'now'}"

        return _fetch_with_fallback(
            self._cache, cache_key, _TTL["dragon_tiger"],
            lambda: self._fetch_dragon_tiger_akshare(symbol, start_date, end_date, days),
        )

    @_safe_fetch(retries=2, delay=2.0)
    def _fetch_dragon_tiger_akshare(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        days: int = 30,
    ) -> dict:
        _end = (end_date or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
        if start_date:
            _start = start_date.replace("-", "")
        else:
            _start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        df = ak.stock_lhb_detail_em(
            symbol=symbol,
            start_date=_start,
            end_date=_end,
        )
        if not isinstance(df, pd.DataFrame) or df.empty:
            return {}

        records = df.to_dict(orient="records")
        return {
            "dragon_tiger": records,
            "count": len(records),
            "symbol": symbol,
        }

    # === industry_pe: AkShare only ===

    def fetch_industry_pe(self, industry: str = "", date: str = "") -> dict:
        """获取行业 PE 比率数据。

        Args:
            industry: 行业名称（可选，为空则返回全部行业）
            date: 日期字符串 YYYYMMDD（可选，默认最近一期）
        """
        cache_key = f"industry_pe:{industry}:{date}"

        return _fetch_with_fallback(
            self._cache, cache_key, _TTL["industry_pe"],
            lambda: self._fetch_industry_pe_akshare(industry, date),
        )

    @_safe_fetch(retries=2, delay=2.0)
    def _fetch_industry_pe_akshare(self, industry: str = "", date: str = "") -> dict:
        """通过 AkShare 获取行业 PE 数据（巨潮资讯）。"""
        kwargs: dict = {}
        if date:
            kwargs["date"] = date

        df = ak.stock_industry_pe_ratio_cninfo(**kwargs)
        if not isinstance(df, pd.DataFrame) or df.empty:
            return {}

        records = df.to_dict(orient="records")

        # Filter by industry name if specified
        if industry:
            records = [
                r for r in records
                if industry in str(r.get("行业名称", "")) or industry in str(r.get("行业分类", ""))
            ]

        return {
            "industry_pe": records,
            "count": len(records),
            "query_industry": industry or "all",
        }

    # === index_data: AkShare only ===

    def fetch_index_data(self, index_code: str = "000300", days: int = 120) -> dict:
        """获取沪深指数日线数据（用于 Beta 计算等）。

        Args:
            index_code: 指数代码（000300=沪深300, 000001=上证指数, 399001=深证成指）
            days: 获取近 N 天的数据
        """
        cache_key = f"index_data:{index_code}:{days}"

        return _fetch_with_fallback(
            self._cache, cache_key, _TTL["index_data"],
            lambda: self._fetch_index_data_akshare(index_code, days),
        )

    @_safe_fetch(retries=2, delay=2.0)
    def _fetch_index_data_akshare(self, index_code: str = "000300", days: int = 120) -> dict:
        """通过 AkShare 获取指数日线数据。"""
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end_date = datetime.now().strftime("%Y%m%d")

        df = ak.stock_zh_index_daily(symbol=f"sh{index_code}")
        if not isinstance(df, pd.DataFrame) or df.empty:
            return {}

        # Filter by date range
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df[df["date"] >= start_date]
            df = df[df["date"] <= end_date]

        records = df.to_dict(orient="records")
        return {
            "index_data": records,
            "index_code": index_code,
            "count": len(records),
        }
