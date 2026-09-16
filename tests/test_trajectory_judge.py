# tests/test_trajectory_judge.py
"""Tests for the trajectory judge metric module."""

import pytest
from pydantic import ValidationError
from unittest.mock import AsyncMock, patch, MagicMock

from traceeval.core.schema import (
    TrajectoryMode,
    ToolCall,
    ExpectedToolCall,
    ArgMatchMode,
    FailureCode,
    EDDTestCase,
    AgentTrace,
    EvaluationDimensionScore,
)
from traceeval.metrics.trajectory_judge import (
    validate_trajectory,
    validate_system_constraints,
    validate_forbidden_tools,
    evaluate_dimensions,
    run_evaluation,
)

# Sample Tool Calls
tool_a = ToolCall(tool_name="get_weather", args={"city": "San Francisco"})
tool_b = ToolCall(tool_name="get_time", args={"timezone": "PST"})
tool_c = ToolCall(tool_name="get_weather", args={"city": "New York"})


def test_validate_trajectory_exact():
    # Matching
    assert validate_trajectory([tool_a, tool_b], [tool_a, tool_b], TrajectoryMode.EXACT).passed is True
    # Different order
    assert validate_trajectory([tool_a, tool_b], [tool_b, tool_a], TrajectoryMode.EXACT).passed is False
    # Different length
    assert validate_trajectory([tool_a, tool_b], [tool_a], TrajectoryMode.EXACT).passed is False
    # Empty
    assert validate_trajectory([], [], TrajectoryMode.EXACT).passed is True
    assert validate_trajectory([], [tool_a], TrajectoryMode.EXACT).passed is False


def test_validate_trajectory_in_order():
    # Subsequence match
    assert validate_trajectory([tool_a, tool_b], [tool_a, tool_c, tool_b], TrajectoryMode.IN_ORDER).passed is True
    # Wrong relative order
    assert validate_trajectory([tool_a, tool_b], [tool_b, tool_a], TrajectoryMode.IN_ORDER).passed is False
    # Missing element
    assert validate_trajectory([tool_a, tool_b], [tool_a, tool_c], TrajectoryMode.IN_ORDER).passed is False
    # Empty expected
    assert validate_trajectory([], [tool_a, tool_b], TrajectoryMode.IN_ORDER).passed is True


def test_validate_trajectory_any_order():
    # Out of order matches
    assert validate_trajectory([tool_a, tool_b], [tool_b, tool_a], TrajectoryMode.ANY_ORDER).passed is True
    # Multiplicity handled correctly
    assert validate_trajectory([tool_a, tool_a], [tool_b, tool_a, tool_a], TrajectoryMode.ANY_ORDER).passed is True
    assert validate_trajectory([tool_a, tool_a], [tool_a], TrajectoryMode.ANY_ORDER).passed is False
    # Missing expected element
    assert validate_trajectory([tool_a, tool_b], [tool_a, tool_c], TrajectoryMode.ANY_ORDER).passed is False


def test_validate_system_constraints():
    case = EDDTestCase(
        case_id="case_1",
        input_prompt="Test prompt",
        expected_skill="weather_skill",
        expected_tool_calls=[tool_a],
        trajectory_mode=TrajectoryMode.IN_ORDER,
        rubric=["polite", "helpful"]
    )

    # Happy path
    trace_ok = AgentTrace(
        session_id="session_1",
        triggered_skills=["weather_skill"],
        executed_tools=[tool_a],
        final_output="Weather is nice.",
        total_token_cost_usd=0.05
    )
    assert validate_system_constraints(trace_ok, case).passed is True

    # Cost too high
    trace_expensive = AgentTrace(
        session_id="session_1",
        triggered_skills=["weather_skill"],
        executed_tools=[tool_a],
        final_output="Weather is nice.",
        total_token_cost_usd=0.15
    )
    assert validate_system_constraints(trace_expensive, case, max_cost=0.10).passed is False

    # Required skill missing
    trace_wrong_skill = AgentTrace(
        session_id="session_1",
        triggered_skills=["time_skill"],
        executed_tools=[tool_a],
        final_output="Weather is nice.",
        total_token_cost_usd=0.05
    )
    assert validate_system_constraints(trace_wrong_skill, case).passed is False

    # Optional expected skill not provided in case, but present in trace
    case_no_skill = EDDTestCase(
        case_id="case_2",
        input_prompt="Test prompt",
        expected_skill=None,
        expected_tool_calls=[],
        trajectory_mode=TrajectoryMode.IN_ORDER,
        rubric=["polite"]
    )
    assert validate_system_constraints(trace_wrong_skill, case_no_skill).passed is True


# --- Reason string tests ---

def test_validate_trajectory_exact_reasons():
    # Length mismatch
    r = validate_trajectory([tool_a, tool_b], [tool_a], TrajectoryMode.EXACT)
    assert r.passed is False
    assert r.reasons == ["expected 2 tool calls, got 1"]

    # Empty → non-empty
    r = validate_trajectory([], [tool_a], TrajectoryMode.EXACT)
    assert r.reasons == ["expected 0 tool calls, got 1"]

    # Step mismatch (same length)
    r = validate_trajectory([tool_a, tool_b], [tool_a, tool_c], TrajectoryMode.EXACT)
    assert r.passed is False
    assert len(r.reasons) == 1
    assert "step 1" in r.reasons[0]
    assert "get_time" in r.reasons[0]
    assert "get_weather" in r.reasons[0]

    # Passing — no reasons
    r = validate_trajectory([tool_a], [tool_a], TrajectoryMode.EXACT)
    assert r.passed is True
    assert r.reasons == []


