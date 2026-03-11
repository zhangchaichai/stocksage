"""SnapshotEngine: Stage-1 full-market fast filter using AkShare snapshot.

Uses ak.stock_zh_a_spot_em() to get a DataFrame with price/market-cap/PE/
turnover/vol-ratio for all ~5000 A-share stocks, then applies vectorised
pandas filtering to narrow the candidate list to ≤ max_candidates stocks
in under 5 seconds.

This is used as Stage 1 for AkShare-only strategies (e.g. dealer_wyckoff,
turn_bottom) where pywencai doesn't cover the required custom signals.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Mapping from generic field names (used in ScreenerFilter) to the column
# names returned by ak.stock_zh_a_spot_em().
_COLUMN_MAP: dict[str, str] = {
    "close":          "最新价",
    "market_cap":     "总市值",
    "pe":             "市盈率-动态",
    "turnover_rate":  "换手率",
    "vol_ratio":      "量比",
    "change_pct":     "涨跌幅",
    "amplitude":      "振幅",
    "volume":         "成交量",
    "amount":         "成交额",
    "pb":             "市净率",
    "open":           "今开",
    "high":           "最高",
    "low":            "最低",
}


class SnapshotEngine:
    """Vectorised fast-filter using AkShare full-market snapshot."""

    def fast_filter(
        self,
        filters: list[dict[str, Any]],
        max_candidates: int = 200,
    ) -> list[tuple[str, str]]:
        """Stage 1: apply *filters* to the full-market snapshot.

        Returns a list of (symbol, name) tuples with at most *max_candidates*
        entries.  Returns an empty list on any error so the caller can decide
        whether to abort or fall back.
        """
        try:
            import akshare as ak
            import pandas as pd
        except ImportError as exc:
            logger.error("SnapshotEngine requires akshare: %s", exc)
            return []

        try:
            df = ak.stock_zh_a_spot_em()
        except Exception as exc:
            logger.error("ak.stock_zh_a_spot_em() failed: %s", exc)
            return []

        if df is None or df.empty:
            logger.warning("SnapshotEngine: empty snapshot returned")
            return []

        logger.info("SnapshotEngine: snapshot has %d stocks", len(df))

        # Apply each filter with vectorised pandas operations
        mask = pd.Series([True] * len(df), index=df.index)
        for f in filters:
            field = f.get("field", "")
            op = f.get("operator", "")
            value = f.get("value")
            col = _COLUMN_MAP.get(field)
            if col is None or col not in df.columns:
                logger.debug("SnapshotEngine: unknown or missing column for field=%s", field)
                continue
            try:
                series = pd.to_numeric(df[col], errors="coerce")
                v = float(value)
                if op == "lt":
                    mask &= series < v
                elif op == "lte":
                    mask &= series <= v
                elif op == "gt":
                    mask &= series > v
                elif op == "gte":
                    mask &= series >= v
                elif op == "eq":
                    mask &= series == v
                elif op == "ne":
                    mask &= series != v
            except Exception as exc:
                logger.warning("SnapshotEngine filter %s failed: %s", field, exc)
                continue

        filtered = df[mask].head(max_candidates)
        logger.info(
            "SnapshotEngine: %d → %d candidates after filtering",
            len(df), len(filtered),
        )

        return list(
            zip(
                filtered["代码"].astype(str).tolist(),
                filtered["名称"].astype(str).tolist(),
            )
        )
