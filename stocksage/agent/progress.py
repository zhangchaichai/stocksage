"""Agent 级进度事件系统。

在现有的节点级进度回调基础上，增加 Agent 内部的细粒度事件。
与现有 SSE/WebSocket 端点集成。

现有事件（保留）:
  - skill_started / skill_completed / skill_failed  (节点级)
  - skill_chunk  (token 级)

新增事件:
  - agent_started    → Agent 开始 ReAct 循环
  - agent_iteration  → 新一轮推理开始
  - agent_thinking   → Agent 的思考内容
  - agent_tool_call  → Agent 决定调用某工具
  - agent_tool_result → 工具返回结果
  - agent_completed  → Agent 完成分析
  - agent_asking_user → Agent 请求用户输入
  - user_context_injected → 用户补充了信息
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any


@dataclass
class AgentProgressEvent:
    """Agent 进度事件。"""

    event_type: str
    skill_name: str
    payload: dict[str, Any]

    def to_sse(self) -> str:
        """转换为 SSE 格式。"""
        data = {"skill": self.skill_name, **self.payload}
        return f"event: {self.event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def to_display(self) -> str:
        """转换为用户友好的显示文本。"""
        handlers = {
            "agent_started": self._display_started,
            "agent_iteration": self._display_iteration,
            "agent_thinking": self._display_thinking,
            "agent_tool_call": self._display_tool_call,
            "agent_tool_result": self._display_tool_result,
            "agent_completed": self._display_completed,
            "agent_asking_user": self._display_asking,
            "user_context_injected": self._display_injected,
        }
        handler = handlers.get(self.event_type)
        if handler:
            return handler()
        return f"[{self.event_type}] {self.skill_name}"

    def _display_started(self) -> str:
        tools = self.payload.get("tools", [])
        return f"[start] {self.skill_name} ({len(tools)} tools)"

    def _display_iteration(self) -> str:
        i = self.payload.get("iteration", 0)
        m = self.payload.get("max_iterations", 0)
        return f"  [iter] {i}/{m}"

    def _display_thinking(self) -> str:
        thought = self.payload.get("thought", "")
        return f"  [think] {thought}"

    def _display_tool_call(self) -> str:
        tool = self.payload.get("tool", "")
        args = self.payload.get("args", {})
        args_str = ", ".join(f"{k}={v}" for k, v in args.items())
        return f"  [call] {tool}({args_str})"

    def _display_tool_result(self) -> str:
        tool = self.payload.get("tool", "")
        length = self.payload.get("result_length", 0)
        return f"  [result] {tool} ({length} chars)"

    def _display_completed(self) -> str:
        iters = self.payload.get("iterations", 0)
        elapsed = self.payload.get("elapsed", 0)
        return f"[done] {self.skill_name} ({iters} iters, {elapsed}s)"

    def _display_asking(self) -> str:
        question = self.payload.get("question", "")
        return f"[ask] {self.skill_name}: {question}"

    def _display_injected(self) -> str:
        content = self.payload.get("content", "")
        return f"[inject] {content}"


def create_progress_bridge(
    progress_queue: asyncio.Queue[AgentProgressEvent],
    skill_name: str,
) -> "ProgressCallback":
    """创建将 Agent 事件桥接到 asyncio.Queue 的回调。

    这个回调传递给 SkillAgent.on_progress，
    Agent 的每个事件都会被推送到 queue，
    再由 RunOrchestrator 消费并推送给前端。
    """

    def callback(event_type: str, payload: dict[str, Any]) -> None:
        event = AgentProgressEvent(
            event_type=event_type,
            skill_name=skill_name,
            payload=payload,
        )
        try:
            progress_queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    return callback