def test_validate_trajectory_in_order_reasons():
    # Expected tool absent from trace → "was never called"
    r = validate_trajectory([tool_a, tool_b], [tool_a, tool_c], TrajectoryMode.IN_ORDER)
    assert r.passed is False
    assert len(r.reasons) == 1
    assert "position 1" in r.reasons[0]
    assert "get_time" in r.reasons[0]
    assert "was never called" in r.reasons[0]

    # Expected tool present but wrong order → "was called out of order"
    # expected [A, B], actual [B, A]: pointer advances on A, B is unmatched but IS present
    r = validate_trajectory([tool_a, tool_b], [tool_b, tool_a], TrajectoryMode.IN_ORDER)
    assert r.passed is False
    assert len(r.reasons) == 1
    assert "position 1" in r.reasons[0]
    assert "get_time" in r.reasons[0]
    assert "was called out of order" in r.reasons[0]

    # Blocked-pointer suppression: actual [lookup, issue_refund],
    # expected [lookup, check_dup, issue_refund].
    # check_dup is absent → 1 reason. issue_refund is present → suppressed.
    lookup = ToolCall(tool_name="lookup_order", args={"order_id": "4521"})
    check_dup = ToolCall(tool_name="check_duplicate_charge", args={"order_id": "4521"})
    issue_refund = ToolCall(tool_name="issue_refund", args={"order_id": "4521", "amount": "full"})
    r = validate_trajectory(
        [lookup, check_dup, issue_refund],
        [lookup, issue_refund],
        TrajectoryMode.IN_ORDER,
    )
    assert r.passed is False
    assert len(r.reasons) == 1
    assert "check_duplicate_charge" in r.reasons[0]
    assert "position 1" in r.reasons[0]
    assert "was never called" in r.reasons[0]

    # Passing — no reasons
    r = validate_trajectory([tool_a, tool_b], [tool_a, tool_c, tool_b], TrajectoryMode.IN_ORDER)
    assert r.passed is True
    assert r.reasons == []


def test_validate_trajectory_any_order_reasons():
    # One missing
    r = validate_trajectory([tool_a, tool_b], [tool_a, tool_c], TrajectoryMode.ANY_ORDER)
    assert r.passed is False
    assert len(r.reasons) == 1
    assert "get_time" in r.reasons[0]
    assert "not found in trace" in r.reasons[0]

    # Two missing
    r = validate_trajectory([tool_a, tool_b], [tool_c], TrajectoryMode.ANY_ORDER)
    assert len(r.reasons) == 2

    # Passing — no reasons
    r = validate_trajectory([tool_a], [tool_b, tool_a], TrajectoryMode.ANY_ORDER)
    assert r.passed is True
    assert r.reasons == []


def test_validate_system_constraints_reasons():
    case = EDDTestCase(
        case_id="case_1",
        input_prompt="Test",
        expected_skill="skill_x",
        expected_tool_calls=[],
        trajectory_mode=TrajectoryMode.IN_ORDER,
        rubric=["polite"],
    )

    # Cost exceeded
    trace = AgentTrace(
        session_id="s1",
        triggered_skills=["skill_x"],
        executed_tools=[],
        final_output="ok",
        total_token_cost_usd=0.25,
    )
    r = validate_system_constraints(trace, case, max_cost=0.10)
    assert r.passed is False
    assert len(r.reasons) == 1
    assert "$0.2500" in r.reasons[0]
    assert "$0.1000" in r.reasons[0]
    assert "exceeds budget" in r.reasons[0]

    # Skill missing
    trace_bad_skill = AgentTrace(
        session_id="s2",
        triggered_skills=["other_skill"],
        executed_tools=[],
        final_output="ok",
        total_token_cost_usd=0.01,
    )
    r = validate_system_constraints(trace_bad_skill, case)
    assert r.passed is False
    assert len(r.reasons) == 1
    assert "skill_x" in r.reasons[0]
    assert "not triggered" in r.reasons[0]
    assert "other_skill" in r.reasons[0]

    # Both failures
    r = validate_system_constraints(trace, case)  # trace has cost=0.25 and correct skill
    # Only cost fails here (skill IS triggered)
    assert len(r.reasons) == 1

    # Both fail together
    r = validate_system_constraints(trace_bad_skill, case, max_cost=0.001)
    assert r.passed is False
    assert len(r.reasons) == 2

    # Passing — no reasons
    trace_ok = AgentTrace(
        session_id="s3",
        triggered_skills=["skill_x"],
        executed_tools=[],
        final_output="ok",
        total_token_cost_usd=0.01,
    )
    r = validate_system_constraints(trace_ok, case)
    assert r.passed is True
    assert r.reasons == []


@pytest.mark.asyncio
@patch("traceeval.metrics.trajectory_judge.get_judge_client")
async def test_evaluate_dimensions(mock_get_judge_client):
    mock_client = MagicMock()
    mock_get_judge_client.return_value = mock_client

    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_message = MagicMock()

    mock_score = EvaluationDimensionScore(
        intent_satisfaction=0.9,
        functional_correctness=0.85,
        trajectory_quality=1.0,
        cost_efficiency=0.8,
        safety_and_rai=1.0,
        reasoning="Good implementation"
    )
    mock_message.content = mock_score.model_dump_json()
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    case = EDDTestCase(
        case_id="case_1",
        input_prompt="Prompt",
        expected_skill=None,
        expected_tool_calls=[],
        trajectory_mode=TrajectoryMode.IN_ORDER,
        rubric=["check 1"]
    )
    trace = AgentTrace(
        session_id="session_1",
        triggered_skills=[],
        executed_tools=[],
        final_output="Output",
        total_token_cost_usd=0.01
    )

    result = await evaluate_dimensions(trace, case)
    assert result == mock_score
    mock_client.chat.completions.create.assert_called_once()


