"""HTML report formatters for email notifications."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_FOOTER = '<p style="color:gray;font-size:12px;margin-top:24px">来自 StockSage 智能选股引擎</p>'

_STYLE_TABLE = (
    'border="1" cellpadding="6" '
    'style="border-collapse:collapse;font-size:14px;width:100%"'
)

_STYLE_TH = 'style="background:#f5f5f5;text-align:left"'


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _pct(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v:+.2f}%"


# ── Screener report ──────────────────────────────────────────────────────────

def format_screener_report(job: Any) -> tuple[str, str]:
    """Format a ScreenerJob into (subject, html_body).

    The job must be loaded with candidates / results populated.
    """
    strategy = job.strategy_id or "自定义"
    subject = f"📊 选股报告 — {strategy}"

    # Use AI-scored results if available, otherwise fall back to candidates
    items: list[dict] = job.results or job.candidates or []
    total = job.total_scanned or 0
    count = len(items)

    rows = []
    for i, item in enumerate(items, 1):
        symbol = item.get("symbol", item.get("code", ""))
        name = item.get("name", item.get("stock_name", ""))
        ai_score = item.get("ai_score")
        score_str = f"{ai_score}%" if ai_score is not None else "-"
        pe = item.get("pe", item.get("PE", ""))
        rsi = item.get("rsi", item.get("RSI", ""))
        change = item.get("change_pct", item.get("pct_change", None))
        change_str = _pct(change) if change is not None else "-"

        rows.append(
            f"<tr><td>{i}</td><td>{symbol}</td><td>{name}</td>"
            f"<td>{score_str}</td><td>{pe}</td><td>{rsi}</td>"
            f"<td>{change_str}</td></tr>"
        )

    rows_html = "\n".join(rows) if rows else "<tr><td colspan='7'>无符合条件的股票</td></tr>"

    html = f"""\
<h2>📊 选股报告 — {strategy}</h2>
<p>扫描 {total} 只 → 精选 <b>{count}</b> 只 | {_ts()}</p>
<table {_STYLE_TABLE}>
  <tr {_STYLE_TH}>
    <th>#</th><th>代码</th><th>名称</th><th>AI评分</th><th>PE</th><th>RSI</th><th>涨跌幅</th>
  </tr>
  {rows_html}
</table>
{_FOOTER}"""

    return subject, html


# ── Workflow run report ──────────────────────────────────────────────────────

def format_workflow_report(run: Any) -> tuple[str, str]:
    """Format a WorkflowRun into (subject, html_body)."""
    symbol = run.symbol or "unknown"
    stock_name = run.stock_name or ""
    subject = f"📈 分析报告 — {symbol} {stock_name}"

    result: dict = run.result or {}
    recommendation = result.get("recommendation", result.get("action", "N/A"))
    confidence = result.get("confidence", result.get("confidence_score", None))
    conf_str = f"{confidence}" if confidence is not None else "N/A"

    # Collect skill summaries
    skill_rows = []
    skills = result.get("skills", result.get("skill_results", {}))
    if isinstance(skills, dict):
        for name, data in skills.items():
            summary = ""
            if isinstance(data, dict):
                summary = data.get("summary", data.get("signal", str(data)[:120]))
            else:
                summary = str(data)[:120]
            skill_rows.append(f"<tr><td>{name}</td><td>{summary}</td></tr>")

    skills_html = "\n".join(skill_rows) if skill_rows else ""
    skills_table = ""
    if skills_html:
        skills_table = f"""\
<h3>技能分析摘要</h3>
<table {_STYLE_TABLE}>
  <tr {_STYLE_TH}><th>技能</th><th>结论</th></tr>
  {skills_html}
</table>"""

    reason = result.get("reason", result.get("reasoning", ""))
    reason_block = f"<p><b>分析理由：</b>{reason}</p>" if reason else ""

    html = f"""\
<h2>📈 分析报告 — {symbol} {stock_name}</h2>
<p>推荐操作: <b>{recommendation}</b> | 置信度: <b>{conf_str}</b> | {_ts()}</p>
{reason_block}
{skills_table}
{_FOOTER}"""

    return subject, html


# ── Workflow backtest report ─────────────────────────────────────────────────

def format_backtest_report(results: list[dict]) -> tuple[str, str]:
    """Format batch backtest results into (subject, html_body).

    Each dict in results should contain keys like symbol, price_change_pct,
    direction_correct, sharpe_ratio, diagnosis, etc.
    """
    total = len(results)
    correct = sum(1 for r in results if r.get("direction_correct"))
    win_rate = (correct / total * 100) if total else 0
    avg_return = (
        sum(r.get("price_change_pct", 0) or 0 for r in results) / total
        if total else 0
    )

    subject = f"📉 回测报告 — {total}笔 胜率{win_rate:.0f}%"

    rows = []
    for r in results:
        symbol = r.get("symbol", "")
        pct = _pct(r.get("price_change_pct"))
        correct_str = "✅" if r.get("direction_correct") else "❌"
        sharpe = r.get("sharpe_ratio")
        sharpe_str = f"{sharpe:.2f}" if sharpe is not None else "-"
        rows.append(
            f"<tr><td>{symbol}</td><td>{pct}</td>"
            f"<td>{correct_str}</td><td>{sharpe_str}</td></tr>"
        )

    rows_html = "\n".join(rows) if rows else "<tr><td colspan='4'>无回测记录</td></tr>"

    html = f"""\
