"""Screener service: filter evaluation and stock pool resolution."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Operator mapping
_OPS = {
    "lt": lambda a, b: a < b,
    "gt": lambda a, b: a > b,
    "eq": lambda a, b: a == b,
    "lte": lambda a, b: a <= b,
    "gte": lambda a, b: a >= b,
    "ne": lambda a, b: a != b,
}

# ── Market / board filter: maps key → code prefix(es) ────────────────────────
# sh_main:  沪市主板 (60x, 900x, exclude 688x)
# sz_main:  深市主板 (00x)
# cyb:      创业板 (30x)
# kcb:      科创板 (688x)
# bj:       北交所 (4x, 8x)
_MARKET_PREFIXES: dict[str, tuple[str, ...]] = {
    "sh_main": ("60", "90"),
    "sz_main": ("00",),
    "cyb":     ("30",),
    "kcb":     ("688",),
    "bj":      ("4", "8"),
}
# sh_main should exclude 688 (kcb)
_MARKET_EXCLUDE_PREFIXES: dict[str, tuple[str, ...]] = {
    "sh_main": ("688",),
}


def _apply_market_filters(df, market_filters: list[str]):
    """Apply board/market prefix filters to an AkShare spot DataFrame.

    *df* must have a '代码' column.  Returns the filtered DataFrame.
    If *market_filters* is empty, returns *df* unchanged.
    """
    if not market_filters:
        return df

    import pandas as pd

    codes = df["代码"].astype(str)
    mask = pd.Series([False] * len(df), index=df.index)

    for mf in market_filters:
        prefixes = _MARKET_PREFIXES.get(mf)
        if not prefixes:
            continue
        sub_mask = codes.str.startswith(prefixes)
        # Apply exclusions (e.g. sh_main excludes 688)
        excl = _MARKET_EXCLUDE_PREFIXES.get(mf)
        if excl:
            sub_mask = sub_mask & ~codes.str.startswith(excl)
        mask = mask | sub_mask

    return df[mask]


def _get_cyb_stocks() -> list[tuple[str, str]]:
    """Get ChiNext (创业板) stocks — codes starting with 30."""
    import akshare as ak
    df = ak.stock_zh_a_spot_em()
    filtered = df[df["代码"].astype(str).str.startswith("30")]
    return list(zip(filtered["代码"].astype(str).tolist(), filtered["名称"].tolist()))


def _filter_main_sh() -> list[tuple[str, str]]:
    """Shanghai main board: codes starting with 60 (exclude 688=STAR)."""
    import akshare as ak
    df = ak.stock_zh_a_spot_em()
    codes = df["代码"].astype(str)
    filtered = df[codes.str.startswith("60") & ~codes.str.startswith("688")]
    return list(zip(filtered["代码"].astype(str).tolist(), filtered["名称"].tolist()))


def _filter_main_sz() -> list[tuple[str, str]]:
    """Shenzhen main board: codes starting with 00 (exclude 30=ChiNext)."""
    import akshare as ak
    df = ak.stock_zh_a_spot_em()
    filtered = df[df["代码"].astype(str).str.startswith("00")]
    return list(zip(filtered["代码"].astype(str).tolist(), filtered["名称"].tolist()))


# Pool map: id → (label, factory)
_POOL_MAP: dict[str, tuple[str, Any]] = {
    "hs300":   ("沪深300",  "000300"),
    "zz500":   ("中证500",  "000905"),
    "zz1000":  ("中证1000", "000852"),
    "kc50":    ("科创50",   "000688"),
}


def resolve_stock_pool(
    pool: str,
    custom_symbols: list[str] | None = None,
    market_filters: list[str] | None = None,
) -> list[tuple[str, str]]:
    """Return list of (symbol, name) tuples for the given pool.

    If *market_filters* is provided (non-empty), an additional board/prefix
    filter is applied on top of the pool selection.  This is most useful when
    pool='all_a' and you only want specific boards.

    Falls back to a small built-in list if AkShare is unavailable.
    """
    if pool == "custom" and custom_symbols:
        return [(s, s) for s in custom_symbols]

    try:
        import akshare as ak

        # Index constituent pools
        if pool in _POOL_MAP:
            _, index_code = _POOL_MAP[pool]
            df = ak.index_stock_cons_df(symbol=index_code)
            pairs = list(zip(df["品种代码"].tolist(), df["品种名称"].tolist()))
            # market_filters have limited effect on index pools (they're
            # already specific), but apply anyway for consistency.
            if market_filters:
                import pandas as pd
                tmp = pd.DataFrame(pairs, columns=["代码", "名称"])
                tmp = _apply_market_filters(tmp, market_filters)
                return list(zip(tmp["代码"].tolist(), tmp["名称"].tolist()))
            return pairs

        # Filtered full-market pools
        if pool == "all_a":
            df = ak.stock_zh_a_spot_em()
            if market_filters:
                df = _apply_market_filters(df, market_filters)
            return list(zip(df["代码"].tolist(), df["名称"].tolist()))
        elif pool == "cyb":
            return _get_cyb_stocks()
        elif pool == "main_sh":
            return _filter_main_sh()
        elif pool == "main_sz":
            return _filter_main_sz()
        else:
            # Default: hs300
            df = ak.index_stock_cons_df(symbol="000300")
            return list(zip(df["品种代码"].tolist(), df["品种名称"].tolist()))

    except Exception as e:
        logger.warning("Failed to resolve stock pool via akshare: %s, using fallback", e)
        return _FALLBACK_POOL


# Small fallback pool for testing when akshare is unavailable
_FALLBACK_POOL = [
    ("600519", "贵州茅台"), ("000858", "五粮液"), ("601318", "中国平安"),
    ("600036", "招商银行"), ("000333", "美的集团"), ("600276", "恒瑞医药"),
    ("601166", "兴业银行"), ("000651", "格力电器"), ("600030", "中信证券"),
    ("601888", "中国中免"),
]


def _get_nested(data: dict, key: str) -> Any:
    """Get a value from a nested dict using dot-separated or flat key."""
    # Try flat key first
    if key in data:
        return data[key]
    # Try searching in all sub-dicts
    for _group_key, group_val in data.items():
        if isinstance(group_val, dict) and key in group_val:
            return group_val[key]
    return None


def evaluate_filters(indicators: dict, filters: list[dict]) -> bool:
    """Check if a stock's indicators pass all filter conditions."""
    for f in filters:
        field = f["field"]
        op = f["operator"]
        target = f["value"]

        actual = _get_nested(indicators, field)
        if actual is None:
            return False

        op_fn = _OPS.get(op)
        if op_fn is None:
            continue

        try:
            if not op_fn(float(actual), float(target)):
                return False
        except (TypeError, ValueError):
            # String comparison
            try:
                if not op_fn(str(actual), str(target)):
                    return False
            except Exception:
                return False

    return True


def extract_key_indicators(indicators: dict) -> dict[str, Any]:
    """Extract a small snapshot of key indicators for display in results."""
    snapshot: dict[str, Any] = {}
    keys_of_interest = [
        "pe", "pb", "market_cap", "rsi", "macd_dif", "macd_dea", "macd_hist",
        "ma5", "ma10", "ma20", "ma60", "adx",
        "wyckoff_phase", "obv_divergence",
        "turnover_premium", "main_net_flow_total",
    ]
    for key in keys_of_interest:
        val = _get_nested(indicators, key)
        if val is not None:
            snapshot[key] = val
    return snapshot
