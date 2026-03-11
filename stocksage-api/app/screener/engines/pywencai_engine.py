"""PywencaiEngine: natural-language stock screener backed by 同花顺问财.

Ported and generalised from aiagents-stock (MainForceStockSelector,
LowPriceBullSelector, SmallCapSelector, ProfitGrowthSelector).

No login required — pywencai generates an ephemeral hexin-v token via a
bundled Node.js script; the only system requirement is Node.js >= 12.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class PywencaiEngine:
    """Wrap pywencai with multi-tier fallback queries and smart column matching.

    Each strategy provides an ordered list of *queries* (most specific first,
    simplest last).  The engine tries them in sequence and returns the first
    successful result.
    """

    def query(
        self,
        queries: list[str],
        top_n: int = 20,
        sort_field: str | None = None,
        sort_ascending: bool = True,
    ) -> tuple[bool, Any, str]:
        """Execute queries with automatic fallback.

        Returns:
            (success, DataFrame | None, message)
        """
        try:
            import pandas as pd
            import pywencai
        except ImportError as exc:
            return False, None, f"pywencai not installed: {exc}"

        for i, q in enumerate(queries, 1):
            try:
                logger.info("pywencai query attempt %d/%d: %.80s…", i, len(queries), q)
                raw = self._query_no_proxy(pywencai, q)
                df = self._to_df(raw)
                if df is not None and not df.empty:
                    if sort_field:
                        df = self._smart_sort(df, sort_field, sort_ascending)
                    result_df = df.head(top_n).reset_index(drop=True)
                    msg = f"方案{i}成功，共{len(df)}只候选，返回前{len(result_df)}只"
                    logger.info("pywencai %s", msg)
                    return True, result_df, msg
                logger.warning("pywencai attempt %d returned empty result", i)
            except Exception as exc:
                logger.warning("pywencai attempt %d failed: %s", i, exc)
                if i < len(queries):
                    time.sleep(2)

        return False, None, f"所有{len(queries)}个查询方案均失败"

    # ── Proxy bypass ──────────────────────────────────────────────────────────

    @staticmethod
    def _query_no_proxy(pywencai_mod, query: str):
        """Call pywencai.get() with proxy env vars temporarily cleared."""
        import os
        saved = {}
        for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
            if key in os.environ:
                saved[key] = os.environ.pop(key)
        try:
            return pywencai_mod.get(query=query, loop=True)
        finally:
            os.environ.update(saved)

    # ── DataFrame helpers ────────────────────────────────────────────────────

    def _to_df(self, raw: Any) -> Any:
        """Normalise pywencai return value to a pandas DataFrame (or None)."""
        try:
            import pandas as pd
        except ImportError:
            return None

        if raw is None:
            return None
        if isinstance(raw, pd.DataFrame):
            return raw if not raw.empty else None
        if isinstance(raw, dict):
            try:
                df = pd.DataFrame(raw)
                return df if not df.empty else None
            except Exception:
                return None
        if isinstance(raw, list) and raw:
            try:
                df = pd.DataFrame(raw)
                return df if not df.empty else None
            except Exception:
                return None
        return None

    def _smart_find_column(self, df: Any, pattern: str) -> str | None:
        """Return the first column name that contains *pattern* (case-insensitive).

        Mimics MainForceStockSelector's column name fuzzy matching.
        """
        if df is None:
            return None
        pattern_lower = pattern.lower()
        for col in df.columns:
            if pattern_lower in str(col).lower():
                return col
        return None

    def _smart_sort(self, df: Any, field_pattern: str, ascending: bool) -> Any:
        """Sort *df* by the column best matching *field_pattern*."""
        col = self._smart_find_column(df, field_pattern)
        if col is None:
            logger.debug("sort column matching '%s' not found, skipping sort", field_pattern)
            return df
        try:
            return df.sort_values(by=col, ascending=ascending)
        except Exception as exc:
            logger.warning("sort by '%s' failed: %s", col, exc)
            return df

    def df_to_matches(self, df: Any, strategy_display_fields: list[dict]) -> list[dict]:
        """Convert a pywencai result DataFrame to screener match dicts.

        Each row becomes::

            {
                "symbol": "600519",
                "name": "贵州茅台",
                "indicators": {"净利润增长率": 12.3, ...},
            }
        """
        if df is None:
            return []
        try:
            import pandas as pd
        except ImportError:
            return []

        matches: list[dict] = []

        # Locate symbol & name columns with fuzzy matching
        symbol_col = (
            self._smart_find_column(df, "股票代码")
            or self._smart_find_column(df, "代码")
            or self._smart_find_column(df, "code")
        )
        name_col = (
            self._smart_find_column(df, "股票简称")
            or self._smart_find_column(df, "名称")
            or self._smart_find_column(df, "name")
        )

        for _, row in df.iterrows():
            symbol = str(row[symbol_col]).strip() if symbol_col else ""
            name = str(row[name_col]).strip() if name_col else ""

            # Build indicators dict from display_fields + all remaining numeric cols
            indicators: dict[str, Any] = {}

            # Preferred fields declared in the strategy YAML
            for fld in strategy_display_fields:
                raw_field = fld.get("field", "")
                label = fld.get("label", raw_field)
                col = self._smart_find_column(df, raw_field) or self._smart_find_column(df, label)
                if col and col in row.index:
                    val = row[col]
                    if val is not None and str(val) not in ("nan", "NaN", "None", ""):
                        try:
                            indicators[label] = float(val)
                        except (ValueError, TypeError):
                            indicators[label] = str(val)

            # Fill remaining numeric columns not already captured
            skip_cols = {symbol_col, name_col}
            for col in df.columns:
                if col in skip_cols:
                    continue
                col_label = str(col)
                if col_label in indicators:
                    continue
                val = row[col]
                if val is not None and str(val) not in ("nan", "NaN", "None", ""):
                    try:
                        indicators[col_label] = float(val)
                    except (ValueError, TypeError):
                        indicators[col_label] = str(val)

            if symbol:
                matches.append({"symbol": symbol, "name": name, "indicators": indicators})

        return matches
