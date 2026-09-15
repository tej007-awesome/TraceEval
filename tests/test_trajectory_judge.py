# tests/test_trajectory_judge.py
"""Tests for the trajectory judge metric module."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from traceeval.core.schema import (
    TrajectoryMode,
    ToolCall,
    EDDTestCase,
    AgentTrace,
    EvaluationDimensionScore,
)
from traceeval.metrics.trajectory_judge import (
    validate_trajectory,
    validate_system_constraints,
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
@patch("traceeval.metrics.trajectory_judge.AsyncOpenAI")
async def test_evaluate_dimensions(mock_async_openai_class, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")
    # Setup mocks
    mock_client = MagicMock()
    mock_async_openai_class.return_value = mock_client

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
@patch("traceeval.metrics.trajectory_judge.AsyncOpenAI")
async def test_evaluate_dimensions_empty_response(mock_async_openai_class, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")
    mock_client = MagicMock()
    mock_async_openai_class.return_value = mock_client

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
