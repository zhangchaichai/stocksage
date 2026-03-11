"""SkillRegistry: Skill 注册与发现。"""

from __future__ import annotations

from pathlib import Path

from stocksage.skill_engine.loader import SkillLoader
from stocksage.skill_engine.models import SkillDef


class SkillRegistry:
    """Skill 注册表，按名称索引 SkillDef。"""

    def __init__(self):
        self._skills: dict[str, SkillDef] = {}
        self._loader = SkillLoader()

    def load_from_dir(self, directory: Path) -> int:
        """从目录加载所有 Skill，返回加载数量。"""
        skills = self._loader.load_dir(directory)
        for skill in skills:
            self._skills[skill.name] = skill
        return len(skills)

    def get(self, name: str) -> SkillDef | None:
        """按名称获取 Skill 定义。"""
        return self._skills.get(name)

    def list_names(self) -> list[str]:
        """列出所有已注册的 Skill 名称。"""
        return list(self._skills.keys())

    def list_by_type(self, skill_type: str) -> list[SkillDef]:
        """按类型过滤 Skill。"""
        return [s for s in self._skills.values() if s.type == skill_type]
