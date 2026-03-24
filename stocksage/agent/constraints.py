"""Agent 行为边界配置。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AgentConstraints:
    """控制 SkillAgent 的行为边界。

    Attributes:
        max_iterations: ReAct 循环最大迭代次数。
        allowed_tools: 工具白名单；空列表表示不使用工具。
        budget_tokens: 总 token 预算上限（输入+输出），0 表示无限制。
        timeout_seconds: 单个 Agent 执行超时时间，0 表示无限制。
        max_tool_result_chars: 工具返回结果的最大字符数，超出截断。0 表示不截断。
    """

    max_iterations: int = 8
    allowed_tools: list[str] = field(default_factory=list)
    budget_tokens: int = 0
    timeout_seconds: int = 120
    max_tool_result_chars: int = 8000
