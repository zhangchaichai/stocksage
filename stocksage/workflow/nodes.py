"""LangGraph 工作流节点函数。

每个节点函数是 SkillExecutor.execute() 的薄包装，
接收 WorkflowState，返回增量状态更新。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stocksage.skill_engine.executor import SkillExecutor
    from stocksage.skill_engine.models import SkillDef
    from stocksage.workflow.state import WorkflowState

logger = logging.getLogger(__name__)


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
