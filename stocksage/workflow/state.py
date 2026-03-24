"""WorkflowState 定义 + reducers + 动态状态工厂。

LangGraph 通过 Annotated 类型上的 reducer 函数自动合并并行节点的输出，
确保 fan-out 场景下状态安全合并。

v3.0 新增: create_state_class() 动态状态工厂，根据工作流 YAML 的 state
声明动态生成 TypedDict + reducers。
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_dict(left: dict, right: dict) -> dict:
    """字典合并 reducer，右值覆盖左值同名 key。"""
    return {**left, **right}


# ============================================================
# 固定 WorkflowState（v2 向后兼容）
# ============================================================


class WorkflowState(TypedDict):
    """工作流全局状态。

    每个节点返回增量 dict，LangGraph 通过 reducer 自动合并。
    """

    # 元信息：股票代码、名称、市场等，初始化时设置
    meta: dict

    # 记忆上下文：工作流启动前由 recall_memory() 注入，各 Skill 只读
    memory: dict

    # Phase 1: 数据层，6 个数据 Skill 各写自己的 key（增量合并）
    data: Annotated[dict, merge_dict]

    # Phase 2: 分析层，6 个分析师各写自己的 key（增量合并）
    analysis: Annotated[dict, merge_dict]

    # Phase 3/3.5/3.6: 辩论层（bull/bear + debate rounds）
    debate: Annotated[dict, merge_dict]

    # Phase 4/4.5: 专家评审层（5 专家 + coordinator）
    expert_panel: Annotated[dict, merge_dict]

    # Phase 4.5: Round 3 决策（coordinator 写入）
    round3_decision: dict

    # Phase 5: 最终决策
    decision: dict

    # 运行时：错误追踪
    errors: Annotated[list, operator.add]

    # 当前阶段标记
    current_phase: str

    # LLM 原始响应追踪（skill_name → raw_response）
    llm_traces: Annotated[dict, merge_dict]


# ============================================================
# 动态状态工厂（v3.0）
# ============================================================

# 合并策略名 -> reducer 函数的映射
_MERGE_STRATEGIES: dict[str, Any] = {
    "deep_merge": merge_dict,
    "append": operator.add,
    # "overwrite" 不需要 reducer（LangGraph 默认行为）
}

# state schema 中 type 名 -> Python 类型
_TYPE_MAP: dict[str, type] = {
    "dict": dict,
    "list": list,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
}


def create_state_class(state_schema: dict[str, dict]) -> type:
    """根据工作流定义的 state 声明，动态创建带 reducer 的 TypedDict。

    Args:
        state_schema: 工作流 YAML 中的 ``state`` 部分，形如::

            {
                "data": {"type": "dict", "merge": "deep_merge"},
                "errors": {"type": "list", "merge": "append"},
                "decision": {"type": "dict", "merge": "overwrite"},
            }

    Returns:
        动态生成的 TypedDict 子类，可直接传给 ``StateGraph(state_class)``。
    """
    annotations: dict[str, Any] = {}

    for key, spec in state_schema.items():
        type_name = spec.get("type", "dict")
        base_type = _TYPE_MAP.get(type_name, dict)
        merge_name = spec.get("merge", "overwrite")

        reducer = _MERGE_STRATEGIES.get(merge_name)
        if reducer is not None:
            annotations[key] = Annotated[base_type, reducer]
        else:
            # overwrite 或未知策略：无 reducer
            annotations[key] = base_type

    # 动态创建 TypedDict
    ns: dict[str, Any] = {"__annotations__": annotations}
    state_cls = type("DynamicWorkflowState", (dict,), ns)
    # 标记为 TypedDict 兼容（LangGraph 通过 __annotations__ 识别）
    state_cls.__required_keys__ = frozenset(annotations.keys())
    state_cls.__optional_keys__ = frozenset()
    return state_cls