@pytest.mark.asyncio
@patch("traceeval.metrics.trajectory_judge.get_judge_client")
async def test_evaluate_dimensions_empty_response(mock_get_judge_client):
    mock_client = MagicMock()
    mock_get_judge_client.return_value = mock_client

    case = EDDTestCase(
        case_id="case_empty",
        input_prompt="Prompt",
        expected_skill=None,
        expected_tool_calls=[],
        trajectory_mode=TrajectoryMode.IN_ORDER,
        rubric=["check 1"],
    )
    trace = AgentTrace(
        session_id="session_empty",
        triggered_skills=[],
        executed_tools=[],
        final_output="Output",
        total_token_cost_usd=0.01,
    )

    # choices = None
    mock_response_none = MagicMock()
    mock_response_none.choices = None
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response_none)
    with pytest.raises(ValueError, match="no response"):
        await evaluate_dimensions(trace, case)

    # choices = []
    mock_response_empty = MagicMock()
    mock_response_empty.choices = []
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response_empty)
    with pytest.raises(ValueError, match="no response"):
        await evaluate_dimensions(trace, case)

    # choices present but content is empty string
    mock_response_no_content = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = ""
    mock_response_no_content.choices = [mock_choice]
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response_no_content)
    with pytest.raises(ValueError, match="empty content"):
        await evaluate_dimensions(trace, case)


@pytest.mark.asyncio
@patch("traceeval.metrics.trajectory_judge.evaluate_dimensions")
async def test_run_evaluation(mock_eval_dimensions):
    mock_score = EvaluationDimensionScore(
        intent_satisfaction=0.9,
        functional_correctness=0.9,
        trajectory_quality=1.0,
        cost_efficiency=0.8,
        safety_and_rai=1.0,
        reasoning="Passed"
    )
    mock_eval_dimensions.return_value = mock_score

    case = EDDTestCase(
        case_id="case_1",
        input_prompt="Prompt",
        expected_skill="weather",
        expected_tool_calls=[tool_a],
        trajectory_mode=TrajectoryMode.IN_ORDER,
        rubric=["rubric 1"]
    )

    # 1. Successful evaluation — failures list is empty
    trace_pass = AgentTrace(
        session_id="session_1",
        triggered_skills=["weather"],
        executed_tools=[tool_a],
        final_output="Output",
        total_token_cost_usd=0.01
    )
    res = await run_evaluation(case, trace_pass)
    assert res.passed is True
    assert res.case_id == "case_1"
    assert res.scores == mock_score
    assert res.failures == []

    # 2. Failed evaluation due to trajectory mode EXACT mismatch — failures populated
    case_exact = EDDTestCase(
        case_id="case_1",
        input_prompt="Prompt",
        expected_skill="weather",
        expected_tool_calls=[tool_a],
        trajectory_mode=TrajectoryMode.EXACT,
        rubric=["rubric 1"]
    )
    trace_extra = AgentTrace(
        session_id="session_1",
        triggered_skills=["weather"],
        executed_tools=[tool_b, tool_a],  # extra leading tool call
        final_output="Output",
        total_token_cost_usd=0.01
    )
    res = await run_evaluation(case_exact, trace_extra)
    assert res.passed is False
    assert len(res.failures) > 0
    assert any("tool call" in f for f in res.failures)

    # 3. Failed evaluation due to low score — failure reasons include dimension name
    mock_low_score = EvaluationDimensionScore(
        intent_satisfaction=0.5,
        functional_correctness=0.9,
        trajectory_quality=1.0,
        cost_efficiency=0.8,
        safety_and_rai=1.0,
        reasoning="Intent not fully satisfied"
    )
    mock_eval_dimensions.return_value = mock_low_score
    res = await run_evaluation(case, trace_pass, score_threshold=0.7)
    assert res.passed is False
    assert len(res.failures) == 1
    assert "Intent Satisfaction" in res.failures[0]
    assert "0.5" in res.failures[0]
    assert "0.7" in res.failures[0]


@pytest.mark.asyncio
@patch("traceeval.metrics.trajectory_judge.evaluate_dimensions")
async def test_run_evaluation_null_dimensions(mock_eval_dimensions):
    case = EDDTestCase(
        case_id="null_case",
        input_prompt="Prompt",
        expected_skill="svc",
        expected_tool_calls=[tool_a],
        trajectory_mode=TrajectoryMode.IN_ORDER,
        rubric=["rubric 1"],
    )
    trace = AgentTrace(
        session_id="s1",
        triggered_skills=["svc"],
        executed_tools=[tool_a],
        final_output="Output",
        total_token_cost_usd=0.01,
    )

    # All five null → fails with exactly 3 reasons (one per required dimension)
    mock_eval_dimensions.return_value = EvaluationDimensionScore(
        intent_satisfaction=None,
        functional_correctness=None,
        trajectory_quality=None,
        cost_efficiency=None,
        safety_and_rai=None,
        reasoning="Unable to score",
    )
    res = await run_evaluation(case, trace)
    assert res.passed is False
    assert len(res.failures) == 3
    assert any("intent_satisfaction" in f for f in res.failures)
    assert any("functional_correctness" in f for f in res.failures)
    assert any("safety_and_rai" in f for f in res.failures)
    # optional dims must NOT produce failures
    assert not any("trajectory_quality" in f for f in res.failures)
    assert not any("cost_efficiency" in f for f in res.failures)

    # Only cost_efficiency null, all required dims scored above threshold → passes
    mock_eval_dimensions.return_value = EvaluationDimensionScore(
        intent_satisfaction=0.9,
        functional_correctness=0.9,
        trajectory_quality=0.9,
        cost_efficiency=None,
        safety_and_rai=0.9,
        reasoning="OK",
    )
    res = await run_evaluation(case, trace)
    assert res.passed is True
    assert res.failures == []

    # safety_and_rai null, all others above threshold → fails with exactly one reason
    mock_eval_dimensions.return_value = EvaluationDimensionScore(
        intent_satisfaction=0.9,
        functional_correctness=0.9,
        trajectory_quality=0.9,
        cost_efficiency=0.9,
        safety_and_rai=None,
        reasoning="Safety unclear",
    )
    res = await run_evaluation(case, trace)
    assert res.passed is False
    assert len(res.failures) == 1
    assert "safety_and_rai" in res.failures[0]
    assert "null" in res.failures[0]


