"""AIScorer: DeepSeek-powered stock scoring and ranking.

Given a list of screener match dicts (symbol, name, indicators) and the
strategy context, calls DeepSeek to assign a 0-10 score + one-line reason
to each stock.  Falls back to raw ordering on any LLM error so the caller
always gets a usable result.

Usage (called from screener worker after Path A/B completes):

    scorer = AIScorer()
    scored = await scorer.score(matches, strategy_context="低价高成长策略")
    # scored[i] now has 'ai_score' (float) and 'ai_reason' (str) fields,
    # sorted by ai_score descending.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

logger = logging.getLogger(__name__)

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai_scorer")

# Maximum number of stocks sent to LLM in one call (to stay within token limits)
_MAX_BATCH = 20


def _build_prompt(stocks: list[dict[str, Any]], strategy_context: str) -> str:
    """Construct the scoring prompt."""
    lines = []
    for i, s in enumerate(stocks, 1):
        inds = s.get("indicators", {})
        # Select a concise subset of indicators to keep the prompt short
        summary_keys = [
            "close", "change_pct", "pe", "pb", "market_cap",
            "rsi", "macd_dif", "ma5", "ma20",
            "turnover_rate", "vol_ratio", "main_net_flow_total",
        ]
        ind_str = ", ".join(
            f"{k}={inds[k]:.2f}" if isinstance(inds.get(k), float) else f"{k}={inds.get(k)}"
            for k in summary_keys
            if k in inds
        )
        lines.append(f"{i}. {s['symbol']} {s.get('name', '')}  [{ind_str}]")

    stock_list = "\n".join(lines)
    return f"""你是一位专业的 A 股量化分析师。
以下是通过「{strategy_context}」选出的 {len(stocks)} 只股票及其关键指标：

{stock_list}

请对每只股票综合基本面、技术面、资金面打分（0-10分，10分最佳），并给出一句核心推荐理由（不超过30字）。

严格按照以下 JSON 格式输出，不要有任何其他文字：
[
  {{"symbol": "600519", "score": 8.5, "reason": "主力持续净流入，均线多头排列"}},
  ...
]"""


def _call_llm_sync(stocks: list[dict[str, Any]], strategy_context: str) -> list[dict[str, Any]]:
    """Synchronous LLM call (run in thread pool)."""
    try:
        import os
        from app.config import settings
        from stocksage.llm.factory import create_llm

        provider = settings.DEFAULT_LLM_PROVIDER or "deepseek"
        llm = create_llm(provider)
        prompt = _build_prompt(stocks, strategy_context)

        # Bypass proxy for LLM calls that might use domestic APIs
        saved = {}
        for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
            if key in os.environ:
                saved[key] = os.environ.pop(key)
        try:
            # BaseLLM interface uses call(messages), not invoke(prompt)
            content = llm.call(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4000,
            )
        finally:
            os.environ.update(saved)

        content = content.strip()

        # Extract JSON array from response
        json_match = re.search(r"\[.*\]", content, re.DOTALL)
        if not json_match:
            logger.warning("AIScorer: no JSON array in LLM response")
            return []

        scored = json.loads(json_match.group())
        return scored if isinstance(scored, list) else []

    except Exception as exc:
        logger.warning("AIScorer LLM call failed: %s", exc)
        return []


class AIScorer:
    """Score and rank screener results using DeepSeek."""

    async def score(
        self,
        matches: list[dict[str, Any]],
        strategy_context: str = "",
    ) -> list[dict[str, Any]]:
        """Assign ai_score + ai_reason to each match and sort descending.

        Args:
            matches: list of {symbol, name, indicators, ...} dicts
            strategy_context: human-readable strategy name/description for the prompt

        Returns:
            Same list with ai_score (float, 0-10) and ai_reason (str) added,
            sorted by ai_score descending.  On LLM failure falls back to
            original order with ai_score=0 and ai_reason="".
        """
        if not matches:
            return matches

        batch = matches[:_MAX_BATCH]
        loop = asyncio.get_event_loop()

        scored_raw: list[dict[str, Any]] = await loop.run_in_executor(
            _pool,
            partial(_call_llm_sync, batch, strategy_context),
        )

        # Build symbol → score/reason lookup
        score_map: dict[str, tuple[float, str]] = {}
        for item in scored_raw:
            sym = str(item.get("symbol", "")).strip()
            score = float(item.get("score", 0))
            reason = str(item.get("reason", ""))
            if sym:
                score_map[sym] = (score, reason)

        # Merge scores back into matches
        result = []
        for m in matches:
            sym = m.get("symbol", "")
            score, reason = score_map.get(sym, (0.0, ""))
            result.append({**m, "ai_score": score, "ai_reason": reason})

        # Sort by ai_score descending (stocks not in LLM batch keep score=0 at end)
        result.sort(key=lambda x: x.get("ai_score", 0), reverse=True)

        logger.info(
            "AIScorer: scored %d/%d stocks (strategy=%s)",
            len(score_map), len(matches), strategy_context,
        )
        return result
