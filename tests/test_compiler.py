"""WorkflowCompiler tests (Task 1.6)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import yaml
import pytest
from langgraph.types import Send

from stocksage.skill_engine.models import (
    ExecutionConfig,
    OutputField,
    SkillDef,
    SkillInterface,
)
from stocksage.skill_engine.registry import SkillRegistry
from stocksage.workflow.compiler import (
    CompiledWorkflow,
    EdgeDef,
    NodeDef,
    WorkflowCompiler,
    WorkflowDefinition,
    _build_initial_state,
    _make_fan_out_fn,
    _make_condition_fn,
)


# ============================================================
# Helpers
# ============================================================


def _make_registry(*skill_names: str) -> SkillRegistry:
    """Create a SkillRegistry with mock skills."""
    registry = SkillRegistry()
    for name in skill_names:
        skill = SkillDef(
            name=name,
            type="agent",
            interface=SkillInterface(
                outputs=[OutputField(name="result", target=f"state.analysis.{name}")]
            ),
            execution=ExecutionConfig(model="test"),
            prompt_template="Test {{ symbol }}",
        )
        registry._skills[name] = skill
    return registry


def _make_mock_executor(response: dict | None = None) -> MagicMock:
    """Create a mock SkillExecutor."""
    executor = MagicMock()
    executor.execute.return_value = response or {"analysis": {"test": {"score": 8}}}
    return executor


def _simple_workflow_dict() -> dict:
    """A minimal 3-node workflow definition dict."""
    return {
        "name": "simple_test",
        "version": "1.0.0",
        "description": "Test workflow",
        "nodes": [
            {"name": "analyst_a", "skill": "analyst_a"},
            {"name": "analyst_b", "skill": "analyst_b"},
            {"name": "judge", "skill": "judge"},
        ],
        "edges": [
            {"source": "START", "target": ["analyst_a", "analyst_b"], "type": "fan_out"},
            {"source": "analyst_a", "target": "judge", "type": "fan_in"},
            {"source": "analyst_b", "target": "judge", "type": "fan_in"},
            {"source": "judge", "target": "END", "type": "serial"},
        ],
    }


# ============================================================
# WorkflowCompiler.load tests
# ============================================================


class TestLoad:
    def test_load_from_dict(self):
        raw = _simple_workflow_dict()
        defn = WorkflowCompiler.load(raw)
        assert defn.name == "simple_test"
        assert len(defn.nodes) == 3
        assert len(defn.edges) == 4

    def test_load_nodes_parsed(self):
        raw = _simple_workflow_dict()
        defn = WorkflowCompiler.load(raw)
        names = {n.name for n in defn.nodes}
        assert names == {"analyst_a", "analyst_b", "judge"}

    def test_load_edges_parsed(self):
        raw = _simple_workflow_dict()
        defn = WorkflowCompiler.load(raw)
        fan_out_edges = [e for e in defn.edges if e.type == "fan_out"]
        assert len(fan_out_edges) == 1
        assert fan_out_edges[0].target == ["analyst_a", "analyst_b"]

    def test_load_with_state_schema(self):
        raw = {
            "name": "with_state",
            "state": {
                "data": {"type": "dict", "merge": "deep_merge"},
                "errors": {"type": "list", "merge": "append"},
            },
            "nodes": [],
            "edges": [],
        }
        defn = WorkflowCompiler.load(raw)
        assert defn.state is not None
        assert "data" in defn.state

    def test_load_from_yaml_string(self, tmp_path):
        yaml_content = """
name: yaml_test
version: "1.0.0"
nodes:
  - name: node_a
    skill: node_a
edges:
  - source: START
    target: node_a
    type: serial
  - source: node_a
    target: END
    type: serial
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_content)
        defn = WorkflowCompiler.load(yaml_file)
        assert defn.name == "yaml_test"
        assert len(defn.nodes) == 1

    def test_load_invalid_type_raises(self):
        with pytest.raises((ValueError, yaml.YAMLError)):
            WorkflowCompiler.load("- [unclosed")