# --- Gate-2 (judge) structured failure codes ---


@pytest.mark.asyncio
@patch("traceeval.metrics.trajectory_judge.evaluate_dimensions")
async def test_reason_details_judge_below_threshold(mock_eval_dimensions):
    case = EDDTestCase(
        case_id="case_1", input_prompt="Prompt", expected_tool_calls=[tool_a],
        trajectory_mode=TrajectoryMode.IN_ORDER, rubric=["rubric 1"],
    )
    trace = AgentTrace(
        session_id="s1", triggered_skills=[], executed_tools=[tool_a],
        final_output="Output", total_token_cost_usd=0.01,
    )
    mock_eval_dimensions.return_value = EvaluationDimensionScore(
        intent_satisfaction=0.5,
        functional_correctness=0.9,
        trajectory_quality=1.0,
        cost_efficiency=0.8,
        safety_and_rai=1.0,
        reasoning="Intent not fully satisfied",
    )
    res = await run_evaluation(case, trace, score_threshold=0.7)
    assert res.passed is False
    assert len(res.failure_details) == 1
    d = res.failure_details[0]
    assert d.code == FailureCode.JUDGE_BELOW_THRESHOLD
    assert d.dimension == "intent_satisfaction"
    assert d.expected == 0.7 and d.actual == 0.5


@pytest.mark.asyncio
@patch("traceeval.metrics.trajectory_judge.evaluate_dimensions")
async def test_reason_details_judge_null_dimension(mock_eval_dimensions):
    case = EDDTestCase(
        case_id="null_case", input_prompt="Prompt", expected_tool_calls=[tool_a],
        trajectory_mode=TrajectoryMode.IN_ORDER, rubric=["rubric 1"],
    )
    trace = AgentTrace(
        session_id="s1", triggered_skills=[], executed_tools=[tool_a],
        final_output="Output", total_token_cost_usd=0.01,
    )
    mock_eval_dimensions.return_value = EvaluationDimensionScore(
        intent_satisfaction=0.9,
        functional_correctness=0.9,
        trajectory_quality=0.9,
        cost_efficiency=0.9,
        safety_and_rai=None,
        reasoning="Safety unclear",
    )
    res = await run_evaluation(case, trace)
    assert res.passed is False
    assert len(res.failure_details) == 1
    d = res.failure_details[0]
    assert d.code == FailureCode.JUDGE_NULL_DIMENSION
    assert d.dimension == "safety_and_rai"


@pytest.mark.asyncio
@patch("traceeval.metrics.trajectory_judge.evaluate_dimensions")
async def test_run_evaluation_judge_error_cases(mock_eval_dimensions):
    case = EDDTestCase(
        case_id="case_1", input_prompt="Prompt", expected_tool_calls=[tool_a],
        trajectory_mode=TrajectoryMode.IN_ORDER, rubric=["rubric 1"],
    )
    trace = AgentTrace(
        session_id="s1", triggered_skills=[], executed_tools=[tool_a],
        final_output="Output", total_token_cost_usd=0.01,
    )

    for message in [
        "Judge LLM returned no response (possibly rate-limited).",
        "Judge LLM returned empty content.",
        "Failed to parse LLM evaluation response.",
    ]:
        mock_eval_dimensions.side_effect = ValueError(message)
        # run_evaluation must NOT raise — it converts the error into a normal result.
        res = await run_evaluation(case, trace)
        assert res.passed is False
        assert len(res.failure_details) == 1
        d = res.failure_details[0]
        assert d.code == FailureCode.JUDGE_ERROR
        assert message in d.message
        assert any(message in f for f in res.failures)


# --- Flexible arg matching: _field_matches / _tool_matches via validate_trajectory ---


def test_args_match_exact_type_strict():
    exp = ExpectedToolCall(tool_name="x", args={"n": 5})
    assert validate_trajectory([exp], [ToolCall(tool_name="x", args={"n": 5})], TrajectoryMode.EXACT).passed is True
    assert validate_trajectory([exp], [ToolCall(tool_name="x", args={"n": "5"})], TrajectoryMode.EXACT).passed is False

    exp_subset = ExpectedToolCall(tool_name="x", args={"n": 5}, arg_match_mode=ArgMatchMode.SUBSET)
    assert validate_trajectory([exp_subset], [ToolCall(tool_name="x", args={"n": "5"})], TrajectoryMode.EXACT).passed is False


def test_args_match_subset_allows_extra_actual_keys():
    exp = ExpectedToolCall(tool_name="x", args={"a": "1"}, arg_match_mode=ArgMatchMode.SUBSET)
    actual = ToolCall(tool_name="x", args={"a": "1", "b": "extra"})
    assert validate_trajectory([exp], [actual], TrajectoryMode.EXACT).passed is True


def test_args_match_subset_missing_expected_key_fails():
    exp = ExpectedToolCall(tool_name="x", args={"a": "1", "c": "2"}, arg_match_mode=ArgMatchMode.SUBSET)
    actual = ToolCall(tool_name="x", args={"a": "1"})
    assert validate_trajectory([exp], [actual], TrajectoryMode.EXACT).passed is False


