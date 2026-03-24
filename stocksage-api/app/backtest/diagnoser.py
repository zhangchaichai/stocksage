"""Backtest diagnosis generator: LLM-based analysis of prediction accuracy."""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_DIAGNOSIS_SYSTEM = "你是一位资深量化分析师，负责复盘投资预测的准确性。请仅输出合法 JSON。"

_DIAGNOSIS_PROMPT = """\
## 复盘任务

请分析以下股票预测的准确性，找出预测正确或失误的根本原因。

## 预测信息
- 股票代码: {symbol}
- 预测方向: {predicted_direction}
- 实际方向: {actual_direction}
- 实际涨跌幅: {price_change_pct:+.2f}%
- 最大收益: {max_gain_pct:+.2f}%
- 最大回撤: {max_drawdown_pct:+.2f}%
- 回测周期: {period_days} 天
- Sharpe ratio: {sharpe_ratio}
- Sortino ratio: {sortino_ratio}
- VaR (95%): {var_95}
- Wyckoff 阶段: {wyckoff_phase}
- 方向是否正确: {direction_correct}

## 原始分析摘要
{analysis_summary}

## 输出格式

请严格输出以下 JSON 结构：
```json
{{
  "accuracy_verdict": "correct 或 partially_correct 或 incorrect",
  "score": 0.0到1.0之间的评分,
  "direction_correct": true或false,
  "magnitude_error": "overestimated 或 underestimated 或 close 或 n/a",
  "correct_insights": ["分析中正确的判断1", "判断2"],
  "missed_factors": ["遗漏的因素1", "因素2"],
  "root_cause": "预测结果的根本原因分析",
  "improvement_suggestions": [
    {{
      "type": "skill_prompt 或 skill_weight 或 data_source 或 workflow_structure",
      "target": "需要改进的skill名称或数据源",
      "priority": "high 或 medium 或 low",
      "confidence": 0.5,
      "suggestion": "具体的改进建议"
    }}
  ]
}}
```
"""


def _build_analysis_summary(analysis_snapshot: dict[str, Any] | None) -> str:
    """Build a concise analysis summary from the original snapshot."""
    if not analysis_snapshot:
        return "无分析快照"

    parts = []

    # Decision
    decision = analysis_snapshot.get("decision", {})
    if isinstance(decision, dict):
        rec = decision.get("recommendation", "N/A")
        conf = decision.get("confidence", "N/A")
        logic = decision.get("core_logic", "")
        parts.append(f"推荐: {rec} (置信度: {conf})")
        if logic:
            parts.append(f"核心逻辑: {logic[:300]}")

        # Dimension scores
        dim_scores = decision.get("dimension_scores", {})
        if isinstance(dim_scores, dict) and dim_scores:
            scores_str = ", ".join(f"{k}: {v}" for k, v in dim_scores.items())
            parts.append(f"维度评分: {scores_str}")

    # Key analysis highlights
    analysis = analysis_snapshot.get("analysis", {})
    if isinstance(analysis, dict):
        for name, result in analysis.items():
            if isinstance(result, dict):
                summary = result.get("summary", result.get("conclusion", ""))
                if summary and isinstance(summary, str):
                    parts.append(f"[{name}] {summary[:150]}")

    return "\n".join(parts) if parts else "无分析摘要"


def generate_diagnosis_sync(
    backtest_data: dict[str, Any],
    analysis_snapshot: dict[str, Any] | None,
    llm,
) -> dict[str, Any]:
    """Generate LLM-based diagnosis for a backtest result.

    Args:
        backtest_data: The backtest result fields dict.
        analysis_snapshot: The original analysis snapshot from InvestmentAction.
        llm: An LLM instance satisfying BaseLLM protocol.

    Returns:
        Parsed diagnosis dict, or error dict on failure.
    """
    analysis_summary = _build_analysis_summary(analysis_snapshot)

    prompt = _DIAGNOSIS_PROMPT.format(
        symbol=backtest_data.get("symbol", ""),
        predicted_direction=backtest_data.get("predicted_direction", "unknown"),
        actual_direction=backtest_data.get("actual_direction", "unknown"),
        price_change_pct=backtest_data.get("price_change_pct", 0),
        max_gain_pct=backtest_data.get("max_gain_pct", 0),
        max_drawdown_pct=backtest_data.get("max_drawdown_pct", 0),
        period_days=backtest_data.get("period_days", 0),
        sharpe_ratio=backtest_data.get("sharpe_ratio") or "N/A",
        sortino_ratio=backtest_data.get("sortino_ratio") or "N/A",
        var_95=backtest_data.get("var_95") or "N/A",
        wyckoff_phase=backtest_data.get("wyckoff_phase_at_action") or "N/A",
        direction_correct=backtest_data.get("direction_correct", False),
        analysis_summary=analysis_summary,
    )

    messages = [
        {"role": "system", "content": _DIAGNOSIS_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    try:
        response = llm.call(messages, temperature=0.3, max_tokens=2000)
    except Exception as e:
        logger.warning("LLM diagnosis call failed: %s", e)
        return {"error": "llm_call_failed", "detail": str(e)}

    # Parse JSON from response
    text = response.strip()
    # Strip markdown code fences
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
        logger.warning("Diagnosis JSON parse failed: %s, response: %s", e, text[:200])
        return {"error": "json_parse_failed", "raw": text[:500]}