# ============================================================
# WorkflowCompiler.validate tests
# ============================================================


class TestValidate:
    def test_valid_workflow(self):
        raw = _simple_workflow_dict()
        defn = WorkflowCompiler.load(raw)
        registry = _make_registry("analyst_a", "analyst_b", "judge")
        errors = WorkflowCompiler.validate(defn, registry)
        assert errors == []

    def test_missing_skill(self):
        raw = _simple_workflow_dict()
        defn = WorkflowCompiler.load(raw)
        registry = _make_registry("analyst_a")  # Missing analyst_b and judge
        errors = WorkflowCompiler.validate(defn, registry)
        assert any("analyst_b" in e for e in errors)
        assert any("judge" in e for e in errors)

    def test_orphan_node(self):
        raw = {
            "name": "orphan",
            "nodes": [
                {"name": "node_a", "skill": "node_a"},
                {"name": "orphan_node", "skill": "orphan_node"},
            ],
            "edges": [
                {"source": "START", "target": "node_a", "type": "serial"},
                {"source": "node_a", "target": "END", "type": "serial"},
            ],
        }
        defn = WorkflowCompiler.load(raw)
        registry = _make_registry("node_a", "orphan_node")
        errors = WorkflowCompiler.validate(defn, registry)
        assert any("不可达" in e for e in errors)

    def test_no_end_edge(self):
        raw = {
            "name": "no_end",
            "nodes": [{"name": "node_a", "skill": "node_a"}],
            "edges": [
                {"source": "START", "target": "node_a", "type": "serial"},
            ],
        }
        defn = WorkflowCompiler.load(raw)
        registry = _make_registry("node_a")
        errors = WorkflowCompiler.validate(defn, registry)
        assert any("END" in e for e in errors)

    def test_invalid_edge_source(self):
        raw = {
            "name": "bad_edge",
            "nodes": [{"name": "node_a", "skill": "node_a"}],
            "edges": [
                {"source": "START", "target": "node_a", "type": "serial"},
                {"source": "nonexistent", "target": "END", "type": "serial"},
            ],
        }
        defn = WorkflowCompiler.load(raw)
        registry = _make_registry("node_a")
        errors = WorkflowCompiler.validate(defn, registry)
        assert any("nonexistent" in e for e in errors)


# ============================================================
# WorkflowCompiler.compile tests
# ============================================================


class TestCompile:
    def test_compile_simple_serial(self):
        """Test a simple A → B → END serial workflow compiles."""
        raw = {
            "name": "serial_test",
            "nodes": [
                {"name": "step_a", "skill": "step_a"},
                {"name": "step_b", "skill": "step_b"},
            ],
            "edges": [
                {"source": "START", "target": "step_a", "type": "serial"},
                {"source": "step_a", "target": "step_b", "type": "serial"},
                {"source": "step_b", "target": "END", "type": "serial"},
            ],
        }
        defn = WorkflowCompiler.load(raw)
        registry = _make_registry("step_a", "step_b")
        executor = _make_mock_executor()

        compiled = WorkflowCompiler.compile(defn, executor, registry)
        assert isinstance(compiled, CompiledWorkflow)
        assert compiled.name == "serial_test"

    def test_compile_fan_out_fan_in(self):
        """Test fan_out and fan_in edges compile correctly."""
        raw = _simple_workflow_dict()
        defn = WorkflowCompiler.load(raw)
        registry = _make_registry("analyst_a", "analyst_b", "judge")
        executor = _make_mock_executor()

        compiled = WorkflowCompiler.compile(defn, executor, registry)
        assert isinstance(compiled, CompiledWorkflow)

    def test_compile_conditional(self):
        """Test conditional edge compiles correctly."""
        raw = {
            "name": "conditional_test",
            "nodes": [
                {"name": "coordinator", "skill": "coordinator"},
                {"name": "round3", "skill": "round3"},
                {"name": "judge", "skill": "judge"},
            ],
            "edges": [
                {"source": "START", "target": "coordinator", "type": "serial"},
                {
                    "source": "coordinator",
                    "target": "round3",
                    "type": "conditional",
                    "condition": {"path": "round3_decision.need_round3", "equals": True},
                    "path_map": {"round3": "round3", "judge": "judge"},
                },
                {"source": "round3", "target": "judge", "type": "serial"},
                {"source": "judge", "target": "END", "type": "serial"},
            ],
        }
        defn = WorkflowCompiler.load(raw)
        registry = _make_registry("coordinator", "round3", "judge")
        executor = _make_mock_executor()

        compiled = WorkflowCompiler.compile(defn, executor, registry)
        assert isinstance(compiled, CompiledWorkflow)

    def test_compile_with_custom_state(self):
        """Test compilation with dynamic state schema."""
        raw = {
            "name": "custom_state",
            "state": {
                "data": {"type": "dict", "merge": "deep_merge"},
                "result": {"type": "dict", "merge": "overwrite"},
            },
            "nodes": [{"name": "step_a", "skill": "step_a"}],
            "edges": [
                {"source": "START", "target": "step_a", "type": "serial"},
                {"source": "step_a", "target": "END", "type": "serial"},
            ],
        }
        defn = WorkflowCompiler.load(raw)
        registry = _make_registry("step_a")
        executor = _make_mock_executor()

        compiled = WorkflowCompiler.compile(defn, executor, registry)
        assert compiled.initial_state_template["data"] == {}
        assert compiled.initial_state_template["result"] == {}


