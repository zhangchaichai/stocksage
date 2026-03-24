"""用户交互中间件：管理 Agent 与用户之间的实时交互。

支持两种交互模式：
1. Agent 主动请求：通过 AskUserTool 向用户提问
2. 用户主动补充：通过 inject_context API 注入信息
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class InteractionRequest:
    """用户交互请求。"""

    question: str
    options: list[str] = field(default_factory=list)
    _response_future: asyncio.Future[str | None] = field(
        default=None, repr=False, init=False,
    )
    _loop: asyncio.AbstractEventLoop | None = field(
        default=None, repr=False, init=False,
    )

    def __post_init__(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        self._loop = loop
        self._response_future = loop.create_future()

    async def wait_for_response(self, timeout: float = 120.0) -> str | None:
        """等待用户回复。"""
        if self._response_future is None:
            return None
        try:
            return await asyncio.wait_for(self._response_future, timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def set_response(self, response: str) -> None:
        """设置用户回复（线程安全）。"""
        if self._response_future and not self._response_future.done():
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(
                    self._response_future.set_result, response,
                )
            else:
                self._response_future.set_result(response)


class InteractionManager:
    """管理运行中的用户交互请求。"""

    def __init__(self) -> None:
        self._pending: dict[str, InteractionRequest] = {}  # run_id:skill -> request

    def register(
        self,
        run_id: str,
        skill_name: str,
        request: InteractionRequest,
    ) -> None:
        """注册一个交互请求。"""
        key = f"{run_id}:{skill_name}"
        self._pending[key] = request
        logger.info("交互请求注册: %s — %s", key, request.question)

    def respond(self, run_id: str, skill_name: str, response: str) -> bool:
        """回复一个交互请求。"""
        key = f"{run_id}:{skill_name}"
        request = self._pending.pop(key, None)
        if request is None:
            logger.warning("未找到交互请求: %s", key)
            return False
        request.set_response(response)
        return True

    def get_pending(self, run_id: str) -> dict[str, InteractionRequest]:
        """获取某个 run 的所有待处理交互请求。"""
        prefix = f"{run_id}:"
        return {
            k.split(":", 1)[1]: v
            for k, v in self._pending.items()
            if k.startswith(prefix)
        }

    def cancel_all(self, run_id: str) -> int:
        """取消某个 run 的所有交互请求。"""
        prefix = f"{run_id}:"
        to_remove = [k for k in self._pending if k.startswith(prefix)]
        for k in to_remove:
            req = self._pending.pop(k)
            if req._response_future and not req._response_future.done():
                req._response_future.set_result(None)
        return len(to_remove)


def make_interaction_callback(
    interaction_manager: InteractionManager,
    run_id: str,
    skill_name: str,
    progress_queue: asyncio.Queue | None = None,
) -> Any:
    """创建 AskUserTool 可调用的交互回调。"""

    async def callback(
        question: str,
        options: list[str],
        timeout: float = 120.0,
    ) -> str | None:
        request = InteractionRequest(question=question, options=options)
        interaction_manager.register(run_id, skill_name, request)

        # Emit event for frontend
        if progress_queue:
            from stocksage.agent.progress import AgentProgressEvent

            event = AgentProgressEvent(
                event_type="agent_asking_user",
                skill_name=skill_name,
                payload={"question": question, "options": options},
            )
            try:
                progress_queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

        return await request.wait_for_response(timeout=timeout)

    return callback