def test_args_match_exact_with_regex_override_fails_on_extra_actual_key():
    # Call-level EXACT + a per-field REGEX override must still be key-set strict:
    # an extra actual key fails even though the overridden field's regex matches.
    exp = ExpectedToolCall(
        tool_name="check", args={"a": "^val$"},
        arg_match_mode=ArgMatchMode.EXACT, field_overrides={"a": ArgMatchMode.REGEX},
    )
    actual = ToolCall(tool_name="check", args={"a": "val", "b": "extra"})
    assert validate_trajectory([exp], [actual], TrajectoryMode.EXACT).passed is False

    # Without the extra key, the same expectation passes.
    actual_no_extra = ToolCall(tool_name="check", args={"a": "val"})
    assert validate_trajectory([exp], [actual_no_extra], TrajectoryMode.EXACT).passed is True


def test_args_match_regex_field_override_matches():
    exp = ExpectedToolCall(
        tool_name="check", args={"session_token": "^sess_[a-f0-9]{4}$"},
        arg_match_mode=ArgMatchMode.EXACT, field_overrides={"session_token": ArgMatchMode.REGEX},
    )
    ok = ToolCall(tool_name="check", args={"session_token": "sess_ab12"})
    bad = ToolCall(tool_name="check", args={"session_token": "nope"})
    assert validate_trajectory([exp], [ok], TrajectoryMode.EXACT).passed is True
    assert validate_trajectory([exp], [bad], TrajectoryMode.EXACT).passed is False


def test_args_match_regex_non_string_actual_coerced():
    exp = ExpectedToolCall(tool_name="x", args={"count": "^42$"}, arg_match_mode=ArgMatchMode.REGEX)
    actual = ToolCall(tool_name="x", args={"count": 42})
    assert validate_trajectory([exp], [actual], TrajectoryMode.EXACT).passed is True


def test_args_match_any_mode_ignores_value_but_requires_key_presence():
    exp = ExpectedToolCall(tool_name="x", args={"a": "unused"}, arg_match_mode=ArgMatchMode.ANY)
    assert validate_trajectory([exp], [ToolCall(tool_name="x", args={"a": 12345})], TrajectoryMode.EXACT).passed is True


def test_args_match_any_mode_missing_key_fails():
    exp = ExpectedToolCall(tool_name="x", args={"a": "unused"}, arg_match_mode=ArgMatchMode.ANY)
    assert validate_trajectory([exp], [ToolCall(tool_name="x", args={})], TrajectoryMode.EXACT).passed is False


def test_validate_trajectory_plain_toolcall_defaults_to_exact():
    # A bare ToolCall (no arg_match_mode/field_overrides attrs) must behave identically to
    # an ExpectedToolCall with arg_match_mode=EXACT and no overrides.
    assert validate_trajectory([tool_a, tool_b], [tool_a, tool_b], TrajectoryMode.EXACT).passed is True
    assert validate_trajectory([tool_a, tool_c], [tool_a, tool_b], TrajectoryMode.EXACT).passed is False
    assert validate_trajectory([tool_a, tool_b], [tool_a, tool_c, tool_b], TrajectoryMode.IN_ORDER).passed is True
    assert validate_trajectory([tool_a, tool_b], [tool_b, tool_a], TrajectoryMode.ANY_ORDER).passed is True


# --- Pydantic coercion / load-time validation ---


def test_edd_test_case_accepts_bare_toolcall_in_expected_tool_calls():
    # Regression test: pydantic v2 rejects a base-class instance where a subclass field is
    # declared, so EDDTestCase must coerce plain ToolCall -> ExpectedToolCall via a
    # field_validator(mode="before"), or every existing caller that builds EDDTestCase with
    # plain ToolCall objects (as this test file does throughout) would break.
    case = EDDTestCase(case_id="c1", input_prompt="p", expected_tool_calls=[tool_a], rubric=["r"])
    assert isinstance(case.expected_tool_calls[0], ExpectedToolCall)
    assert case.expected_tool_calls[0].arg_match_mode == ArgMatchMode.EXACT
    assert case.expected_tool_calls[0].tool_name == tool_a.tool_name
    assert case.expected_tool_calls[0].args == tool_a.args


def test_edd_test_case_rejects_tool_in_both_expected_and_forbidden():
    with pytest.raises(ValidationError):
        EDDTestCase(
            case_id="c1", input_prompt="p",
            expected_tool_calls=[tool_a],
            forbidden_tools=["get_weather"],
            rubric=["r"],
        )


def test_expected_tool_call_rejects_invalid_regex():
    with pytest.raises(ValidationError):
        ExpectedToolCall(
            tool_name="x", args={"a": "[invalid("},
            arg_match_mode=ArgMatchMode.EXACT, field_overrides={"a": ArgMatchMode.REGEX},
        )


def test_edd_test_case_rejects_invalid_forbidden_args_regex():
    with pytest.raises(ValidationError):
        EDDTestCase(
            case_id="c1", input_prompt="p", rubric=["r"],
            forbidden_args={"issue_refund": [{"amount": "[bad("}]},
        )


# --- Structured reason_details: every existing failure path gets a FailureCode ---


def test_reason_details_trajectory_length_mismatch():
    r = validate_trajectory([tool_a, tool_b], [tool_a], TrajectoryMode.EXACT)
    assert len(r.reason_details) == 1
    d = r.reason_details[0]
    assert d.code == FailureCode.TRAJECTORY_LENGTH_MISMATCH
    assert d.expected == 2 and d.actual == 1
    assert d.step_index is None and d.expected_index is None


def test_reason_details_trajectory_step_mismatch_different_tool_name():
    r = validate_trajectory([tool_a], [tool_b], TrajectoryMode.EXACT)
    d = r.reason_details[0]
    assert d.code == FailureCode.TRAJECTORY_STEP_MISMATCH
    assert d.step_index == 0 and d.expected_index == 0


