"""状态工具：跨 Agent 状态读写 + 用户交互。"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from stocksage.agent.tools.base import Tool


class ReadAnalysisTool(Tool):
    """读取其他分析师的分析结果。

    后续 Agent（辩论、裁判）通过此工具读取前序分析师的结论。
    """

    def __init__(self, state_ref: dict[str, Any]):
        self._state = state_ref

    @property
    def name(self) -> str:
        return "read_analysis"

    @property
    def description(self) -> str:
        return (
            "读取指定分析师的分析结果。可用分析师: "
            "technical_analyst, fundamental_analyst, risk_analyst, "
            "sentiment_analyst, news_analyst, fund_flow_analyst, "
            "macro_analyst, valuation_analyst 等"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "analyst": {
                    "type": "string",
                    "description": "分析师名称",
                },
            },
            "required": ["analyst"],
        }

    async def execute(self, analyst: str, **kwargs: Any) -> str:
        analysis = self._state.get("analysis", {})
        result = analysis.get(analyst)
        if not result:
            available = list(analysis.keys())
            return (
                f"{analyst} 的分析结果尚不可用。"
                f"当前可用: {', '.join(available) if available else '无'}"
            )
        return json.dumps(result, ensure_ascii=False, indent=2)


class ReadDebateRecordTool(Tool):
    """读取多空辩论记录。"""

    def __init__(self, state_ref: dict[str, Any]):
        self._state = state_ref

    @property
    def name(self) -> str:
        return "read_debate_record"

    @property
    def description(self) -> str:
        return "读取多空辩论记录（多方论点、空方论点、各轮交锋）"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "round": {
                    "type": "string",
                    "description": "辩论轮次，如 'r1', 'r2', 'all'。默认 'all'",
                },
            },
        }

    async def execute(self, round: str = "all", **kwargs: Any) -> str:
        debate = self._state.get("debate", {})
        if not debate:
            return "辩论尚未开始或无记录"
        if round == "all":
            return json.dumps(debate, ensure_ascii=False, indent=2)
        round_data = debate.get(round)
        if not round_data:
            available = list(debate.keys())
            return f"辩论轮次 '{round}' 不可用。可用: {', '.join(available)}"
        return json.dumps(round_data, ensure_ascii=False, indent=2)


class ReadMemoryTool(Tool):
    """读取历史分析记忆。"""

    def __init__(self, state_ref: dict[str, Any]):
        self._state = state_ref

    @property
    def name(self) -> str:
        return "read_memory"

    @property
    def description(self) -> str:
        return "读取对该股票的历史分析记忆（如有）"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self, **kwargs: Any) -> str:
        memory = self._state.get("memory", {})
        if not memory:
            return "无历史分析记忆"
        return json.dumps(memory, ensure_ascii=False, indent=2)


class AskUserTool(Tool):
    """向用户提问并等待回答。

    当 Agent 需要用户确认或补充信息时调用。
    工作流会暂停，等待用户通过 WebSocket/API 回复。
    """

    def __init__(self, interaction_callback: Callable | None = None):
        self._callback = interaction_callback

    @property
    def name(self) -> str:
        return "ask_user"

    @property
    def description(self) -> str:
        return (
            "向用户提问并等待回答。当你需要用户确认、"
            "补充信息或在多种分析方向中选择时使用。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "要问用户的问题",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选的预定义选项",
                },
            },
            "required": ["question"],
        }

    async def execute(
        self,
        question: str,
        options: list[str] | None = None,
        **kwargs: Any,
    ) -> str:
        if not self._callback:
            return "当前不支持用户交互，请基于已有信息继续分析。"

        try:
            response = await asyncio.wait_for(
                self._callback(question, options or [], 120),
                timeout=130,
            )
        except asyncio.TimeoutError:
            return "用户未在超时时间内回复，请基于已有信息继续。"
        except Exception as e:
            return f"用户交互异常: {e!s}，请基于已有信息继续。"

        if response is None:
            return "用户未回复，请基于已有信息继续。"
        return f"用户回复: {response}"
