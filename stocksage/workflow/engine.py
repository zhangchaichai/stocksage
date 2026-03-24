"""LangGraph 工作流引擎。

工作流结构（v3.1 法庭辩论模型 + 盲点研究）：
  START → collect_data → 6 analysts (并行) → conflict_aggregator
  → bull/bear (并行) → debate R1-R2 (串行4步)
  → 5 experts (并行) → panel_coordinator
  → [conditional] Round 3 or skip → blind_spot_researcher → judge → END

Phase 1: 数据获取（ThreadPoolExecutor 并行）
Phase 2: 6 分析师并行（Send fan-out）
Phase 2.5: 矛盾汇总（串行）
Phase 3: 多空观点（Send fan-out 2）
Phase 3.5: 辩论 R1-R2（串行 4 步）
Phase 4: 5 专家并行（Send fan-out 5）
Phase 4.5: 协调者（串行）
Phase 3.6: Round 3（条件，串行 2 步）
Phase 4.6: 盲点研究员（Web 搜索 + 分析）
Phase 5: 决策法官
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from stocksage.data.fetcher import DataFetcher
from stocksage.llm.factory import create_llm
from stocksage.skill_engine.executor import SkillExecutor
from stocksage.skill_engine.registry import SkillRegistry
from stocksage.workflow.conditions import should_run_round3
from stocksage.workflow.nodes import make_skill_node
from stocksage.workflow.state import WorkflowState

logger = logging.getLogger(__name__)

ANALYST_SKILLS = [
    "technical_analyst", "fundamental_analyst", "risk_analyst",
    "sentiment_analyst", "news_analyst", "fund_flow_analyst",
]

EXPERT_SKILLS = [
    "blind_spot_detector", "consensus_analyzer", "decision_tree_builder",
    "quality_checker", "evidence_validator",
]

DEBATE_R1R2_SKILLS = [
    "debate_r1_bull_challenge", "debate_r1_bear_response",
    "debate_r2_bull_revise", "debate_r2_bear_revise",
]


class WorkflowEngine:
    """构建并运行 LangGraph 股票分析工作流（v3.1 法庭辩论 + 盲点研究模型）。"""

    def __init__(
        self,
        skills_dir: Path | None = None,
        enable_mcp: bool = True,
        memory_recall_fn: Callable[[str], dict[str, Any]] | None = None,
    ):
        self._registry = SkillRegistry()
        self._llm = create_llm("deepseek")
        self._memory_recall_fn = memory_recall_fn

        # MCP 初始化（可选，失败则降级）
        mcp_manager = None
        if enable_mcp:
            mcp_manager = self._init_mcp()

        self._fetcher = DataFetcher(mcp_manager=mcp_manager)

        # ToolBridge（可选）
        tool_bridge = None
        if mcp_manager:
            try:
                from stocksage.mcp.tool_bridge import ToolBridge
                tool_bridge = ToolBridge(mcp_manager=mcp_manager)
            except Exception:
                pass

        self._executor = SkillExecutor(self._llm, self._fetcher, tool_bridge=tool_bridge)

        skills_path = skills_dir or Path(__file__).parent.parent / "skills"
        count = self._registry.load_from_dir(skills_path)
        logger.info("已加载 %d 个 Skills", count)

        self._graph = self._build_graph()

    @staticmethod
    def _init_mcp():
        """尝试初始化 MCP 管理器，失败返回 None。"""
        try:
            from stocksage.mcp.client_manager import MCPClientManager
            return MCPClientManager()
        except Exception as e:
            logger.info("MCP 未启用（%s），使用 self-built 数据源", e)
            return None

    def _add_skill_node(self, builder: StateGraph, name: str) -> None:
        """注册 Skill 节点到 StateGraph（辅助方法）。"""
        skill = self._registry.get(name)
        if skill:
            builder.add_node(name, make_skill_node(skill, self._executor))

    def _build_graph(self):
        """构建完整 v3.1 LangGraph StateGraph。"""
        builder = StateGraph(WorkflowState)

        # === Phase 1: 数据收集 ===
        builder.add_node("collect_data", self._collect_data)

        # === Phase 2: 6 个分析师 ===
        for name in ANALYST_SKILLS:
            self._add_skill_node(builder, name)

        # === Phase 2.5: 矛盾汇总 ===
        self._add_skill_node(builder, "conflict_aggregator")

        # === Phase 3: 多空观点 ===
        self._add_skill_node(builder, "bull_advocate")
        self._add_skill_node(builder, "bear_advocate")

        # === Phase 3.5: 辩论 R1-R2 (串行) ===
        for name in DEBATE_R1R2_SKILLS:
            self._add_skill_node(builder, name)

        # === Phase 4: 5 个专家 ===
        for name in EXPERT_SKILLS:
            self._add_skill_node(builder, name)

        # === Phase 4.5: 协调者 ===
        self._add_skill_node(builder, "panel_coordinator")

        # === Phase 3.6: Round 3 (条件) ===
        self._add_skill_node(builder, "debate_r3_bull")
        self._add_skill_node(builder, "debate_r3_bear")

        # === Phase 4.6: 盲点研究员 ===
        self._add_skill_node(builder, "blind_spot_researcher")

        # === Phase 5: 法官 ===
        self._add_skill_node(builder, "judge")

        # ========== 边定义 ==========

        # START → Phase 1
        builder.add_edge(START, "collect_data")

        # Phase 1 → Phase 2 (fan-out 6 分析师)
        builder.add_conditional_edges("collect_data", self._fan_out_analysts)

        # Phase 2 → Phase 2.5 (所有分析师 → conflict_aggregator)
        for name in ANALYST_SKILLS:
            builder.add_edge(name, "conflict_aggregator")

        # Phase 2.5 → Phase 3 (fan-out bull + bear)
        builder.add_conditional_edges("conflict_aggregator", self._fan_out_bull_bear)

        # Phase 3 → Phase 3.5 (bull + bear 都完成后进入辩论)
        builder.add_edge("bull_advocate", "debate_r1_bull_challenge")
        builder.add_edge("bear_advocate", "debate_r1_bull_challenge")

        # Phase 3.5: 串行辩论 R1-R2
        builder.add_edge("debate_r1_bull_challenge", "debate_r1_bear_response")
        builder.add_edge("debate_r1_bear_response", "debate_r2_bull_revise")
        builder.add_edge("debate_r2_bull_revise", "debate_r2_bear_revise")

        # Phase 3.5 → Phase 4 (fan-out 5 专家)
        builder.add_conditional_edges("debate_r2_bear_revise", self._fan_out_experts)

        # Phase 4 → Phase 4.5 (所有专家 → coordinator)
        for name in EXPERT_SKILLS:
            builder.add_edge(name, "panel_coordinator")

        # Phase 4.5 → 条件边: Round 3 or 盲点研究
        builder.add_conditional_edges(
            "panel_coordinator",
            should_run_round3,
            {"round3": "debate_r3_bull", "judge": "blind_spot_researcher"},
        )

        # Phase 3.6: Round 3 串行 → 盲点研究
        builder.add_edge("debate_r3_bull", "debate_r3_bear")
        builder.add_edge("debate_r3_bear", "blind_spot_researcher")

        # Phase 4.6: 盲点研究 → 法官
        builder.add_edge("blind_spot_researcher", "judge")

        # Phase 5 → END
        builder.add_edge("judge", END)

        return builder.compile()

    def run(self, symbol: str, stock_name: str = "") -> dict:
        """运行完整工作流，返回最终状态。"""
        # 记忆召回（工作流启动前）
        memory_context: dict = {}
        if self._memory_recall_fn:
            try:
                memory_context = self._memory_recall_fn(symbol)
                logger.info("[Memory] 召回记忆: %d 个字段", len(memory_context))
            except Exception as e:
                logger.warning("[Memory] 召回失败: %s", e)

        initial_state: WorkflowState = {
            "meta": {"symbol": symbol, "stock_name": stock_name, "market": "cn"},
            "memory": memory_context,
            "data": {},
            "analysis": {},
            "debate": {},
            "expert_panel": {},
            "round3_decision": {},
            "decision": {},
            "errors": [],
            "current_phase": "init",
            "llm_traces": {},
        }
        return self._graph.invoke(initial_state)

    def _collect_data(self, state: WorkflowState) -> dict:
        """Phase 1: 并行获取所有数据源。"""
        symbol = state["meta"]["symbol"]
        logger.info("[Phase 1] 数据获取中: %s", symbol)
        print("  [Phase 1] 数据获取中...")

        fetch_tasks = [
            ("stock_info", self._fetcher.fetch_stock_info),
            ("price_data", self._fetcher.fetch_price_data),
            ("financial", self._fetcher.fetch_financial),
            ("quarterly", self._fetcher.fetch_quarterly),
            ("news", self._fetcher.fetch_news),
            ("market_news", self._fetcher.fetch_market_news),
            ("fund_flow", self._fetcher.fetch_fund_flow),
            ("sentiment", self._fetcher.fetch_sentiment),
            ("margin", self._fetcher.fetch_margin_data),
            ("northbound", self._fetcher.fetch_northbound_flow),
            ("balance_sheet", self._fetcher.fetch_balance_sheet),
        ]

        data: dict = {}
        errors: list = []

        with ThreadPoolExecutor(max_workers=len(fetch_tasks)) as pool:
            future_to_key = {
                pool.submit(fn, symbol): key for key, fn in fetch_tasks
            }
            for future in as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    result = future.result(timeout=30)
                    if result:
                        data[key] = result
                        logger.info("  + %s: 获取成功", key)
                        print(f"    + {key}: 已获取")
                    else:
                        errors.append(f"数据获取为空: {key}")
                        logger.warning("  - %s: 获取为空", key)
                        print(f"    - {key}: 为空")
                except Exception as e:
                    errors.append(f"数据获取失败: {key}: {e}")
                    logger.warning("  - %s: 获取失败: %s", key, e)
                    print(f"    - {key}: 失败")

        print(f"  [Phase 1] 完成: {len(data)}/{len(fetch_tasks)} 个数据源")

        # 量化指标预计算
        from stocksage.data.indicators import compute_all_indicators
        try:
            indicators = compute_all_indicators(data)
            data["indicators"] = indicators
            logger.info("  量化指标计算完成: %d 个维度", len(indicators))
            print(f"    + 量化指标: 已计算 ({len(indicators)} 个维度)")
        except Exception as e:
            logger.warning("  量化指标计算失败: %s", e)

        return {"data": data, "errors": errors, "current_phase": "data_collection"}

    @staticmethod
    def _fan_out_analysts(state: WorkflowState) -> list[Send]:
        """Phase 1 → Phase 2: fan-out 到 6 个分析师。"""
        print("  [Phase 2] 六维分析中...")
        return [Send(name, state) for name in ANALYST_SKILLS]

    @staticmethod
    def _fan_out_bull_bear(state: WorkflowState) -> list[Send]:
        """Phase 2.5 → Phase 3: fan-out 到 bull + bear。"""
        print("  [Phase 3] 多空辩论构建中...")
        return [Send("bull_advocate", state), Send("bear_advocate", state)]

    @staticmethod
    def _fan_out_experts(state: WorkflowState) -> list[Send]:
        """Phase 3.5 → Phase 4: fan-out 到 5 个专家。"""
        print("  [Phase 4] 专家评审中...")
        return [Send(name, state) for name in EXPERT_SKILLS]
