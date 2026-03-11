"""Condition expression evaluator tests (Task 1.3)."""

from __future__ import annotations

from stocksage.workflow.conditions import (
    evaluate_condition,
    should_run_round3,
    _resolve_path,
    _MissingSentinel,
    _MISSING,
)


class TestShouldRunRound3BackwardCompat:
    """Ensure existing function is untouched."""

    def test_returns_round3(self):
        state = {"round3_decision": {"need_round3": True}}
        assert should_run_round3(state) == "round3"

    def test_returns_judge(self):
        state = {"round3_decision": {"need_round3": False}}
        assert should_run_round3(state) == "judge"

    def test_missing_key(self):
        assert should_run_round3({}) == "judge"


class TestResolvePath:
    def test_simple_key(self):
        assert _resolve_path({"a": 1}, "a") == 1

    def test_nested_path(self):
        state = {"a": {"b": {"c": 42}}}
        assert _resolve_path(state, "a.b.c") == 42

    def test_missing_returns_sentinel(self):
        result = _resolve_path({}, "x.y.z")
        assert isinstance(result, _MissingSentinel)

    def test_partial_missing(self):
        state = {"a": {"b": 1}}
        result = _resolve_path(state, "a.c")
        assert isinstance(result, _MissingSentinel)

    def test_non_dict_intermediate(self):
        state = {"a": "string_value"}
        result = _resolve_path(state, "a.b")
        assert isinstance(result, _MissingSentinel)


class TestEvaluateConditionSimpleEquals:
    def test_equals_true(self):
        cond = {"path": "a.b", "equals": True}
        state = {"a": {"b": True}}
        assert evaluate_condition(cond, state) is True

    def test_equals_false(self):
        cond = {"path": "a.b", "equals": True}
        state = {"a": {"b": False}}
        assert evaluate_condition(cond, state) is False

    def test_equals_string(self):
        cond = {"path": "status", "equals": "ready"}
        state = {"status": "ready"}
        assert evaluate_condition(cond, state) is True

    def test_equals_number(self):
        cond = {"path": "count", "equals": 42}
        state = {"count": 42}
        assert evaluate_condition(cond, state) is True

    def test_missing_path_returns_false(self):
        cond = {"path": "x.y.z", "equals": True}
        assert evaluate_condition(cond, {}) is False


class TestEvaluateConditionOperators:
    def test_eq(self):
        cond = {"path": "x", "operator": "eq", "value": 10}
        assert evaluate_condition(cond, {"x": 10}) is True
        assert evaluate_condition(cond, {"x": 11}) is False

    def test_ne(self):
        cond = {"path": "x", "operator": "ne", "value": 10}
        assert evaluate_condition(cond, {"x": 11}) is True
        assert evaluate_condition(cond, {"x": 10}) is False

    def test_lt(self):
        cond = {"path": "x", "operator": "lt", "value": 10}
        assert evaluate_condition(cond, {"x": 5}) is True
        assert evaluate_condition(cond, {"x": 10}) is False

    def test_gt(self):
        cond = {"path": "x", "operator": "gt", "value": 5}
        assert evaluate_condition(cond, {"x": 10}) is True
        assert evaluate_condition(cond, {"x": 5}) is False

    def test_lte(self):
        cond = {"path": "x", "operator": "lte", "value": 10}
        assert evaluate_condition(cond, {"x": 10}) is True
        assert evaluate_condition(cond, {"x": 11}) is False

    def test_gte(self):
        cond = {"path": "x", "operator": "gte", "value": 10}
        assert evaluate_condition(cond, {"x": 10}) is True
        assert evaluate_condition(cond, {"x": 9}) is False

    def test_in_operator(self):
        cond = {"path": "x", "operator": "in", "value": [1, 2, 3]}
        assert evaluate_condition(cond, {"x": 2}) is True
        assert evaluate_condition(cond, {"x": 5}) is False

    def test_contains_operator(self):
        cond = {"path": "x", "operator": "contains", "value": "hello"}
        assert evaluate_condition(cond, {"x": "say hello world"}) is True
        assert evaluate_condition(cond, {"x": "goodbye"}) is False

    def test_unknown_operator(self):
        cond = {"path": "x", "operator": "xor", "value": 1}
        assert evaluate_condition(cond, {"x": 1}) is False

    def test_default_operator_is_eq(self):
        cond = {"path": "x", "value": 10}
        assert evaluate_condition(cond, {"x": 10}) is True

    def test_type_error_returns_false(self):
        cond = {"path": "x", "operator": "gt", "value": 5}
        assert evaluate_condition(cond, {"x": "not_a_number"}) is False


class TestEvaluateConditionBooleanCombos:
    def test_any_true(self):
        cond = {
            "any": [
                {"path": "a", "equals": False},
                {"path": "b", "equals": True},
            ]
        }
        state = {"a": False, "b": True}
        assert evaluate_condition(cond, state) is True

    def test_any_false(self):
        cond = {
            "any": [
                {"path": "a", "equals": True},
                {"path": "b", "equals": True},
            ]
        }
        state = {"a": False, "b": False}
        assert evaluate_condition(cond, state) is False

    def test_all_true(self):
        cond = {
            "all": [
                {"path": "a", "equals": 1},
                {"path": "b", "equals": 2},
            ]
        }
        state = {"a": 1, "b": 2}
        assert evaluate_condition(cond, state) is True

    def test_all_false(self):
        cond = {
            "all": [
                {"path": "a", "equals": 1},
                {"path": "b", "equals": 2},
            ]
        }
        state = {"a": 1, "b": 99}
        assert evaluate_condition(cond, state) is False

    def test_nested_boolean(self):
        cond = {
            "all": [
                {"path": "x", "operator": "gt", "value": 0},
                {
                    "any": [
                        {"path": "y", "equals": "a"},
                        {"path": "y", "equals": "b"},
                    ]
                },
            ]
        }
        state = {"x": 5, "y": "b"}
        assert evaluate_condition(cond, state) is True

        state2 = {"x": 5, "y": "c"}
        assert evaluate_condition(cond, state2) is False

    def test_any_not_list_returns_false(self):
        assert evaluate_condition({"any": "not_a_list"}, {}) is False

    def test_all_not_list_returns_false(self):
        assert evaluate_condition({"all": "not_a_list"}, {}) is False


class TestEvaluateConditionEdgeCases:
    def test_no_path_returns_false(self):
        assert evaluate_condition({}, {}) is False

    def test_empty_path_returns_false(self):
        assert evaluate_condition({"path": "", "equals": True}, {}) is False

    def test_none_value_in_state(self):
        cond = {"path": "x", "equals": None}
        assert evaluate_condition(cond, {"x": None}) is True

    def test_zero_value_in_state(self):
        cond = {"path": "x", "equals": 0}
        assert evaluate_condition(cond, {"x": 0}) is True
