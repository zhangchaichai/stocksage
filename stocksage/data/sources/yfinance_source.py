"""YFinance 备用数据源：当 AkShare 不可用时提供 fallback。

A 股代码转换规则：
- 6/9 开头 → .SS（上海）
- 0/3 开头 → .SZ（深圳）
列名归一化为中文，与 AkShare 输出格式对齐。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _to_yfinance_ticker(symbol: str) -> str:
    """A 股裸码 → yfinance ticker。"""
    suffix = ".SS" if symbol.startswith(("6", "9")) else ".SZ"
    return f"{symbol}{suffix}"


def fetch_price_yfinance(symbol: str, days: int = 60) -> dict:
    """通过 yfinance 获取 A 股价格数据（AkShare 的 fallback）。"""
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance 未安装，fallback 不可用")
        return {}

    ticker = _to_yfinance_ticker(symbol)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days * 2)

    try:
        tk = yf.Ticker(ticker)
        df = tk.history(
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
        )
    except Exception as e:
        logger.warning("yfinance 获取失败 %s: %s", ticker, e)
        return {}

    if df.empty:
        return {}

    df = df.tail(days)

    # 列名归一化为 AkShare 中文格式
    records = [
        {
            "日期": idx.strftime("%Y-%m-%d"),
            "开盘": round(float(row["Open"]), 2),
            "收盘": round(float(row["Close"]), 2),
            "最高": round(float(row["High"]), 2),
            "最低": round(float(row["Low"]), 2),
            "成交量": int(row["Volume"]),
        }
        for idx, row in df.iterrows()
    ]

    return {
        "klines": records,
        "latest_price": records[-1]["收盘"] if records else 0,
        "days": len(records),
        "source": "yfinance",
    }


def fetch_stock_info_yfinance(symbol: str) -> dict:
    """通过 yfinance 获取股票基本信息（AkShare 的 fallback）。"""
    try:
        import yfinance as yf
    except ImportError:
        return {}

    ticker = _to_yfinance_ticker(symbol)

    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
    except Exception as e:
        logger.warning("yfinance info 获取失败 %s: %s", ticker, e)
        return {}

    if not info:
        return {}

    # 归一化为 AkShare 风格的中文字段
    return {
        "股票代码": symbol,
        "股票简称": info.get("shortName", ""),
        "总市值": info.get("marketCap", ""),
        "流通市值": info.get("marketCap", ""),
        "行业": info.get("industry", ""),
        "上市时间": "",
        "source": "yfinance",
    }