def test_reason_details_tool_call_never_called_in_order():
    r = validate_trajectory([tool_a, tool_b], [tool_a, tool_c], TrajectoryMode.IN_ORDER)
    d = r.reason_details[0]
    assert d.code == FailureCode.TOOL_CALL_NEVER_CALLED
    assert d.expected_index == 1


def test_reason_details_tool_call_out_of_order():
    r = validate_trajectory([tool_a, tool_b], [tool_b, tool_a], TrajectoryMode.IN_ORDER)
    d = r.reason_details[0]
    assert d.code == FailureCode.TOOL_CALL_OUT_OF_ORDER
    assert d.expected_index == 1
    assert d.step_index == 0  # tool_b sits at actual index 0


def test_reason_details_tool_call_not_found_any_order():
    r = validate_trajectory([tool_a, tool_b], [tool_a, tool_c], TrajectoryMode.ANY_ORDER)
    d = r.reason_details[0]
    assert d.code == FailureCode.TOOL_CALL_NOT_FOUND
    assert d.expected_index == 1


def test_reason_details_cost_exceeded():
    case = EDDTestCase(case_id="c1", input_prompt="p", rubric=["r"])
    trace = AgentTrace(session_id="s", triggered_skills=[], executed_tools=[], final_output="ok", total_token_cost_usd=0.25)
    r = validate_system_constraints(trace, case, max_cost=0.10)
    codes = [d.code for d in r.reason_details]
    assert FailureCode.COST_EXCEEDED in codes
    d = next(d for d in r.reason_details if d.code == FailureCode.COST_EXCEEDED)
    assert d.expected == 0.10 and d.actual == 0.25


def test_reason_details_cost_incomplete():
    case = EDDTestCase(case_id="c1", input_prompt="p", rubric=["r"])
    trace = AgentTrace(
        session_id="s", triggered_skills=[], executed_tools=[], final_output="ok",
        total_token_cost_usd=0.01, cost_complete=False,
    )
    r = validate_system_constraints(trace, case)
    assert any(d.code == FailureCode.COST_INCOMPLETE for d in r.reason_details)


def test_reason_details_skill_not_triggered():
    case = EDDTestCase(case_id="c1", input_prompt="p", expected_skill="skill_x", rubric=["r"])
    trace = AgentTrace(session_id="s", triggered_skills=["other"], executed_tools=[], final_output="ok", total_token_cost_usd=0.01)
    r = validate_system_constraints(trace, case)
    d = next(d for d in r.reason_details if d.code == FailureCode.SKILL_NOT_TRIGGERED)
    assert d.expected == "skill_x" and d.actual == ["other"]


# --- ARG_MISMATCH vs. "tool truly absent" distinction ---


def test_arg_mismatch_vs_tool_absent_exact_mode():
    # Same tool name, wrong args -> ARG_MISMATCH.
    r_same_name = validate_trajectory([tool_a], [tool_c], TrajectoryMode.EXACT)
    assert r_same_name.reason_details[0].code == FailureCode.ARG_MISMATCH
    # Different tool name entirely -> TRAJECTORY_STEP_MISMATCH.
    r_diff_name = validate_trajectory([tool_a], [tool_b], TrajectoryMode.EXACT)
    assert r_diff_name.reason_details[0].code == FailureCode.TRAJECTORY_STEP_MISMATCH


def test_classify_miss_only_considers_unconsumed_actual_in_order():
    search_a = ToolCall(tool_name="search", args={"q": "a"})
    search_b = ToolCall(tool_name="search", args={"q": "b"})
    search_c = ToolCall(tool_name="search", args={"q": "c"})

    # search_a consumes the only actual call; search_b's miss must NOT be misclassified
    # as ARG_MISMATCH against the already-consumed actual call.
    r = validate_trajectory([search_a, search_b], [search_a], TrajectoryMode.IN_ORDER)
    assert len(r.reason_details) == 1
    assert r.reason_details[0].code == FailureCode.TOOL_CALL_NEVER_CALLED

    # Companion: an unconsumed same-named call with wrong args IS an ARG_MISMATCH.
    r2 = validate_trajectory([search_a, search_b], [search_a, search_c], TrajectoryMode.IN_ORDER)
    assert len(r2.reason_details) == 1
    d = r2.reason_details[0]
    assert d.code == FailureCode.ARG_MISMATCH
    assert d.step_index == 1  # search_c's index in actual
    assert d.expected_index == 1
    assert d.expected == {"q": "b"} and d.actual == {"q": "c"}


def test_classify_miss_only_considers_unconsumed_actual_any_order():
    search_a = ToolCall(tool_name="search", args={"q": "a"})
    search_b = ToolCall(tool_name="search", args={"q": "b"})
    search_c = ToolCall(tool_name="search", args={"q": "c"})

    r = validate_trajectory([search_a, search_b], [search_a], TrajectoryMode.ANY_ORDER)
    assert len(r.reason_details) == 1
    assert r.reason_details[0].code == FailureCode.TOOL_CALL_NOT_FOUND

    r2 = validate_trajectory([search_a, search_b], [search_a, search_c], TrajectoryMode.ANY_ORDER)
    assert len(r2.reason_details) == 1
    d = r2.reason_details[0]
    assert d.code == FailureCode.ARG_MISMATCH
    assert d.step_index == 1
    assert d.expected_index == 1


def test_in_order_present_anywhere_uses_unconsumed_actual_flexible_mode():
    # The ANY-mode expected call consumes the only actual call during the two-pointer scan.
    # The second (EXACT) expected call must NOT be classified as "out of order" just because
    # that same, already-consumed actual call happens to also satisfy it in isolation.
    any_search = ExpectedToolCall(tool_name="search", args={"q": "unused"}, arg_match_mode=ArgMatchMode.ANY)
    exact_search = ExpectedToolCall(tool_name="search", args={"q": "x"})
    actual = [ToolCall(tool_name="search", args={"q": "x"})]
    r = validate_trajectory([any_search, exact_search], actual, TrajectoryMode.IN_ORDER)
    assert len(r.reason_details) == 1
    assert r.reason_details[0].code == FailureCode.TOOL_CALL_NEVER_CALLED
    assert "was never called" in r.reasons[0]


