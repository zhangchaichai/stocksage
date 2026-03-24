"""Interaction node + remote skill config tests."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from stocksage.skill_engine.models import (
    ExecutionConfig,
    RemoteConfig,
    SkillDef,
    SkillInterface,
)
from stocksage.skill_engine.loader import SkillLoader
from stocksage.workflow.nodes import make_interaction_node


class TestInteractionNode:
    def test_no_callback_auto_continues(self):
        """Interaction node without callback returns None response."""
        node_fn = make_interaction_node(
            node_name="test_interact",
            prompt="确认？",
            options=["继续", "取消"],
        )
        result = node_fn({})
        assert result == {"interaction_response": None}

    def test_with_callback_returns_response(self):
        """Interaction node with callback returns user response."""
        async def mock_callback(prompt, options, timeout):
            return "继续"

        node_fn = make_interaction_node(
            node_name="test_interact",
            prompt="确认？",
            options=["继续", "取消"],
            interaction_callback=mock_callback,
        )
        result = node_fn({})
        assert result == {"interaction_response": "继续"}

    def test_callback_timeout_returns_none(self):
        """Callback that times out returns None."""
        async def mock_callback(prompt, options, timeout):
            return None  # simulating timeout

        node_fn = make_interaction_node(
            node_name="test_interact",
            prompt="确认？",
            timeout=0.1,
            interaction_callback=mock_callback,
        )
        result = node_fn({})
        assert result == {"interaction_response": None}

    def test_node_name_set(self):
        """Node function should have correct __name__."""
        node_fn = make_interaction_node(
            node_name="my_interaction",
            prompt="test",
        )
        assert node_fn.__name__ == "my_interaction"


class TestRemoteConfig:
    def test_skill_def_with_remote_config(self):
        """SkillDef should accept remote config."""
        skill = SkillDef(
            name="remote_analyst",
            type="agent",
            remote=RemoteConfig(
                enabled=True,
                endpoint="https://remote-agent.example.com/a2a",
                protocol="a2a",
            ),
        )
        assert skill.remote is not None
        assert skill.remote.enabled is True
        assert skill.remote.endpoint == "https://remote-agent.example.com/a2a"
        assert skill.remote.protocol == "a2a"

    def test_skill_def_without_remote_config(self):
        """SkillDef should work without remote config."""
        skill = SkillDef(name="local_analyst", type="agent")
        assert skill.remote is None

    def test_remote_skill_raises_not_implemented(self):
        """Remote skill execution should raise NotImplementedError."""
        from stocksage.skill_engine.executor import SkillExecutor

        mock_llm = MagicMock()
        mock_llm.provider_name = "test"
        fetcher = MagicMock()

        executor = SkillExecutor(mock_llm, fetcher)
        skill = SkillDef(
            name="remote_test",
            type="agent",
            remote=RemoteConfig(enabled=True, endpoint="http://test", protocol="a2a"),
            prompt_template="test",
        )

        with pytest.raises(NotImplementedError, match="远程 Skill"):
            executor.execute(skill, {"meta": {}})

    def test_disabled_remote_uses_local(self):
        """Remote config with enabled=False should use local execution."""
        from stocksage.skill_engine.executor import SkillExecutor

        mock_llm = MagicMock()
        mock_llm.provider_name = "test"
        mock_llm.call = MagicMock(return_value='{"result": "ok"}')
        fetcher = MagicMock()

        executor = SkillExecutor(mock_llm, fetcher)
        skill = SkillDef(
            name="test_analyst",
            type="agent",
            remote=RemoteConfig(enabled=False, endpoint="http://test"),
            interface=SkillInterface(),
            execution=ExecutionConfig(),
            prompt_template="分析 {{ symbol }}",
        )

        state = {"meta": {"symbol": "600519", "stock_name": "test"}, "data": {}, "analysis": {}}
        result = executor.execute(skill, state)

        # Should use local execution, not raise
        mock_llm.call.assert_called_once()


class TestLoaderRemoteConfig:
    def test_loader_parses_remote_config(self, tmp_path):
        """SkillLoader should parse remote config from YAML front matter."""
        md_content = """---
name: remote_analyst
type: agent
remote:
  enabled: true
  endpoint: https://remote-agent.example.com/a2a
  protocol: a2a
execution:
  model: gpt-4o
  temperature: 0.5
---
分析 {{ symbol }}
"""
        skill_file = tmp_path / "remote_analyst.md"
        skill_file.write_text(md_content, encoding="utf-8")

        loader = SkillLoader()
        skill = loader.load(skill_file)

        assert skill.name == "remote_analyst"
        assert skill.remote is not None
        assert skill.remote.enabled is True
        assert skill.remote.endpoint == "https://remote-agent.example.com/a2a"
        assert skill.remote.protocol == "a2a"

    def test_loader_no_remote_config(self, tmp_path):
        """SkillLoader should handle missing remote config."""
        md_content = """---
name: local_analyst
type: agent
---
分析 {{ symbol }}
"""
        skill_file = tmp_path / "local_analyst.md"
        skill_file.write_text(md_content, encoding="utf-8")

        loader = SkillLoader()
        skill = loader.load(skill_file)

        assert skill.name == "local_analyst"
        assert skill.remote is None


class TestCompilerInteractionNode:
    def test_compiler_parses_interaction_node(self):
        """WorkflowCompiler should parse interaction nodes from definition."""
        from stocksage.workflow.compiler import WorkflowCompiler

        raw = {
            "name": "test_workflow",
            "nodes": [
                {"name": "analyst", "skill": "technical_analyst"},
                {
                    "name": "user_check",
                    "type": "interaction",
                    "config": {
                        "prompt": "确认继续分析？",
                        "options": ["继续", "取消"],
                        "timeout": 60,
                    },
                },
            ],
            "edges": [],
        }

        definition = WorkflowCompiler.load(raw)

        assert len(definition.nodes) == 2
        interaction_node = definition.nodes[1]
        assert interaction_node.name == "user_check"
        assert interaction_node.type == "interaction"
        assert interaction_node.config is not None
        assert interaction_node.config["prompt"] == "确认继续分析？"
        assert interaction_node.config["options"] == ["继续", "取消"]
        assert interaction_node.config["timeout"] == 60
