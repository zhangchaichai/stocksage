"""SkillLoader: 解析 .md 文件为 SkillDef。

.md 文件格式：YAML front matter（两个 --- 之间）+ Markdown 正文（作为 prompt 模板）。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from stocksage.skill_engine.models import (
    ExecutionConfig,
    InputField,
    OutputField,
    RemoteConfig,
    SkillDef,
    SkillInterface,
)


class SkillLoader:
    """从 Markdown 文件加载 Skill 定义。"""

    def load(self, path: Path) -> SkillDef:
        """解析单个 .md 文件，返回 SkillDef。"""
        content = path.read_text(encoding="utf-8")
        front_matter, prompt_template = self._split_front_matter(content)
        meta = yaml.safe_load(front_matter) or {}
        return self._build_skill_def(meta, prompt_template)

    def load_dir(self, directory: Path) -> list[SkillDef]:
        """递归加载目录下所有 .md 文件。"""
        skills = []
        for md_file in sorted(directory.rglob("*.md")):
            if md_file.name.startswith("_"):
                continue
            skills.append(self.load(md_file))
        return skills

    def _split_front_matter(self, content: str) -> tuple[str, str]:
        """分离 YAML front matter 和 Markdown 正文。"""
        content = content.strip()
        if not content.startswith("---"):
            return "", content

        # 找第二个 --- 分隔符
        end_idx = content.index("---", 3)
        front_matter = content[3:end_idx].strip()
        prompt_template = content[end_idx + 3:].strip()
        return front_matter, prompt_template

    def _build_skill_def(self, meta: dict, prompt_template: str) -> SkillDef:
        """从解析后的 YAML 元数据构建 SkillDef。"""
        interface_raw = meta.get("interface", {})
        inputs = [
            InputField(**inp) for inp in interface_raw.get("inputs", [])
        ]
        outputs = [
            OutputField(**out) for out in interface_raw.get("outputs", [])
        ]

        exec_raw = meta.get("execution", {})
        execution = ExecutionConfig(
            model=exec_raw.get("model", "deepseek-chat"),
            temperature=exec_raw.get("temperature", 0.7),
            max_tokens=exec_raw.get("max_tokens", 2000),
            timeout=exec_raw.get("timeout", 30),
            retry=exec_raw.get("retry", 2),
        )

        # A2A 远程配置 (可选)
        remote_raw = meta.get("remote")
        remote = None
        if remote_raw and isinstance(remote_raw, dict):
            remote = RemoteConfig(
                enabled=remote_raw.get("enabled", False),
                endpoint=remote_raw.get("endpoint", ""),
                protocol=remote_raw.get("protocol", "a2a"),
            )

        return SkillDef(
            name=meta.get("name", "unnamed"),
            type=meta.get("type", "agent"),
            version=meta.get("version", "1.0.0"),
            description=meta.get("description", ""),
            interface=SkillInterface(inputs=inputs, outputs=outputs),
            tools=meta.get("tools", []),
            execution=execution,
            prompt_template=prompt_template,
            remote=remote,
        )
