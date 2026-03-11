"""StockSage CLI 入口。

用法:
    python -m stocksage 600519              # 分析贵州茅台（默认使用法庭辩论工作流）
    python -m stocksage 000001              # 分析平安银行
    python -m stocksage 600519 --name 贵州茅台
    python -m stocksage 600519 --workflow quick_analysis   # 快速分析模式
    python -m stocksage 600519 --workflow path/to/custom.yaml  # 自定义工作流
    python -m stocksage 600519 --legacy     # 使用旧版 WorkflowEngine（向后兼容）
    python -m stocksage 600519 --pdf        # 同时生成 PDF 报告
    python -m stocksage 600519 --no-md      # 不生成 Markdown 报告
"""

from __future__ import annotations

import argparse
import json
import logging
import time

from dotenv import load_dotenv


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def print_report(result: dict) -> None:
    """格式化输出分析报告。"""
    meta = result.get("meta", {})
    decision = result.get("decision", {})
    errors = result.get("errors", [])

    print("\n" + "=" * 60)
    print(f"  StockSage 分析报告")
    print(f"  股票: {meta.get('stock_name', '')} ({meta.get('symbol', '')})")
    print("=" * 60)

    if isinstance(decision, dict) and "recommendation" in decision:
        print(f"\n  推荐: {decision['recommendation']}")
        print(f"  置信度: {decision.get('confidence', 'N/A')}")

        if scores := decision.get("dimension_scores"):
            print(f"\n  六维评分 (看空-10 ~ 看多+10):")
            for dim, score in scores.items():
                bar = "+" * max(0, int(score)) if isinstance(score, (int, float)) else ""
                bar_neg = "-" * max(0, -int(score)) if isinstance(score, (int, float)) else ""
                print(f"    [{dim:>13}] {bar_neg}{bar} ({score})")
            if ws := decision.get("weighted_score"):
                print(f"    {'加权总分':>15}: {ws}")

        print(f"\n  核心逻辑: {decision.get('core_logic', '')}")
        print(f"  风险提示: {decision.get('risk_warning', '')}")
        print(f"  操作建议: {decision.get('action_strategy', '')}")

        if bull := decision.get("bull_factors"):
            print("\n  看多因素:")
            for f in bull:
                print(f"    + {f}")

        if bear := decision.get("bear_factors"):
            print("\n  看空因素:")
            for f in bear:
                print(f"    - {f}")

        if watch := decision.get("key_watch_points"):
            print("\n  关注指标:")
            for w in watch:
                print(f"    * {w}")

        if dims := decision.get("dimension_summary"):
            print("\n  六维总结:")
            for dim, summary in dims.items():
                print(f"    [{dim}] {summary}")

        if blind_spots := decision.get("blind_spot_assessment"):
            print("\n  盲点处理:")
            for bs in blind_spots:
                tag = "√" if bs.get("addressed_in_debate") else "!"
                evidence_tag = "有据" if bs.get("evidence_found") else "无据"
                print(f"    [{tag}|{evidence_tag}] {bs.get('blind_spot', '')}")
                if bs.get("evidence_summary"):
                    print(f"        证据: {bs.get('evidence_summary', '')}")
                print(f"        → {bs.get('conclusion', '')}")
    else:
        print("\n  ⚠ 决策生成失败")
        if isinstance(decision, dict) and decision.get("error"):
            print(f"  原因: {decision['error']}")
        print("  原始结果:")
        print(json.dumps(decision, ensure_ascii=False, indent=2))

    if errors:
        print(f"\n  警告: 执行过程中有 {len(errors)} 个错误:")
        for err in errors:
            print(f"    ! {err}")

    print("\n" + "=" * 60)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="StockSage 多 Agent 股票分析系统")
    parser.add_argument("symbol", help="股票代码，如 600519")
    parser.add_argument("--name", default="", help="股票名称（可选，自动获取）")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志输出")
    parser.add_argument("--pdf", action="store_true", help="生成 PDF 报告")
    parser.add_argument("--no-md", action="store_true", help="不生成 Markdown 报告")
    parser.add_argument("--output", default="", help="报告输出路径（默认自动生成）")
    parser.add_argument(
        "--workflow", default="courtroom_debate_v3",
        help="工作流名称或 YAML 文件路径（默认: courtroom_debate_v3）",
    )
    parser.add_argument("--legacy", action="store_true", help="使用旧版 WorkflowEngine")
    args = parser.parse_args()

    setup_logging(args.verbose)

    # 获取股票名称
    stock_name = args.name
    if not stock_name:
        from stocksage.data.fetcher import DataFetcher
        fetcher = DataFetcher()
        info = fetcher.fetch_stock_info(args.symbol)
        stock_name = info.get("股票简称", "") if info else ""
        if stock_name:
            print(f"  -> 已识别: {stock_name}")
        else:
            stock_name = args.symbol
            print(f"  -> 未能获取股票名称，使用代码: {stock_name}")

    print(f"\nStockSage 正在分析 {args.symbol} ...")
    start_time = time.time()

    if args.legacy:
        # 旧版引擎（向后兼容）
        from stocksage.workflow.engine import WorkflowEngine
        engine = WorkflowEngine()
        result = engine.run(args.symbol, stock_name)
    else:
        # v3.0 WorkflowCompiler
        result = _run_compiled_workflow(args.workflow, args.symbol, stock_name)

    elapsed = time.time() - start_time
    print(f"\n  总耗时: {elapsed:.1f}s")

    print_report(result)

    # Markdown 报告（默认生成）
    if not args.no_md:
        from stocksage.report import generate_markdown_report
        md_path = generate_markdown_report(result, args.output + ".md" if args.output else None)
        print(f"\n  Markdown 报告已生成: {md_path}")

    # PDF 报告（可选）
    if args.pdf:
        from stocksage.report import generate_report
        pdf_output = args.output + ".pdf" if args.output else None
        pdf_path = generate_report(result, pdf_output)
        print(f"  PDF 报告已生成: {pdf_path}")


