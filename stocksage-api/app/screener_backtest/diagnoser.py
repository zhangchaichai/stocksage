"""LLM-based diagnosis for screener backtest results.

Analyzes the quality of stock selection by evaluating:
- Overall selection accuracy (win rate, avg return)
- Individual stock performance patterns
- Strategy strengths and weaknesses
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_SCREENER_DIAGNOSIS_SYSTEM = "你是一位资深量化策略分析师，负责评估选股策略的有效性。请仅输出合法 JSON。"

_SCREENER_DIAGNOSIS_PROMPT = """\
## 选股策略回测诊断

请分析以下选股策略回测结果，评估策略的有效性并给出改进建议。

## 回测概况
- 策略ID: {strategy_id}
- 回测周期: {period_days} 天
- 选出股票数: {total_stocks}
- 平均收益率: {avg_return_pct}%
- 胜率: {win_rate}%
- 最大单只收益: {max_gain_pct}%
- 最大单只亏损: {max_loss_pct}%
- Sharpe ratio: {sharpe_ratio}

## 个股表现明细（前10只）
{stock_details_text}

## 输出格式

请严格输出以下 JSON 结构：
```json
{{
  "overall_verdict": "effective 或 marginal 或 ineffective",
  "score": 0.0到1.0之间的评分,
  "strengths": ["策略优势1", "优势2"],
  "weaknesses": ["策略劣势1", "劣势2"],
  "best_picks": ["表现最好的股票及原因"],
  "worst_picks": ["表现最差的股票及原因"],
  "root_cause": "策略表现的根本原因分析",
  "improvement_suggestions": [
    {{
      "type": "filter_adjustment 或 timing_improvement 或 risk_control 或 pool_change",
      "target": "需要改进的方面",
      "priority": "high 或 medium 或 low",
      "confidence": 0.5,
      "suggestion": "具体的改进建议"
    }}
  ]
}}
```
"""


def _format_stock_details(details: list[dict], limit: int = 10) -> str:
    """Format stock details for the prompt."""
    sorted_details = sorted(
        details,
        key=lambda d: d.get("price_change_pct") or 0,
        reverse=True,
    )
    lines = []
    for d in sorted_details[:limit]:
        symbol = d.get("symbol", "?")
        name = d.get("name", "?")
        pct = d.get("price_change_pct")
        entry = d.get("entry_price")
        current = d.get("current_price")
        max_g = d.get("max_gain_pct")
        max_d = d.get("max_drawdown_pct")
        pct_str = f"{pct:+.2f}%" if pct is not None else "N/A"
        lines.append(
            f"- {symbol} {name}: 收益{pct_str}, "
            f"入场价{entry}, 当前价{current}, "
            f"最高{max_g}%, 最低{max_d}%"
        )
    return "\n".join(lines) if lines else "无个股数据"


def generate_screener_diagnosis_sync(
    result_data: dict[str, Any],
    strategy_id: str | None,
    llm,
) -> dict[str, Any]:
    """Generate LLM diagnosis for screener backtest results.

    Args:
        result_data: Output from execute_screener_backtest_sync.
        strategy_id: The strategy ID used for screening.
        llm: An LLM instance satisfying BaseLLM protocol.

    Returns:
        Parsed diagnosis dict, or error dict on failure.
    """
    stock_details = result_data.get("stock_details", [])
    stock_details_text = _format_stock_details(stock_details)

    prompt = _SCREENER_DIAGNOSIS_PROMPT.format(
        strategy_id=strategy_id or "custom",
        period_days=result_data.get("period_days", "N/A"),
        total_stocks=result_data.get("total_stocks", 0),
        avg_return_pct=result_data.get("avg_return_pct") or "N/A",
        win_rate=result_data.get("win_rate") or "N/A",
        max_gain_pct=result_data.get("max_gain_pct") or "N/A",
        max_loss_pct=result_data.get("max_loss_pct") or "N/A",
        sharpe_ratio=result_data.get("sharpe_ratio") or "N/A",
        stock_details_text=stock_details_text,
    )

    messages = [
        {"role": "system", "content": _SCREENER_DIAGNOSIS_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    try:
        response = llm.call(messages, temperature=0.3, max_tokens=2000)
    except Exception as e:
        logger.warning("Screener diagnosis LLM call failed: %s", e)
        return {"error": "llm_call_failed", "detail": str(e)}

    # Parse JSON
    text = response.strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()

    try:
        result = json.loads(text)
        if not isinstance(result, dict):
            return {"error": "unexpected_type", "raw": text[:500]}
        return result
    except json.JSONDecodeError as e:
        logger.warning("Screener diagnosis JSON parse failed: %s", e)
        return {"error": "json_parse_failed", "raw": text[:500]}
