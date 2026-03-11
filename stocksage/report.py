"""PDF 报告生成器：将完整分析结果（含 LLM 中间过程）输出为 PDF。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

logger = logging.getLogger(__name__)

# 中文字体路径（macOS）
_FONT_REGULAR = "/System/Library/Fonts/Supplemental/Songti.ttc"
_FONT_BOLD = "/System/Library/Fonts/STHeiti Medium.ttc"

# Skill 中文名称映射
_SKILL_NAMES = {
    "technical_analyst": "技术分析师",
    "fundamental_analyst": "基本面分析师",
    "risk_analyst": "风险管理专家",
    "sentiment_analyst": "市场情绪分析师",
    "news_analyst": "新闻分析师",
    "fund_flow_analyst": "资金流分析师",
    "conflict_aggregator": "矛盾汇总器",
    "bull_advocate": "多方辩护人",
    "bear_advocate": "空方辩护人",
    "debate_r1_bull_challenge": "辩论R1-多方质疑",
    "debate_r1_bear_response": "辩论R1-空方回应",
    "debate_r2_bull_revise": "辩论R2-多方修正",
    "debate_r2_bear_revise": "辩论R2-空方修正",
    "debate_r3_bull": "辩论R3-多方",
    "debate_r3_bear": "辩论R3-空方",
    "blind_spot_detector": "盲区检测专家",
    "consensus_analyzer": "共识分析专家",
    "decision_tree_builder": "决策树构建专家",
    "quality_checker": "质量审查专家",
    "evidence_validator": "证据验证专家",
    "panel_coordinator": "专家团协调者",
    "blind_spot_researcher": "盲点研究员",
    "judge": "综合决策法官",
}

# 各阶段包含的 skill 及输出顺序
_PHASE_SKILLS = [
    ("Phase 2: 六维分析", [
        "technical_analyst", "fundamental_analyst", "risk_analyst",
        "sentiment_analyst", "news_analyst", "fund_flow_analyst",
    ]),
    ("Phase 2.5: 矛盾汇总", ["conflict_aggregator"]),
    ("Phase 3: 多空辩论", ["bull_advocate", "bear_advocate"]),
    ("Phase 3.5: 辩论交锋", [
        "debate_r1_bull_challenge", "debate_r1_bear_response",
        "debate_r2_bull_revise", "debate_r2_bear_revise",
    ]),
    ("Phase 3.6: 第三轮辩论", ["debate_r3_bull", "debate_r3_bear"]),
    ("Phase 4: 专家评审", [
        "blind_spot_detector", "consensus_analyzer",
        "decision_tree_builder", "quality_checker", "evidence_validator",
    ]),
    ("Phase 4.5: 专家团协调", ["panel_coordinator"]),
    ("Phase 4.6: 盲点研究", ["blind_spot_researcher"]),
    ("Phase 5: 最终决策", ["judge"]),
]


class ReportPDF(FPDF):
    """支持中文的 PDF 报告。"""

    def __init__(self):
        super().__init__()
        self.add_font("songti", "", _FONT_REGULAR)
        self.add_font("heiti", "", _FONT_BOLD)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        self.set_font("heiti", size=8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, "StockSage 分析报告", align="R", new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("songti", size=8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"第 {self.page_no()} 页", align="C")

    def add_title(self, text: str):
        self.set_font("heiti", size=20)
        self.set_text_color(0, 0, 0)
        self.cell(0, 15, text, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def add_subtitle(self, text: str):
        self.set_font("heiti", size=10)
        self.set_text_color(80, 80, 80)
        self.cell(0, 8, text, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(5)

    def add_section(self, title: str):
        self.ln(5)
        self.set_font("heiti", size=14)
        self.set_text_color(30, 60, 120)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(30, 60, 120)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)

    def add_subsection(self, title: str):
        self.ln(3)
        self.set_font("heiti", size=11)
        self.set_text_color(60, 60, 60)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def add_text(self, text: str, size: int = 9):
        self.set_font("songti", size=size)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 5, text)
        self.ln(1)

    def add_key_value(self, key: str, value: str):
        self.set_font("heiti", size=9)
        self.set_text_color(60, 60, 60)
        key_w = self.get_string_width(key + "：") + 2
        self.cell(key_w, 6, key + "：")
        self.set_font("songti", size=9)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 6, str(value))
        self.ln(1)

    def add_highlight_box(self, text: str, color: tuple = (240, 248, 255)):
        self.set_fill_color(*color)
        self.set_font("heiti", size=11)
        self.set_text_color(20, 60, 100)
        x = self.get_x()
        y = self.get_y()
        self.rect(x, y, 190, 12, "F")
        self.cell(190, 12, text, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)


def _format_json_text(data) -> str:
    """将 dict/list 格式化为可读文本。"""
    if isinstance(data, str):
        return data
    try:
        return json.dumps(data, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(data)


def generate_report(result: dict, output_path: str | Path | None = None) -> Path:
    """根据工作流结果生成 PDF 报告。

    Args:
        result: WorkflowEngine.run() 返回的完整状态
        output_path: 输出路径，默认为当前目录下 report_<symbol>_<date>.pdf

    Returns:
        生成的 PDF 文件路径
    """
    meta = result.get("meta", {})
    symbol = meta.get("symbol", "unknown")
    stock_name = meta.get("stock_name", symbol)
    decision = result.get("decision", {})
    llm_traces = result.get("llm_traces", {})
    errors = result.get("errors", [])

    if output_path is None:
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(f"report_{symbol}_{date_str}.pdf")
    else:
        output_path = Path(output_path)

    pdf = ReportPDF()

    # === 封面 / 标题 ===
    pdf.add_page()
    pdf.ln(20)
    pdf.add_title(f"StockSage 分析报告")
    pdf.add_subtitle(f"{stock_name} ({symbol})")
    pdf.add_subtitle(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    pdf.ln(10)

    # === 最终决策摘要 ===
    pdf.add_section("一、最终决策摘要")

    rec = decision.get("recommendation", "N/A") if isinstance(decision, dict) else "N/A"
    conf = decision.get("confidence", "N/A") if isinstance(decision, dict) else "N/A"
    color_map = {"BUY": (220, 255, 220), "SELL": (255, 220, 220), "HOLD": (255, 255, 220)}
    box_color = color_map.get(rec, (240, 248, 255))
    pdf.add_highlight_box(f"推荐：{rec}    置信度：{conf}", color=box_color)

    # 检测决策生成失败
    if isinstance(decision, dict) and (decision.get("error") or rec == "N/A"):
        pdf.add_text("⚠ 决策生成失败")
        if err := decision.get("error"):
            pdf.add_text(f"原因: {err}")
        pdf.add_text("请重新运行分析或检查 LLM 响应。")

    if isinstance(decision, dict) and "recommendation" in decision:
        # 维度评分
        if scores := decision.get("dimension_scores"):
            pdf.add_subsection("六维方向评分 (看空-10 ~ 看多+10)")
            for dim, score in scores.items():
                pdf.add_key_value(dim, str(score))
            if ws := decision.get("weighted_score"):
                pdf.add_key_value("加权总分", str(ws))

        if cl := decision.get("core_logic"):
            pdf.add_key_value("核心逻辑", cl)
        if rw := decision.get("risk_warning"):
            pdf.add_key_value("风险提示", rw)
        if act := decision.get("action_strategy"):
            pdf.add_key_value("操作建议", act)

        if bull := decision.get("bull_factors"):
            pdf.add_subsection("看多因素")
            for f in bull:
                pdf.add_text(f"  + {f}")

        if bear := decision.get("bear_factors"):
            pdf.add_subsection("看空因素")
            for f in bear:
                pdf.add_text(f"  - {f}")

        if watch := decision.get("key_watch_points"):
            pdf.add_subsection("关注指标")
            for w in watch:
                pdf.add_text(f"  * {w}")

        if dims := decision.get("dimension_summary"):
            pdf.add_subsection("六维总结")
            for dim, summary in dims.items():
                pdf.add_key_value(dim, summary)

        if blind_spots := decision.get("blind_spot_assessment"):
            pdf.add_subsection("盲点处理评估")
            for bs in blind_spots:
                spot = bs.get("blind_spot", "")
                addressed = "已回应" if bs.get("addressed_in_debate") else "未回应"
                evidence = "有数据" if bs.get("evidence_found") else "无数据"
                evidence_summary = bs.get("evidence_summary", "")
                conclusion = bs.get("conclusion", "")
                label = f"[{addressed}|{evidence}] {spot}"
                detail = conclusion
                if evidence_summary:
                    detail = f"证据: {evidence_summary} | 结论: {conclusion}"
                pdf.add_key_value(label, detail)

    # === 数据获取概况 ===
    pdf.add_section("二、数据获取概况")
    data = result.get("data", {})
    data_sources = [
        "stock_info", "price_data", "financial", "quarterly", "news",
        "market_news", "fund_flow", "sentiment", "margin", "northbound",
        "balance_sheet",
    ]
    for src in data_sources:
        status = "已获取" if src in data and data[src] else "未获取"
        pdf.add_key_value(src, status)

    if errors:
        pdf.add_subsection("运行时错误")
        for err in errors:
            pdf.add_text(f"  ! {err}")

    # === LLM 中间过程 ===
    pdf.add_section("三、LLM 中间过程详情")

    for phase_title, skills in _PHASE_SKILLS:
        has_any = any(s in llm_traces for s in skills)
        if not has_any:
            continue

        pdf.add_subsection(phase_title)

        for skill_name in skills:
            if skill_name not in llm_traces:
                continue

            cn_name = _SKILL_NAMES.get(skill_name, skill_name)
            pdf.add_subsection(f"  {cn_name} ({skill_name})")

            raw = llm_traces[skill_name]
            text = _format_json_text(raw)
            # 截断过长的文本
            if len(text) > 3000:
                text = text[:3000] + "\n... (已截断)"
            pdf.add_text(text, size=8)

    # === 生成 PDF ===
    pdf.output(str(output_path))
    logger.info("PDF 报告已生成: %s", output_path)
    return output_path


# ============================================================
# Markdown 报告生成
# ============================================================

def generate_markdown_report(
    result: dict,
    output_path: str | Path | None = None,
) -> Path:
    """根据工作流结果生成 Markdown 报告。

    Args:
        result: WorkflowEngine.run() 返回的完整状态
        output_path: 输出路径，默认为当前目录下 report_<symbol>_<date>.md

    Returns:
        生成的 Markdown 文件路径
    """
    meta = result.get("meta", {})
    symbol = meta.get("symbol", "unknown")
    stock_name = meta.get("stock_name", symbol)
    decision = result.get("decision", {})
    llm_traces = result.get("llm_traces", {})
    errors = result.get("errors", [])
    data = result.get("data", {})

    if output_path is None:
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(f"report_{symbol}_{date_str}.md")
    else:
        output_path = Path(output_path)

    lines: list[str] = []

    def w(text: str = "") -> None:
        lines.append(text)

    # === 标题 ===
    w(f"# StockSage 分析报告 — {stock_name} ({symbol})")
    w()
    w(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    w()
    w("---")
    w()

    # === 一、最终决策摘要 ===
    w("## 一、最终决策摘要")
    w()

    rec = decision.get("recommendation", "N/A") if isinstance(decision, dict) else "N/A"
    conf = decision.get("confidence", "N/A") if isinstance(decision, dict) else "N/A"
    emoji_map = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡", "WATCH": "⚪"}
    emoji = emoji_map.get(rec, "⚪")
    w(f"**{emoji} 推荐：{rec}　　置信度：{conf}**")
    w()

    # 检测决策生成失败
    if isinstance(decision, dict) and (decision.get("error") or rec == "N/A"):
        w("> **⚠ 决策生成失败**")
        if err := decision.get("error"):
            w(f"> 原因: {err}")
        w("> 请重新运行分析或检查 LLM 响应。")
        w()

    if isinstance(decision, dict) and "recommendation" in decision:
        # 维度评分表格
        if scores := decision.get("dimension_scores"):
            w("### 六维方向评分（看空 -10 ~ 看多 +10）")
            w()
            w("| 维度 | 评分 | 方向条 |")
            w("|------|------|--------|")
            for dim, score in scores.items():
                if isinstance(score, (int, float)):
                    bar_pos = "+" * max(0, int(score))
                    bar_neg = "-" * max(0, -int(score))
                    bar = f"`{bar_neg}{bar_pos}`" if bar_neg or bar_pos else "`0`"
                else:
                    bar = str(score)
                w(f"| {dim} | {score} | {bar} |")
            if ws := decision.get("weighted_score"):
                w(f"| **加权总分** | **{ws}** | |")
            w()

        if cl := decision.get("core_logic"):
            w(f"**核心逻辑：** {cl}")
            w()
        if rw := decision.get("risk_warning"):
            w(f"**风险提示：** {rw}")
            w()
        if act := decision.get("action_strategy"):
            w(f"**操作建议：** {act}")
            w()

        if bull := decision.get("bull_factors"):
            w("### 看多因素")
            w()
            for f in bull:
                w(f"- {f}")
            w()

        if bear := decision.get("bear_factors"):
            w("### 看空因素")
            w()
            for f in bear:
                w(f"- {f}")
            w()

        if watch := decision.get("key_watch_points"):
            w("### 关注指标")
            w()
            for item in watch:
                w(f"- {item}")
            w()

        if dims := decision.get("dimension_summary"):
            w("### 六维总结")
            w()
            for dim, summary in dims.items():
                w(f"- **{dim}**：{summary}")
            w()

        if blind_spots := decision.get("blind_spot_assessment"):
            w("### 盲点处理评估")
            w()
            for bs in blind_spots:
                spot = bs.get("blind_spot", "")
                addressed = "是" if bs.get("addressed_in_debate") else "否"
                evidence = bs.get("evidence_found", False)
                evidence_summary = bs.get("evidence_summary", "")
                impact = bs.get("impact_on_decision", "")
                conclusion = bs.get("conclusion", "")
                evidence_tag = "有数据支撑" if evidence else "无直接数据"
                w(f"**[{evidence_tag}] {spot}**")
                w(f"- 辩论中已回应: {addressed}")
                if evidence_summary:
                    w(f"- 搜索证据: {evidence_summary}")
                w(f"- 影响评估: {impact}")
                w(f"- 结论: {conclusion}")
                w()
            w()
    else:
        w("```json")
        w(_format_json_text(decision))
        w("```")
        w()

    w("---")
    w()

    # === 二、数据获取概况 ===
    w("## 二、数据获取概况")
    w()
    data_sources = [
        "stock_info", "price_data", "financial", "quarterly", "news",
        "market_news", "fund_flow", "sentiment", "margin", "northbound",
        "balance_sheet",
    ]
    w("| 数据源 | 状态 |")
    w("|--------|------|")
    for src in data_sources:
        status = "已获取" if src in data and data[src] else "未获取"
        icon = "+" if status == "已获取" else "-"
        w(f"| {src} | {icon} {status} |")
    w()

    if errors:
        w("### 运行时错误")
        w()
        for err in errors:
            w(f"- {err}")
        w()

    w("---")
    w()

    # === 三、LLM 中间过程详情 ===
    w("## 三、LLM 中间过程详情")
    w()

    for phase_title, skills in _PHASE_SKILLS:
        has_any = any(s in llm_traces for s in skills)
        if not has_any:
            continue

        w(f"### {phase_title}")
        w()

        for skill_name in skills:
            if skill_name not in llm_traces:
                continue

            cn_name = _SKILL_NAMES.get(skill_name, skill_name)
            w(f"#### {cn_name}（{skill_name}）")
            w()

            raw = llm_traces[skill_name]
            text = _format_json_text(raw)

            # Markdown 中不截断，完整保留
            w("<details>")
            w(f"<summary>点击展开 {cn_name} 完整输出</summary>")
            w()
            w("```json")
            w(text)
            w("```")
            w()
            w("</details>")
            w()

    w("---")
    w()
    w("*本报告由 StockSage 多 Agent 系统自动生成，仅供参考，不构成投资建议。*")
    w()

    # === 写入文件 ===
    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Markdown 报告已生成: %s", output_path)
    return output_path