def _resolve_workflow_path(workflow_name: str) -> Path:
    """解析工作流名称为 YAML 文件路径。

    支持：
    - 内置工作流名称（如 "courtroom_debate_v3"）
    - 绝对/相对文件路径（如 "path/to/custom.yaml"）
    """
    from pathlib import Path

    # 尝试作为文件路径
    path = Path(workflow_name)
    if path.exists() and path.suffix in (".yaml", ".yml"):
        return path

    # 尝试内置工作流
    builtin_dir = Path(__file__).parent / "workflows"
    for suffix in (".yaml", ".yml"):
        candidate = builtin_dir / f"{workflow_name}{suffix}"
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        f"工作流 '{workflow_name}' 未找到。"
        f"请指定内置工作流名称或 YAML 文件路径。"
        f"内置工作流目录: {builtin_dir}"
    )


def _run_compiled_workflow(workflow_name: str, symbol: str, stock_name: str) -> dict:
    """使用 WorkflowCompiler 编译并运行工作流。"""
    from pathlib import Path

    from stocksage.data.fetcher import DataFetcher
    from stocksage.llm.factory import create_llm
    from stocksage.skill_engine.executor import SkillExecutor
    from stocksage.skill_engine.registry import SkillRegistry
    from stocksage.workflow.compiler import WorkflowCompiler

    # 1. 解析工作流路径
    yaml_path = _resolve_workflow_path(workflow_name)
    print(f"  -> 工作流: {yaml_path.name}")

    # 2. 加载工作流定义
    definition = WorkflowCompiler.load(yaml_path)

    # 3. 初始化组件
    registry = SkillRegistry()
    skills_dir = Path(__file__).parent / "skills"
    registry.load_from_dir(skills_dir)

    llm = create_llm("deepseek")

    # MCP 初始化（可选）
    mcp_manager = None
    try:
        from stocksage.mcp.client_manager import MCPClientManager
        mcp_manager = MCPClientManager()
    except Exception:
        pass

    fetcher = DataFetcher(mcp_manager=mcp_manager)

    tool_bridge = None
    if mcp_manager:
        try:
            from stocksage.mcp.tool_bridge import ToolBridge
            tool_bridge = ToolBridge(mcp_manager=mcp_manager)
        except Exception:
            pass

    executor = SkillExecutor(llm, fetcher, tool_bridge=tool_bridge)

    # 4. 提供 collect_data 自定义节点
    def collect_data_fn(state: dict) -> dict:
        """Phase 1: 并行获取所有数据源（复用 WorkflowEngine 逻辑）。"""
        from stocksage.workflow.engine import WorkflowEngine
        engine_instance = WorkflowEngine.__new__(WorkflowEngine)
        engine_instance._fetcher = fetcher
        return engine_instance._collect_data(state)

    # 5. 验证
    errors = WorkflowCompiler.validate(definition, registry)
    if errors:
        print(f"  ⚠ 工作流验证警告:")
        for err in errors:
            print(f"    ! {err}")

    # 6. 编译并运行
    def _progress(node_name: str, status: str) -> None:
        if status == "started":
            print(f"    > {node_name}...")

    compiled = WorkflowCompiler.compile(
        definition, executor, registry,
        collect_data_fn=collect_data_fn,
        progress_callback=_progress,
    )

    return compiled.run(symbol, stock_name)


if __name__ == "__main__":
    main()
