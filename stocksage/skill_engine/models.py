"""Skill 数据模型定义。

SkillDef 是 .md 文件解析后的结构化表示，包含接口、执行配置、prompt 模板等。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class InputField:
    """Skill 输入字段定义。"""
    name: str
    type: str = "string"
    required: bool = True
    source: str | None = None   # 状态路径，如 "state.data.price_data"


@dataclass(slots=True)
class OutputField:
    """Skill 输出字段定义。"""
    name: str
    type: str = "object"
    target: str | None = None   # 写入状态的路径，如 "state.analysis.technical"


@dataclass(slots=True)
class SkillInterface:
    """Skill 的 I/O 接口定义。"""
    inputs: list[InputField] = field(default_factory=list)
    outputs: list[OutputField] = field(default_factory=list)


@dataclass(slots=True)
class ExecutionConfig:
    """Skill 执行配置。"""
    model: str = "deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 2000
    timeout: int = 30
    retry: int = 2


@dataclass(slots=True)
class SkillDef:
    """Skill 完整定义，由 .md 文件解析而来。"""
    name: str
    type: str                       # "data" | "agent" | "decision"
    version: str = "1.0.0"
    description: str = ""
    interface: SkillInterface = field(default_factory=SkillInterface)
    tools: list[str] = field(default_factory=list)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    prompt_template: str = ""       # Jinja2 模板原文