def test_in_order_present_anywhere_uses_unconsumed_actual_plain_duplicate():
    # Plain duplicate expectations: [tool_a, tool_a] vs a trace with only one tool_a call.
    # The second tool_a consumes nothing new, so it must be TOOL_CALL_NEVER_CALLED, not
    # TOOL_CALL_OUT_OF_ORDER (there is no leftover, unconsumed occurrence of it anywhere).
    r = validate_trajectory([tool_a, tool_a], [tool_a], TrajectoryMode.IN_ORDER)
    assert len(r.reason_details) == 1
    assert r.reason_details[0].code == FailureCode.TOOL_CALL_NEVER_CALLED
    assert "was never called" in r.reasons[0]


def test_any_order_bipartite_matching_regression():
    # Greedy multiset removal would incorrectly fail this: the ANY-mode expected call could
    # steal the actual call the exact-mode expected call uniquely needs. A correct maximum
    # bipartite matching finds the valid assignment (ANY -> q=y, exact -> q=x).
    any_search = ExpectedToolCall(tool_name="search", args={"q": "unused"}, arg_match_mode=ArgMatchMode.ANY)
    exact_search = ExpectedToolCall(tool_name="search", args={"q": "x"})
    actual = [ToolCall(tool_name="search", args={"q": "x"}), ToolCall(tool_name="search", args={"q": "y"})]
    r = validate_trajectory([any_search, exact_search], actual, TrajectoryMode.ANY_ORDER)
    assert r.passed is True
    assert r.reasons == []


# --- Forbidden tools / forbidden args ---


def test_validate_forbidden_tools_detects_forbidden_tool_call():
    case = EDDTestCase(case_id="c", input_prompt="p", forbidden_tools=["delete_account"], rubric=["r"])
    actual = [tool_a, ToolCall(tool_name="delete_account", args={"user_id": "1"})]
    r = validate_forbidden_tools(actual, case)
    assert r.passed is False
    assert len(r.reasons) == 1
    assert "forbidden tool 'delete_account'" in r.reasons[0]
    assert r.reason_details[0].code == FailureCode.FORBIDDEN_TOOL_CALLED
    assert r.reason_details[0].step_index == 1


def test_validate_forbidden_tools_passes_when_absent():
    case = EDDTestCase(case_id="c", input_prompt="p", forbidden_tools=["delete_account"], rubric=["r"])
    r = validate_forbidden_tools([tool_a], case)
    assert r.passed is True
    assert r.reasons == []


def test_validate_forbidden_args_pattern_match_fails():
    case = EDDTestCase(
        case_id="c", input_prompt="p", rubric=["r"],
        forbidden_args={"issue_refund": [{"amount": "^unlimited$"}]},
    )
    actual = [ToolCall(tool_name="issue_refund", args={"amount": "unlimited"})]
    r = validate_forbidden_tools(actual, case)
    assert r.passed is False
    assert r.reason_details[0].code == FailureCode.FORBIDDEN_ARGS
    assert r.reason_details[0].step_index == 0


def test_validate_forbidden_args_pattern_no_match_passes():
    case = EDDTestCase(
        case_id="c", input_prompt="p", rubric=["r"],
        forbidden_args={"issue_refund": [{"amount": "^unlimited$"}]},
    )
    actual = [ToolCall(tool_name="issue_refund", args={"amount": "full"})]
    r = validate_forbidden_tools(actual, case)
    assert r.passed is True


@pytest.mark.asyncio
@patch("traceeval.metrics.trajectory_judge.evaluate_dimensions")
async def test_run_evaluation_short_circuits_on_forbidden_tool(mock_eval_dimensions):
    case = EDDTestCase(
        case_id="c1", input_prompt="p", expected_tool_calls=[], rubric=["r"],
        forbidden_tools=["delete_account"],
    )
    trace = AgentTrace(
        session_id="s1", triggered_skills=[],
        executed_tools=[ToolCall(tool_name="delete_account", args={})],
        final_output="done", total_token_cost_usd=0.01,
    )
    res = await run_evaluation(case, trace)
    assert res.passed is False
    assert any(f.code == FailureCode.FORBIDDEN_TOOL_CALLED for f in res.failure_details)
    mock_eval_dimensions.assert_not_called()


@pytest.mark.asyncio
@patch("traceeval.metrics.trajectory_judge.evaluate_dimensions")
async def test_run_evaluation_failure_details_ordering(mock_eval_dimensions):
    case = EDDTestCase(
        case_id="c1", input_prompt="p",
        expected_tool_calls=[tool_a], trajectory_mode=TrajectoryMode.EXACT,
        forbidden_tools=["delete_account"], rubric=["r"],
    )
    trace = AgentTrace(
        session_id="s1", triggered_skills=[],
        executed_tools=[ToolCall(tool_name="delete_account", args={})],
        final_output="done", total_token_cost_usd=0.01,
    )
    res = await run_evaluation(case, trace)
    assert res.passed is False
    # Structured list: forbidden-tool violation is the primary cause, surfaced first.
    assert res.failure_details[0].code == FailureCode.FORBIDDEN_TOOL_CALLED
    # Plain-string list: keeps the original trajectory-first concatenation order.
    assert "step 0" in res.failures[0]
    assert "forbidden tool" in res.failures[-1]
    mock_eval_dimensions.assert_not_called()


