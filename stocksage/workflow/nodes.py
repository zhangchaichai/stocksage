"""LangGraph 工作流节点函数。

每个节点函数是 SkillExecutor.execute() 的薄包装，
接收 WorkflowState，返回增量状态更新。

v2: 新增 make_streaming_skill_node() 支持 token 级流式 + per-skill 模型路由。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stocksage.skill_engine.executor import SkillExecutor
    from stocksage.skill_engine.models import SkillDef
    from stocksage.workflow.state import WorkflowState

logger = logging.getLogger(__name__)

# LLM 类 Skill 类型集合（与 executor.py 一致）
_LLM_SKILL_TYPES = frozenset({"agent", "decision", "debate", "expert", "coordinator", "researcher"})


def make_skill_node(skill: SkillDef, executor: SkillExecutor):
    """为 Skill 创建一个 LangGraph 节点函数。"""
    def node_fn(state: WorkflowState) -> dict:
        try:
            result = executor.execute(skill, state)
            return result
        except Exception as e:
            logger.error("Skill %s 执行失败: %s", skill.name, e)
            return {"errors": [f"{skill.name}: {e}"]}
    node_fn.__name__ = skill.name
    return node_fn


def make_streaming_skill_node(
    skill: SkillDef,
    executor: SkillExecutor,
    factory: Any | None = None,
    streaming_queue: asyncio.Queue | None = None,
):
    """为 Skill 创建支持流式输出 + per-skill 模型路由的节点函数。

    Args:
        skill: Skill 定义。
        executor: SkillExecutor 实例。
        factory: ModelFactory 实例，用于 per-skill 模型路由。
        streaming_queue: asyncio.Queue，用于从同步线程推送 (skill_name, chunk) 给异步消费端。

    Returns:
        LangGraph 节点函数。
    """

    def node_fn(state: WorkflowState) -> dict:
        try:
            # Per-skill model routing
            skill_executor = executor
            if factory:
                try:
                    from stocksage.llm.factory import ProviderUnavailableError
                    skill_llm = factory.create_model_for_skill(skill.name)
                    skill_executor = executor.with_llm(skill_llm)
                    logger.info(
                        "[ModelRouting] %s → %s",
                        skill.name, skill_llm.provider_name,
                    )
                except ProviderUnavailableError:
                    # Skill 配置为 none，使用默认 executor
                    pass
                except Exception as e:
                    logger.warning(
                        "[ModelRouting] %s fallback to default: %s",
                        skill.name, e,
                    )

            # 对于 LLM 类 skill，尝试流式执行
            if skill.type in _LLM_SKILL_TYPES and streaming_queue is not None:
                # 在新的事件循环中运行异步流式执行
                # （因为 LangGraph 节点在线程池中同步运行）
                def on_chunk_sync(chunk: str) -> None:
                    """同步回调：将 chunk 放入线程安全 queue。"""
                    try:
                        streaming_queue.put_nowait((skill.name, chunk))
                    except Exception:
                        pass

                async def _run_streaming() -> dict:
                    async def on_chunk(chunk: str) -> None:
                        on_chunk_sync(chunk)

                    return await skill_executor.execute_streaming(
                        skill, state, on_chunk=on_chunk,
                    )

                # 创建新的事件循环在线程中运行异步代码
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(_run_streaming())
                finally:
                    loop.close()
                return result
            else:
                return skill_executor.execute(skill, state)

        except Exception as e:
            logger.error("Skill %s 执行失败: %s", skill.name, e)
            return {"errors": [f"{skill.name}: {e}"]}

    node_fn.__name__ = skill.name
    return node_fn


def make_interaction_node(
    node_name: str,
    prompt: str,
    options: list[str] | None = None,
    timeout: float = 120.0,
    interaction_callback: Any = None,
):
    """创建交互节点：暂停工作流等待用户输入。

    交互节点通过 interaction_callback 发起交互请求，
    等待用户通过 REST API 投递响应后继续执行。

    Args:
        node_name: 节点名称。
        prompt: 展示给用户的提示文本。
        options: 可选的预定义选项列表。
        timeout: 超时秒数，超时后自动继续 (response=None)。
        interaction_callback: ``async (prompt, options, timeout) -> str|None``

    Returns:
        LangGraph 节点函数。
    """

    def node_fn(state: WorkflowState) -> dict:
        if interaction_callback is None:
            logger.warning("Interaction node '%s' has no callback, auto-continuing", node_name)
            return {"interaction_response": None}

        # Run async callback in new event loop (LangGraph runs nodes synchronously)
        loop = asyncio.new_event_loop()
        try:
            response = loop.run_until_complete(
                interaction_callback(prompt, options or [], timeout)
            )
        finally:
            loop.close()

        return {"interaction_response": response}

    node_fn.__name__ = node_name
    return node_fn