# ============================================================
# Helper function tests
# ============================================================


class TestHelperFunctions:
    def test_fan_out_fn(self):
        fn = _make_fan_out_fn(["a", "b", "c"])
        state = {"meta": {"symbol": "600519"}}
        sends = fn(state)
        assert len(sends) == 3
        assert all(isinstance(s, Send) for s in sends)

    def test_condition_fn_true(self):
        condition = {"path": "flag", "equals": True}
        path_map = {"yes": "node_a", "no": "node_b"}
        fn = _make_condition_fn(condition, path_map)
        assert fn({"flag": True}) == "yes"

    def test_condition_fn_false(self):
        condition = {"path": "flag", "equals": True}
        path_map = {"yes": "node_a", "no": "node_b"}
        fn = _make_condition_fn(condition, path_map)
        assert fn({"flag": False}) == "no"

    def test_build_initial_state_default(self):
        defn = WorkflowDefinition(name="test")
        from stocksage.workflow.state import WorkflowState
        template = _build_initial_state(defn, WorkflowState)
        assert "meta" in template
        assert "data" in template
        assert "errors" in template
        assert isinstance(template["errors"], list)

    def test_build_initial_state_custom(self):
        defn = WorkflowDefinition(
            name="test",
            state={
                "data": {"type": "dict", "merge": "deep_merge"},
                "errors": {"type": "list", "merge": "append"},
                "counter": {"type": "int", "merge": "overwrite"},
                "name": {"type": "str", "merge": "overwrite"},
            },
        )
        template = _build_initial_state(defn, dict)
        assert template["data"] == {}
        assert template["errors"] == []
        assert template["counter"] == 0
        assert template["name"] == ""

    def test_progress_callback_called(self):
        """Test that progress_callback is triggered during compilation."""
        raw = {
            "name": "progress_test",
            "nodes": [{"name": "step_a", "skill": "step_a"}],
            "edges": [
                {"source": "START", "target": "step_a", "type": "serial"},
                {"source": "step_a", "target": "END", "type": "serial"},
            ],
        }
        defn = WorkflowCompiler.load(raw)
        registry = _make_registry("step_a")
        executor = _make_mock_executor({"analysis": {"step_a": {"ok": True}}})

        progress_events = []
        compiled = WorkflowCompiler.compile(
            defn, executor, registry,
            progress_callback=lambda name, status: progress_events.append((name, status)),
        )
        # Run the compiled workflow
        result = compiled.run("600519", "测试股票")
        assert len(progress_events) == 2  # started + completed
        assert progress_events[0] == ("step_a", "started")
        assert progress_events[1] == ("step_a", "completed")
