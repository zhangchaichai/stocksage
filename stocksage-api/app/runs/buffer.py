"""ResponseBuffer: 流式响应段落聚合器。

将 LLM 产生的 token 流 (skill_chunk) 聚合为逻辑段落，
给每个段落分配稳定 ID，使前端可以增量更新 UI。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class BufferEntry:
    """单个 Skill 的缓冲条目。"""

    item_id: str
    skill_name: str
    parts: list[str] = field(default_factory=list)


class ResponseBuffer:
    """流式响应段落聚合器。

    - 缓冲事件 (skill_chunk): 累积文本，保持稳定 item_id
    - 立即事件 (skill_completed, phase_changed 等): 直写 + 刷新缓冲
    """

    BUFFERED_EVENTS = frozenset({"skill_chunk"})
    IMMEDIATE_EVENTS = frozenset({
        "skill_started", "skill_completed", "skill_failed",
        "phase_changed", "run_completed", "run_failed",
    })

    def __init__(self) -> None:
        self._buffers: dict[str, BufferEntry] = {}  # key = skill_name

    def process(self, event: dict) -> list[dict]:
        """处理一个事件，返回需要推送的事件列表。

        - 缓冲事件: 累积到 buffer，返回带 item_id 的注解事件
        - 立即事件: 先 flush 该 skill 的 buffer，再返回立即事件
        - 其他事件: 原样返回
        """
        event_type = event.get("event")

        if event_type in self.IMMEDIATE_EVENTS:
            flushed = self._flush(event.get("skill_name"))
            return flushed + [event]

        if event_type in self.BUFFERED_EVENTS:
            return [self._accumulate(event)]

        return [event]

    def flush_all(self) -> list[dict]:
        """刷新所有 buffer，返回所有聚合段落事件。"""
        events: list[dict] = []
        for skill_name in list(self._buffers):
            events.extend(self._flush(skill_name))
        return events

    def _accumulate(self, event: dict) -> dict:
        """累积 chunk 到 buffer，返回带稳定 item_id 的事件。"""
        skill = event.get("skill_name", "unknown")
        if skill not in self._buffers:
            self._buffers[skill] = BufferEntry(
                item_id=str(uuid.uuid4()),
                skill_name=skill,
            )
        entry = self._buffers[skill]
        entry.parts.append(event.get("payload", ""))

        # 返回带稳定 ID 的事件（前端用 item_id 定位 DOM 元素）
        annotated = dict(event)
        annotated["item_id"] = entry.item_id
        return annotated

    def _flush(self, skill_name: str | None) -> list[dict]:
        """刷新指定 skill 的 buffer，返回聚合后的完整段落事件。"""
        if not skill_name or skill_name not in self._buffers:
            return []
        entry = self._buffers.pop(skill_name)
        if not entry.parts:
            return []
        return [{
            "event": "skill_paragraph",
            "skill_name": skill_name,
            "item_id": entry.item_id,
            "payload": "".join(entry.parts),
        }]
