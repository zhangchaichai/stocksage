"""Dynamic state schema tests (Task 1.2)."""

from __future__ import annotations

import operator
from typing import Annotated, get_type_hints

from stocksage.workflow.state import (
    WorkflowState,
    create_state_class,
    merge_dict,
)


class TestMergeDict:
    def test_basic_merge(self):
        assert merge_dict({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

    def test_right_overwrites_left(self):
        assert merge_dict({"a": 1}, {"a": 2}) == {"a": 2}

    def test_empty(self):
        assert merge_dict({}, {"a": 1}) == {"a": 1}
        assert merge_dict({"a": 1}, {}) == {"a": 1}


class TestWorkflowStateBackwardCompat:
    """Ensure the fixed WorkflowState is untouched."""

    def test_has_expected_keys(self):
        hints = get_type_hints(WorkflowState, include_extras=True)
        expected_keys = {
            "meta", "data", "analysis", "debate",
            "expert_panel", "round3_decision", "decision",
            "errors", "current_phase", "llm_traces", "memory",
        }
        assert set(hints.keys()) == expected_keys


class TestCreateStateClass:
    def test_basic_dict_overwrite(self):
        schema = {"decision": {"type": "dict", "merge": "overwrite"}}
        cls = create_state_class(schema)
        hints = cls.__annotations__
        assert "decision" in hints
        # overwrite -> plain dict, no Annotated wrapper
        assert hints["decision"] is dict

    def test_deep_merge_reducer(self):
        schema = {"data": {"type": "dict", "merge": "deep_merge"}}
        cls = create_state_class(schema)
        hints = cls.__annotations__
        # Should be Annotated[dict, merge_dict]
        assert hasattr(hints["data"], "__metadata__")

    def test_append_reducer(self):
        schema = {"errors": {"type": "list", "merge": "append"}}
        cls = create_state_class(schema)
        hints = cls.__annotations__
        assert hasattr(hints["errors"], "__metadata__")

    def test_multiple_fields(self):
        schema = {
            "data": {"type": "dict", "merge": "deep_merge"},
            "errors": {"type": "list", "merge": "append"},
            "decision": {"type": "dict", "merge": "overwrite"},
            "counter": {"type": "int", "merge": "overwrite"},
        }
        cls = create_state_class(schema)
        assert cls.__required_keys__ == frozenset(schema.keys())
        assert cls.__optional_keys__ == frozenset()

    def test_default_type_is_dict(self):
        schema = {"foo": {"merge": "overwrite"}}
        cls = create_state_class(schema)
        assert cls.__annotations__["foo"] is dict

    def test_default_merge_is_overwrite(self):
        schema = {"bar": {"type": "str"}}
        cls = create_state_class(schema)
        # No Annotated wrapper -> plain str
        assert cls.__annotations__["bar"] is str

    def test_type_map_coverage(self):
        for type_name, py_type in [
            ("dict", dict), ("list", list), ("str", str),
            ("int", int), ("float", float), ("bool", bool),
        ]:
            schema = {"field": {"type": type_name, "merge": "overwrite"}}
            cls = create_state_class(schema)
            assert cls.__annotations__["field"] is py_type

    def test_unknown_type_falls_back_to_dict(self):
        schema = {"x": {"type": "unknown_type", "merge": "overwrite"}}
        cls = create_state_class(schema)
        assert cls.__annotations__["x"] is dict

    def test_empty_schema(self):
        cls = create_state_class({})
        assert cls.__annotations__ == {}
        assert cls.__required_keys__ == frozenset()