<h2>📉 回测报告</h2>
<p>共 <b>{total}</b> 笔 | 胜率 <b>{win_rate:.1f}%</b> | 平均收益 <b>{_pct(avg_return)}</b> | {_ts()}</p>
<table {_STYLE_TABLE}>
  <tr {_STYLE_TH}>
    <th>股票</th><th>收益率</th><th>方向正确</th><th>Sharpe</th>
  </tr>
  {rows_html}
</table>
{_FOOTER}"""

    return subject, html


# ── Screener backtest report ─────────────────────────────────────────────────

def format_screener_backtest_report(result: Any) -> tuple[str, str]:
    """Format a ScreenerBacktestResult into (subject, html_body)."""
    avg_ret = _pct(result.avg_return_pct)
    win = _pct(result.win_rate * 100) if result.win_rate is not None else "N/A"
    subject = f"📋 选股回测 — {result.total_stocks}只 平均{avg_ret}"

    # Stock details table
    details: list[dict] = result.stock_details or []
    rows = []
    for d in details:
        symbol = d.get("symbol", "")
        name = d.get("name", d.get("stock_name", ""))
        ret = _pct(d.get("return_pct", d.get("price_change_pct")))
        rows.append(f"<tr><td>{symbol}</td><td>{name}</td><td>{ret}</td></tr>")

    rows_html = "\n".join(rows) if rows else "<tr><td colspan='3'>无明细</td></tr>"

    # Diagnosis
    diag = result.diagnosis or {}
    diag_text = diag.get("summary", diag.get("text", "")) if isinstance(diag, dict) else str(diag)
    diag_block = f"<h3>诊断摘要</h3><p>{diag_text}</p>" if diag_text else ""

    sharpe = result.sharpe_ratio
    sharpe_str = f"{sharpe:.2f}" if sharpe is not None else "N/A"

    html = f"""\
<h2>📋 选股回测报告</h2>
<p>共 <b>{result.total_stocks}</b> 只 | 平均收益 <b>{avg_ret}</b> | 胜率 <b>{win}</b> | Sharpe <b>{sharpe_str}</b> | {_ts()}</p>
<table {_STYLE_TABLE}>
  <tr {_STYLE_TH}>
    <th>代码</th><th>名称</th><th>收益率</th>
  </tr>
  {rows_html}
</table>
{diag_block}
{_FOOTER}"""

    return subject, html


# ── Memory forgetting report ────────────────────────────────────────────────

def format_memory_forgetting_report(result_data: dict) -> tuple[str, str]:
    """Format memory forgetting cycle results."""
    compressed = result_data.get("compressed", 0)
    archived = result_data.get("expired_anchors", 0)
    subject = f"🧹 记忆清理 — 压缩{compressed}条 归档{archived}条"

    html = f"""\
<h2>🧹 记忆清理报告</h2>
<ul>
  <li>压缩事件: <b>{compressed}</b> 条</li>
  <li>归档过期锚点: <b>{archived}</b> 条</li>
</ul>
<p>{_ts()}</p>
{_FOOTER}"""

    return subject, html


# ── Task failure report ──────────────────────────────────────────────────────

def format_task_failed(task_name: str, task_type: str, error: str) -> tuple[str, str]:
    """Format a task failure notification."""
    subject = f"⚠️ 任务失败 — {task_name}"

    html = f"""\
<h2>⚠️ 定时任务执行失败</h2>
<table {_STYLE_TABLE}>
  <tr><td><b>任务名称</b></td><td>{task_name}</td></tr>
  <tr><td><b>任务类型</b></td><td>{task_type}</td></tr>
  <tr><td><b>时间</b></td><td>{_ts()}</td></tr>
  <tr><td><b>错误信息</b></td><td style="color:red">{error}</td></tr>
</table>
<p>请检查任务配置或系统日志。</p>
{_FOOTER}"""

    return subject, html
