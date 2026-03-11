"""Hybrid intent recognition engine.

Rule layer (fast, no LLM cost) → LLM fallback (for ambiguous queries).
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Recognized intents
INTENTS = {
    "analyze_stock",
    "open_screener",
    "open_indicators",
    "open_backtest",
    "open_portfolio",
    "open_memory",
    "open_evolution",
    "run_workflow",
    "general_question",
}

# 6-digit stock code pattern
_STOCK_CODE_RE = re.compile(r"(?:^|\s|分析|查看|看看|指标)(\d{6})(?:\s|$|的|了|吗|呢)")

# Keyword → intent mapping
_KEYWORD_MAP: list[tuple[list[str], str]] = [
    (["选股", "筛选", "screener", "screen", "过滤"], "open_screener"),
    (["指标", "技术分析", "indicator", "technical"], "open_indicators"),
    (["回测", "backtest"], "open_backtest"),
    (["持仓", "portfolio", "仓位"], "open_portfolio"),
    (["记忆", "memory", "笔记"], "open_memory"),
    (["进化", "evolution", "策略优化"], "open_evolution"),
    (["工作流", "workflow"], "run_workflow"),
]


def recognize_intent(message: str) -> tuple[str, dict | None]:
    """Recognize intent from a user message using rules.

    Returns:
        (intent, metadata) — metadata may contain 'symbol' for stock analysis.
    """
    text = message.strip().lower()

    # Rule 1: Check for stock code
    m = _STOCK_CODE_RE.search(message)
    if m:
        symbol = m.group(1)
        # Determine if user wants indicators or full analysis
        if any(kw in text for kw in ["指标", "indicator", "技术"]):
            return "open_indicators", {"symbol": symbol}
        return "analyze_stock", {"symbol": symbol}

    # Rule 2: Keyword matching
    for keywords, intent in _KEYWORD_MAP:
        for kw in keywords:
            if kw in text:
                return intent, None

    # Rule 3: Simple stock code only (user just types "600519")
    if re.fullmatch(r"\d{6}", text.strip()):
        return "analyze_stock", {"symbol": text.strip()}

    # No match → general question
    return "general_question", None


async def recognize_intent_with_llm(message: str) -> tuple[str, dict | None]:
    """LLM-based intent recognition for ambiguous queries.

    Uses the configured LLM provider for classification.
    """
    # First try rules
    intent, metadata = recognize_intent(message)
    if intent != "general_question":
        return intent, metadata

    # LLM fallback
    try:
        from stocksage.llm.factory import create_llm
        from app.config import settings

        provider = settings.DEFAULT_LLM_PROVIDER or "deepseek"
        llm = create_llm(provider)

        prompt = f"""You are a stock analysis assistant. Classify the following user message into one of these intents:
- analyze_stock: User wants to analyze a specific stock (extract the stock symbol if present)
- open_screener: User wants to screen/filter stocks
- open_indicators: User wants to view technical indicators
- open_backtest: User wants to run backtests
- open_portfolio: User wants to view portfolio
- open_memory: User wants to view/search memory
- open_evolution: User wants to view strategy evolution
- general_question: General question not matching above

User message: {message}

Reply with ONLY the intent name. If analyze_stock, add the symbol on a second line."""

        response = llm.invoke(prompt)
        content = response.content.strip() if hasattr(response, "content") else str(response).strip()
        lines = content.split("\n")
        detected = lines[0].strip().lower()

        if detected in INTENTS:
            meta = None
            if detected == "analyze_stock" and len(lines) > 1:
                sym = re.search(r"\d{6}", lines[1])
                if sym:
                    meta = {"symbol": sym.group()}
            return detected, meta

    except Exception as e:
        logger.warning("LLM intent recognition failed: %s", e)

    return "general_question", None
