"""条件边函数：控制工作流分支路由。

v3.0 新增: evaluate_condition() 通用条件表达式求值器，
支持 JSONPath 访问、比较运算符和布尔组合。
"""

from __future__ import annotations

from typing import Any


def should_run_round3(state: dict) -> str:
    """协调者决策后的条件路由。

    返回 "round3" 触发 Round 3 深化辩论，返回 "judge" 直接进入决策。
    """
    r3 = state.get("round3_decision", {})
    if r3.get("need_round3", False):
        return "round3"
    return "judge"


# ============================================================
# 通用条件表达式求值器（v3.0）
# ============================================================


def _resolve_path(state: dict, path: str) -> Any:
    """根据点分隔的路径从 state 中提取值。

    Args:
        state: 工作流状态字典
        path: 点分隔路径，如 "round3_decision.need_round3"

    Returns:
        路径对应的值，路径不存在时返回 _MISSING 标记。
    """
    current: Any = state
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


class _MissingSentinel:
    """路径不存在的标记对象。"""

    def __repr__(self) -> str:
        return "<MISSING>"


_MISSING = _MissingSentinel()


# 运算符实现
_OPERATORS: dict[str, Any] = {
    "eq": lambda a, b: a == b,
    "equals": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "lt": lambda a, b: a < b,
    "gt": lambda a, b: a > b,
    "lte": lambda a, b: a <= b,
    "gte": lambda a, b: a >= b,
    "in": lambda a, b: a in b,
    "contains": lambda a, b: b in a,
}


def evaluate_condition(condition: dict, state: dict) -> bool:
    """求值条件表达式。

    支持三种格式：

    1. 简单等值判断::

        {"path": "a.b", "equals": true}

    2. 比较运算::

        {"path": "a.b", "operator": "gt", "value": 5}

    3. 布尔组合::

        {"any": [<condition>, <condition>, ...]}  # OR
        {"all": [<condition>, <condition>, ...]}  # AND

    Args:
        condition: 条件表达式字典
        state: 工作流状态字典

    Returns:
        条件是否满足。路径不存在时返回 False。
    """
    # 布尔组合: any / all
    if "any" in condition:
        sub_conditions = condition["any"]
        if not isinstance(sub_conditions, list):
            return False
        return any(evaluate_condition(sub, state) for sub in sub_conditions)

    if "all" in condition:
        sub_conditions = condition["all"]
        if not isinstance(sub_conditions, list):
            return False
        return all(evaluate_condition(sub, state) for sub in sub_conditions)

    # 需要 path
    path = condition.get("path")
    if not path:
        return False

    value = _resolve_path(state, path)
    if isinstance(value, _MissingSentinel):
        return False

    # 简单等值: {"path": "...", "equals": X}
    if "equals" in condition:
        return value == condition["equals"]

    # 运算符: {"path": "...", "operator": "gt", "value": X}
    op_name = condition.get("operator", "eq")
    op_fn = _OPERATORS.get(op_name)
    if op_fn is None:
        return False

    compare_value = condition.get("value")
    try:
        return op_fn(value, compare_value)
    except (TypeError, ValueError):
        return False
