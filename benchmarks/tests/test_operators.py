import random

import pytest

from benchmarks.operators import ALL_OPERATORS, apply_all, derive_seed
from traceeval.metrics.trajectory_judge import validate_forbidden_tools, validate_system_constraints, validate_trajectory


def _gate1_passes(case, trace):
    traj = validate_trajectory(case.expected_tool_calls, trace.executed_tools, case.trajectory_mode)
    constraints = validate_system_constraints(trace, case)
    forbidden = validate_forbidden_tools(trace.executed_tools, case)
    codes = [d.code for d in (traj.reason_details + constraints.reason_details + forbidden.reason_details)]
    return traj.passed and constraints.passed and forbidden.passed, codes


@pytest.mark.parametrize("operator_name,_", ALL_OPERATORS, ids=[name for name, _ in ALL_OPERATORS])
def test_operator_deterministic_under_seed(operator_name, _, in_order_scenario):
    rng1 = random.Random(derive_seed(42, in_order_scenario.id, operator_name))
    rng2 = random.Random(derive_seed(42, in_order_scenario.id, operator_name))
    func = dict(ALL_OPERATORS)[operator_name]
    r1 = func(in_order_scenario, rng1)
    r2 = func(in_order_scenario, rng2)
    assert r1.model_dump_json() == r2.model_dump_json()


@pytest.mark.parametrize("operator_name,func", ALL_OPERATORS, ids=[name for name, _ in ALL_OPERATORS])
def test_gate1_fault_operators_actually_break_gate1(operator_name, func, in_order_scenario, any_order_scenario):
    """For every applicable gate1_fault result, confirm the mutation actually causes gate 1
    to fail with the operator's predicted FailureCode - proves the operator's hand-reasoned
    ground truth is correct, without using validate_trajectory to derive that ground truth."""
    for scenario in (in_order_scenario, any_order_scenario):
        rng = random.Random(derive_seed(1, scenario.id, operator_name))
        result = func(scenario, rng)
        if not result.applicable or result.category != "gate1_fault":
            continue
        passed, codes = _gate1_passes(result.mutated_case, result.mutated_trace)
        assert passed is False, f"{operator_name} on {scenario.id} did not break gate 1"
        assert result.expected_code in codes, (
            f"{operator_name} on {scenario.id}: expected {result.expected_code}, got {codes}"
        )


@pytest.mark.parametrize("operator_name,func", ALL_OPERATORS, ids=[name for name, _ in ALL_OPERATORS])
def test_benign_gate1_operators_still_pass_gate1(operator_name, func, in_order_scenario, any_order_scenario):
    for scenario in (in_order_scenario, any_order_scenario):
        rng = random.Random(derive_seed(1, scenario.id, operator_name))
        result = func(scenario, rng)
        if not result.applicable or result.category != "benign" or result.expected_gate != "gate1":
            continue
        passed, codes = _gate1_passes(result.mutated_case, result.mutated_trace)
        assert passed is True, f"{operator_name} on {scenario.id} was expected to stay benign but broke gate 1: {codes}"


def test_swapped_order_inapplicable_under_any_order_routes_to_benign(any_order_scenario):
    fault_func = dict(ALL_OPERATORS)["swapped_order"]
    rng = random.Random(1)
    result = fault_func(any_order_scenario, rng)
    assert result.applicable is False
    assert "ANY_ORDER" in result.inapplicable_reason

    # reorder_under_any_order requires a scenario-declared independent_call_groups (see
    # test_reorder_under_any_order_requires_independent_call_groups below); the
    # any_order_scenario fixture doesn't declare one, so it's inapplicable here too - not
    # "routes to benign and always succeeds."
    benign_func = dict(ALL_OPERATORS)["reorder_under_any_order"]
    rng2 = random.Random(1)
    no_groups_scenario = any_order_scenario.model_copy(deep=True)
    no_groups_scenario.independent_call_groups = None
    benign_result = benign_func(no_groups_scenario, rng2)
    assert benign_result.applicable is False
    assert "independent_call_groups" in benign_result.inapplicable_reason


def test_duplicated_step_inapplicable_under_non_exact(in_order_scenario, any_order_scenario):
    func = dict(ALL_OPERATORS)["duplicated_step"]
    for scenario in (in_order_scenario, any_order_scenario):
        rng = random.Random(1)
        result = func(scenario, rng)
        assert result.applicable is False
        assert "EXACT" in result.inapplicable_reason or "allowed" in result.inapplicable_reason


def test_hallucinated_action_inapplicable_when_soft_tool_is_expected(in_order_scenario):
    # Sanity check on the Scenario-level guard: soft_action_tool must never be in
    # expected_tool_calls (the model validator in benchmarks/models.py already enforces
    # this at load time), so the operator's own applicability check is a second line of
    # defense, not the only one.
    expected_names = {tc.tool_name for tc in in_order_scenario.case.expected_tool_calls}
    for variant in in_order_scenario.gate2_variants:
        if variant.soft_action_tool:
            assert variant.soft_action_tool not in expected_names


