# tests/test_loaders.py
"""Tests for data loader utilities."""

import pathlib
from traceeval.loaders.file import load_test_case, load_trace
from traceeval.core.schema import EDDTestCase, AgentTrace, TrajectoryMode
from traceeval.metrics.trajectory_judge import validate_system_constraints


def test_load_test_case(tmp_path: pathlib.Path):
    json_path = tmp_path / "case.json"
    json_path.write_text("""{
        "case_id": "c1",
        "input_prompt": "Hello",
        "expected_skill": "greet",
        "expected_tool_calls": [],
        "trajectory_mode": "EXACT",
        "rubric": ["polite"]
    }""", encoding="utf-8")

    case = load_test_case(json_path)
    assert isinstance(case, EDDTestCase)
    assert case.case_id == "c1"
    assert case.input_prompt == "Hello"
    assert case.expected_skill == "greet"


def test_load_trace(tmp_path: pathlib.Path):
    json_path = tmp_path / "trace.json"
    json_path.write_text("""{
        "session_id": "s1",
        "triggered_skills": ["greet"],
        "executed_tools": [],
        "final_output": "Hi there!",
        "total_token_cost_usd": 0.002
    }""", encoding="utf-8")

    trace = load_trace(json_path)
    assert isinstance(trace, AgentTrace)
    assert trace.session_id == "s1"
    assert trace.final_output == "Hi there!"
    assert trace.total_token_cost_usd == 0.002


def test_load_trace_without_cost_complete_field_defaults_true_and_passes(tmp_path: pathlib.Path):
    """Pre-existing JSON traces predate cost_complete; they must still load and pass checks."""
    json_path = tmp_path / "trace_legacy.json"
    json_path.write_text("""{
        "session_id": "s1",
        "triggered_skills": ["greet"],
        "executed_tools": [],
        "final_output": "Hi there!",
        "total_token_cost_usd": 0.002
    }""", encoding="utf-8")

    trace = load_trace(json_path)
    assert trace.cost_complete is True

    case = EDDTestCase(
        case_id="c1",
        input_prompt="Hello",
        expected_skill=None,
        expected_tool_calls=[],
        trajectory_mode=TrajectoryMode.IN_ORDER,
        rubric=["polite"],
    )
    assert validate_system_constraints(trace, case).passed is True
