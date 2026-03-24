"""Agent 节点工厂：创建 LangGraph 节点，内部运行 SkillAgent ReAct 循环。

通过 WorkflowCompiler.compile() 的 node_factory 参数注入，
不需要修改 WorkflowCompiler 的任何代码。

Usage:
    factory = make_agent_node_factory(llm_adapter, fetcher, mode="standard")
    compiled = WorkflowCompiler.compile(
        definition, executor, registry,
        node_factory=factory,
    )
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from stocksage.agent.constraints import AgentConstraints
from stocksage.agent.progress import create_progress_bridge
from stocksage.agent.skill_agent import SkillAgent
from stocksage.agent.tools.factory import build_tool_registry
from stocksage.agent.tools.presets import get_allowed_tools
from stocksage.data.fetcher import DataFetcher
from stocksage.skill_engine.models import SkillDef

logger = logging.getLogger(__name__)

# Mode → default constraints mapping
_MODE_CONSTRAINTS: dict[str, AgentConstraints] = {
    "quick": AgentConstraints(max_iterations=1, allowed_tools=[], timeout_seconds=30),
    "standard": AgentConstraints(max_iterations=8, timeout_seconds=120),
    "deep": AgentConstraints(max_iterations=15, budget_tokens=80_000, timeout_seconds=300),
}


def make_agent_node_factory(
    llm_adapter: Any,
    fetcher: DataFetcher,
    *,
    mode: str = "standard",
    progress_queue: asyncio.Queue | None = None,
    interaction_callback: Callable | None = None,
    web_search_config: Any = None,
    web_proxy: str | None = None,
) -> Callable[[SkillDef], Callable]:
    """返回一个 node_factory 函数，供 WorkflowCompiler.compile() 使用。

    Args:
        llm_adapter: LLM 适配器 (LiteLLMAdapter / NanobotLLMAdapter / BaseLLMToolCallingAdapter)
        fetcher: DataFetcher 实例
        mode: 运行模式 ("quick" | "standard" | "deep")
        progress_queue: Agent 进度事件队列
        interaction_callback: 用户交互回调工厂
        web_search_config: Web 搜索配置
        web_proxy: HTTP 代理

    Returns:
        node_factory 函数: (SkillDef) -> (state: dict) -> dict
    """
    base_constraints = _MODE_CONSTRAINTS.get(mode, _MODE_CONSTRAINTS["standard"])

    def node_factory(skill: SkillDef) -> Callable[[dict[str, Any]], dict[str, Any]]:
        """为单个 Skill 创建 Agent 节点函数。"""

        # Determine constraints: skill-specific > mode default
        if skill.constraints:
            constraints = AgentConstraints(
                max_iterations=skill.constraints.max_iterations,
                allowed_tools=skill.constraints.allowed_tools or get_allowed_tools(skill.name),
                budget_tokens=skill.constraints.budget_tokens,
                timeout_seconds=skill.constraints.timeout,
            )
        elif mode == "quick":
            # Quick mode: no tools, single iteration — degrades to Template behavior
            constraints = AgentConstraints(
                max_iterations=1,
                allowed_tools=[],
                timeout_seconds=30,
            )
        else:
            # Standard / deep mode: use preset tools for this role
            constraints = AgentConstraints(
                max_iterations=base_constraints.max_iterations,
                allowed_tools=get_allowed_tools(skill.name),
                budget_tokens=base_constraints.budget_tokens,
                timeout_seconds=base_constraints.timeout_seconds,
            )

        def agent_node(state: dict[str, Any]) -> dict[str, Any]:
            """LangGraph 节点函数。"""

            # Build tool registry for this agent
            tool_registry = build_tool_registry(
                skill_name=skill.name,
                state=state,
                fetcher=fetcher,
                skill_constraints=constraints,
                web_search_config=web_search_config,
                web_proxy=web_proxy,
                interaction_callback=interaction_callback,
            )

            # Build progress callback
            on_progress = None
            if progress_queue is not None:
                on_progress = create_progress_bridge(progress_queue, skill.name)

            # Create agent
            agent = SkillAgent(
                skill=skill,
                llm=llm_adapter,
                tool_registry=tool_registry,
                constraints=constraints,
                on_progress=on_progress,
                interaction_callback=interaction_callback,
            )

            # Run ReAct loop
            # LangGraph nodes may be called from sync context;
            # we need to handle both sync and async cases
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # Already in async context — create a new thread to run
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(_run_in_new_loop, agent, state)
                    return future.result(timeout=constraints.timeout_seconds + 10)
            else:
                # No running loop — create one
                return asyncio.run(agent.execute(state))

        agent_node.__name__ = skill.name
        return agent_node

    return node_factory


def _run_in_new_loop(agent: SkillAgent, state: dict[str, Any]) -> dict[str, Any]:
    """在新的事件循环中运行 agent.execute()。"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(agent.execute(state))
    finally:
        loop.close()