def test_apply_all_covers_every_registered_operator(in_order_scenario):
    results = apply_all(in_order_scenario, seed=0)
    operator_names = {r.operator for r in results}
    assert operator_names == {name for name, _ in ALL_OPERATORS}


# --- regex_conforming_variable_value: final_output consistency fix ---


def _scenario_with_token_in_final_output():
    # _conforming_alt_value only recognizes the sess_[a-f0-9]{N} and URL-prefix pattern
    # shapes - use one of those, not an arbitrary pattern, so the operator is applicable.
    from benchmarks.models import Scenario
    from traceeval.core.schema import AgentTrace, EDDTestCase, ExpectedToolCall, ToolCall

    return Scenario(
        id="synthetic_token", domain="refunds",
        case=EDDTestCase(
            case_id="c1", input_prompt="p",
            expected_tool_calls=[ExpectedToolCall(
                tool_name="check_token", args={"token": "^sess_[a-f0-9]{4}$"},
                arg_match_mode="EXACT", field_overrides={"token": "REGEX"},
            )],
            rubric=["Confirms the check was performed."],
        ),
        trace=AgentTrace(
            session_id="s", triggered_skills=[],
            executed_tools=[ToolCall(tool_name="check_token", args={"token": "sess_ab12"})],
            final_output="I verified this using token sess_ab12 and it checked out.",
            total_token_cost_usd=0.01,
        ),
    )


def test_regex_conforming_variable_value_replaces_old_value_in_final_output():
    scenario = _scenario_with_token_in_final_output()
    func = dict(ALL_OPERATORS)["regex_conforming_variable_value"]
    rng = random.Random(1)
    result = func(scenario, rng)
    assert result.applicable is True
    new_token = result.mutated_trace.executed_tools[0].args["token"]
    assert new_token != "sess_ab12"
    assert "sess_ab12" not in result.mutated_trace.final_output
    assert new_token in result.mutated_trace.final_output
    assert "updated to match" in result.label


def test_regex_conforming_variable_value_notes_when_final_output_unaffected(in_order_scenario):
    # refund_001's clean final_output never mentions the session token literal, so the
    # replacement is a no-op there - confirm the label says so rather than silently omitting it.
    func = dict(ALL_OPERATORS)["regex_conforming_variable_value"]
    rng = random.Random(1)
    result = func(in_order_scenario, rng)
    assert result.applicable is True
    assert "unchanged (old value not present)" in result.label


# --- reorder_under_any_order: independent_call_groups ---


def test_reorder_under_any_order_requires_independent_call_groups():
    from benchmarks.models import Scenario
    from traceeval.core.schema import AgentTrace, EDDTestCase, ExpectedToolCall, ToolCall, TrajectoryMode

    scenario = Scenario(
        id="synthetic_no_groups", domain="refunds",
        case=EDDTestCase(
            case_id="c1", input_prompt="p",
            expected_tool_calls=[
                ExpectedToolCall(tool_name="a", args={}), ExpectedToolCall(tool_name="b", args={}),
            ],
            trajectory_mode=TrajectoryMode.ANY_ORDER, rubric=["r"],
        ),
        trace=AgentTrace(
            session_id="s", triggered_skills=[],
            executed_tools=[ToolCall(tool_name="a", args={}), ToolCall(tool_name="b", args={})],
            final_output="done", total_token_cost_usd=0.01,
        ),
        # independent_call_groups intentionally omitted
    )
    func = dict(ALL_OPERATORS)["reorder_under_any_order"]
    result = func(scenario, random.Random(1))
    assert result.applicable is False
    assert "independent_call_groups" in result.inapplicable_reason


def test_reorder_under_any_order_only_shuffles_within_declared_group():
    from benchmarks.models import Scenario
    from traceeval.core.schema import AgentTrace, EDDTestCase, ExpectedToolCall, ToolCall, TrajectoryMode

    # "verify" must always come first (a real dependency); "a" and "b" are independent of
    # each other and declared as such - only they may be reordered.
    scenario = Scenario(
        id="synthetic_groups", domain="refunds",
        case=EDDTestCase(
            case_id="c1", input_prompt="p",
            expected_tool_calls=[
                ExpectedToolCall(tool_name="verify", args={}),
                ExpectedToolCall(tool_name="a", args={}),
                ExpectedToolCall(tool_name="b", args={}),
            ],
            trajectory_mode=TrajectoryMode.ANY_ORDER, rubric=["r"],
        ),
        trace=AgentTrace(
            session_id="s", triggered_skills=[],
            executed_tools=[
                ToolCall(tool_name="verify", args={}), ToolCall(tool_name="a", args={}), ToolCall(tool_name="b", args={}),
            ],
            final_output="done", total_token_cost_usd=0.01,
        ),
        independent_call_groups=[["a", "b"]],
    )
    func = dict(ALL_OPERATORS)["reorder_under_any_order"]
    result = func(scenario, random.Random(1))
    assert result.applicable is True
    names = [tc.tool_name for tc in result.mutated_trace.executed_tools]
    assert names[0] == "verify"  # never moved - not in any declared group
    assert set(names[1:]) == {"a", "b"}  # only the declared group's members swapped
    assert names != ["verify", "a", "b"]  # order genuinely changed
