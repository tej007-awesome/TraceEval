# tests/test_trajectory_judge.py
"""Tests for the trajectory judge metric module."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agentci.core.schema import (
    TrajectoryMode,
    ToolCall,
    EDDTestCase,
    AgentTrace,
    EvaluationDimensionScore,
)
from agentci.metrics.trajectory_judge import (
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
    assert validate_trajectory([tool_a, tool_b], [tool_a, tool_b], TrajectoryMode.EXACT) is True
    # Different order
    assert validate_trajectory([tool_a, tool_b], [tool_b, tool_a], TrajectoryMode.EXACT) is False
    # Different length
    assert validate_trajectory([tool_a, tool_b], [tool_a], TrajectoryMode.EXACT) is False
    # Empty
    assert validate_trajectory([], [], TrajectoryMode.EXACT) is True
    assert validate_trajectory([], [tool_a], TrajectoryMode.EXACT) is False

def test_validate_trajectory_in_order():
    # Subsequence match
    assert validate_trajectory([tool_a, tool_b], [tool_a, tool_c, tool_b], TrajectoryMode.IN_ORDER) is True
    # Wrong relative order
    assert validate_trajectory([tool_a, tool_b], [tool_b, tool_a], TrajectoryMode.IN_ORDER) is False
    # Missing element
    assert validate_trajectory([tool_a, tool_b], [tool_a, tool_c], TrajectoryMode.IN_ORDER) is False
    # Empty expected
    assert validate_trajectory([], [tool_a, tool_b], TrajectoryMode.IN_ORDER) is True

def test_validate_trajectory_any_order():
    # Out of order matches
    assert validate_trajectory([tool_a, tool_b], [tool_b, tool_a], TrajectoryMode.ANY_ORDER) is True
    # Multiplicity handled correctly
    assert validate_trajectory([tool_a, tool_a], [tool_b, tool_a, tool_a], TrajectoryMode.ANY_ORDER) is True
    assert validate_trajectory([tool_a, tool_a], [tool_a], TrajectoryMode.ANY_ORDER) is False
    # Missing expected element
    assert validate_trajectory([tool_a, tool_b], [tool_a, tool_c], TrajectoryMode.ANY_ORDER) is False

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
    assert validate_system_constraints(trace_ok, case) is True

    # Cost too high
    trace_expensive = AgentTrace(
        session_id="session_1",
        triggered_skills=["weather_skill"],
        executed_tools=[tool_a],
        final_output="Weather is nice.",
        total_token_cost_usd=0.15
    )
    assert validate_system_constraints(trace_expensive, case, max_cost=0.10) is False

    # Required skill missing
    trace_wrong_skill = AgentTrace(
        session_id="session_1",
        triggered_skills=["time_skill"],
        executed_tools=[tool_a],
        final_output="Weather is nice.",
        total_token_cost_usd=0.05
    )
    assert validate_system_constraints(trace_wrong_skill, case) is False

    # Optional expected skill not provided in case, but present in trace
    case_no_skill = EDDTestCase(
        case_id="case_2",
        input_prompt="Test prompt",
        expected_skill=None,
        expected_tool_calls=[],
        rubric=[]
    )
    assert validate_system_constraints(trace_wrong_skill, case_no_skill) is True

@pytest.mark.asyncio
@patch("google.genai.Client")
async def test_evaluate_dimensions(mock_genai_client_class):
    # Setup mocks
    mock_client = MagicMock()
    mock_aio = AsyncMock()
    mock_aio.__aenter__.return_value = mock_aio
    mock_client.aio = mock_aio
    mock_genai_client_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_score = EvaluationDimensionScore(
        intent_satisfaction=0.9,
        functional_correctness=0.85,
        trajectory_quality=1.0,
        cost_efficiency=0.8,
        safety_and_rai=1.0,
        reasoning="Good implementation"
    )
    mock_response.parsed = mock_score
    mock_aio.models.generate_content.return_value = mock_response

    case = EDDTestCase(
        case_id="case_1",
        input_prompt="Prompt",
        expected_tool_calls=[],
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
    mock_aio.models.generate_content.assert_called_once()

@pytest.mark.asyncio
@patch("agentci.metrics.trajectory_judge.evaluate_dimensions")
async def test_run_evaluation(mock_eval_dimensions):
    mock_score = EvaluationDimensionScore(
        intent_satisfaction=0.9,
        functional_correctness=0.9,
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
    
    # 1. Successful evaluation
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

    # 2. Failed evaluation due to trajectory mode EXACT mismatch
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
        executed_tools=[tool_b, tool_a], # extra leading tool call
        final_output="Output",
        total_token_cost_usd=0.01
    )
    res = await run_evaluation(case_exact, trace_extra)
    assert res.passed is False

    # 3. Failed evaluation due to low score
    mock_low_score = EvaluationDimensionScore(
        intent_satisfaction=0.5,
        functional_correctness=0.9,
        reasoning="Intent not fully satisfied"
    )
    mock_eval_dimensions.return_value = mock_low_score
    res = await run_evaluation(case, trace_pass, score_threshold=0.7)
    assert res.passed is False