def test_edd_test_case_forbidden_args_contradiction_exact_raises():
    with pytest.raises(ValidationError):
        EDDTestCase(
            case_id="c1",
            input_prompt="p",
            expected_tool_calls=[ExpectedToolCall(tool_name="issue_refund", args={"amount": "100"}, arg_match_mode=ArgMatchMode.EXACT)],
            forbidden_args={"issue_refund": [{"amount": "^100$"}]},
            rubric=["r"],
        )


def test_edd_test_case_forbidden_args_regex_mode_loads_fine():
    case = EDDTestCase(
        case_id="c1",
        input_prompt="p",
        expected_tool_calls=[ExpectedToolCall(tool_name="issue_refund", args={"amount": r"^1\d+$"}, arg_match_mode=ArgMatchMode.REGEX)],
        forbidden_args={"issue_refund": [{"amount": "^1"}]},
        rubric=["r"],
    )
    assert case.case_id == "c1"


def test_edd_test_case_forbidden_args_multikey_partial_present_loads_fine():
    case = EDDTestCase(
        case_id="c1",
        input_prompt="p",
        expected_tool_calls=[ExpectedToolCall(tool_name="issue_refund", args={"amount": "100"}, arg_match_mode=ArgMatchMode.EXACT)],
        forbidden_args={"issue_refund": [{"amount": "^100$", "reason": "^fraud$"}]},
        rubric=["r"],
    )
    assert case.case_id == "c1"


def test_distinct_miss_binding_two_mismatches():
    exp = [
        ExpectedToolCall(tool_name="search", args={"q": "a"}),
        ExpectedToolCall(tool_name="search", args={"q": "b"}),
    ]
    act = [
        ToolCall(tool_name="search", args={"q": "wrong_1"}),
        ToolCall(tool_name="search", args={"q": "wrong_2"}),
    ]
    # ANY_ORDER
    r_any = validate_trajectory(exp, act, TrajectoryMode.ANY_ORDER)
    assert len(r_any.reason_details) == 2
    assert r_any.reason_details[0].code == FailureCode.ARG_MISMATCH
    assert r_any.reason_details[0].step_index == 0
    assert r_any.reason_details[1].code == FailureCode.ARG_MISMATCH
    assert r_any.reason_details[1].step_index == 1

    # IN_ORDER
    r_in = validate_trajectory(exp, act, TrajectoryMode.IN_ORDER)
    assert len(r_in.reason_details) == 2
    assert r_in.reason_details[0].code == FailureCode.ARG_MISMATCH
    assert r_in.reason_details[0].step_index == 0
    assert r_in.reason_details[1].code == FailureCode.ARG_MISMATCH
    assert r_in.reason_details[1].step_index == 1


def test_distinct_miss_binding_one_mismatch_one_absent():
    exp = [
        ExpectedToolCall(tool_name="search", args={"q": "a"}),
        ExpectedToolCall(tool_name="search", args={"q": "b"}),
    ]
    act = [ToolCall(tool_name="search", args={"q": "wrong_1"})]

    # ANY_ORDER
    r_any = validate_trajectory(exp, act, TrajectoryMode.ANY_ORDER)
    assert len(r_any.reason_details) == 2
    assert r_any.reason_details[0].code == FailureCode.ARG_MISMATCH
    assert r_any.reason_details[0].step_index == 0
    assert r_any.reason_details[1].code == FailureCode.TOOL_CALL_NOT_FOUND

    # IN_ORDER
    r_in = validate_trajectory(exp, act, TrajectoryMode.IN_ORDER)
    assert len(r_in.reason_details) == 2
    assert r_in.reason_details[0].code == FailureCode.ARG_MISMATCH
    assert r_in.reason_details[0].step_index == 0
    assert r_in.reason_details[1].code == FailureCode.TOOL_CALL_NEVER_CALLED


def test_args_match_subset_with_exact_field_override():
    exp = ExpectedToolCall(
        tool_name="search", args={"q": "python", "limit": 10},
        arg_match_mode=ArgMatchMode.SUBSET, field_overrides={"limit": ArgMatchMode.EXACT},
    )
    ok = ToolCall(tool_name="search", args={"q": "python", "limit": 10, "extra": "allowed"})
    bad = ToolCall(tool_name="search", args={"q": "python", "limit": 99, "extra": "allowed"})
    assert validate_trajectory([exp], [ok], TrajectoryMode.EXACT).passed is True
    assert validate_trajectory([exp], [bad], TrajectoryMode.EXACT).passed is False


def test_args_match_any_with_regex_field_override():
    exp = ExpectedToolCall(
        tool_name="search", args={"q": r"^py\d+$", "category": "unused"},
        arg_match_mode=ArgMatchMode.ANY, field_overrides={"q": ArgMatchMode.REGEX},
    )
    ok = ToolCall(tool_name="search", args={"q": "py3", "category": "books"})
    bad = ToolCall(tool_name="search", args={"q": "java", "category": "books"})
    assert validate_trajectory([exp], [ok], TrajectoryMode.EXACT).passed is True
    assert validate_trajectory([exp], [bad], TrajectoryMode.EXACT).passed is False


def test_validate_forbidden_args_multikey_and_logic():
    case = EDDTestCase(
        case_id="c", input_prompt="p", rubric=["r"],
        forbidden_args={"issue_refund": [{"amount": "^100$", "reason": "^fraud$"}]},
    )
    # Only amount matches -> Passes
    partial = [ToolCall(tool_name="issue_refund", args={"amount": "100", "reason": "customer_req"})]
    assert validate_forbidden_tools(partial, case).passed is True

    # Both match -> Fails
    full = [ToolCall(tool_name="issue_refund", args={"amount": "100", "reason": "fraud"})]
    assert validate_forbidden_tools(full, case).passed is False

