"""Scenario data-quality lint tests - these check the authored scenario JSON files
themselves (benchmarks/scenarios/), not harness code correctness. A failure here means a
scenario file needs fixing, not that a test is broken.
"""
from pathlib import Path

from benchmarks.lint import find_hardcoded_regex_any_values
from benchmarks.models import Scenario
from benchmarks.run import load_scenarios
from traceeval.core.schema import AgentTrace, EDDTestCase, ExpectedToolCall, ToolCall


def _scenario_with_hardcoded_regex_value() -> Scenario:
    return Scenario(
        id="synthetic_001",
        domain="refunds",
        case=EDDTestCase(
            case_id="c1", input_prompt="p",
            expected_tool_calls=[ExpectedToolCall(
                tool_name="check_token", args={"token": "^tok_[a-f0-9]{4}$"},
                arg_match_mode="EXACT", field_overrides={"token": "REGEX"},
            )],
            rubric=["Mentions token tok_ab12 explicitly."],  # hardcodes the literal value
        ),
        trace=AgentTrace(
            session_id="s", triggered_skills=[],
            executed_tools=[ToolCall(tool_name="check_token", args={"token": "tok_ab12"})],
            final_output="Used token tok_ab12.", total_token_cost_usd=0.01,
        ),
    )


def _scenario_without_hardcoded_value() -> Scenario:
    return Scenario(
        id="synthetic_002",
        domain="refunds",
        case=EDDTestCase(
            case_id="c2", input_prompt="p",
            expected_tool_calls=[ExpectedToolCall(
                tool_name="check_token", args={"token": "^tok_[a-f0-9]{4}$"},
                arg_match_mode="EXACT", field_overrides={"token": "REGEX"},
            )],
            rubric=["Mentions the session token used."],  # generic, no literal
        ),
        trace=AgentTrace(
            session_id="s", triggered_skills=[],
            executed_tools=[ToolCall(tool_name="check_token", args={"token": "tok_ab12"})],
            final_output="Used token tok_ab12.", total_token_cost_usd=0.01,
        ),
    )


def test_find_hardcoded_regex_any_values_detects_violation():
    violations = find_hardcoded_regex_any_values([_scenario_with_hardcoded_regex_value()])
    assert len(violations) == 1
    assert violations[0]["scenario_id"] == "synthetic_001"
    assert violations[0]["field"] == "token"
    assert violations[0]["literal_value"] == "tok_ab12"


def test_find_hardcoded_regex_any_values_passes_generic_rubric():
    violations = find_hardcoded_regex_any_values([_scenario_without_hardcoded_value()])
    assert violations == []


def test_find_hardcoded_regex_any_values_ignores_exact_and_subset_fields():
    # An EXACT/SUBSET field's value SHOULD appear in the rubric - it's fixed by design, no
    # contradiction possible - so it must never be flagged.
    scenario = Scenario(
        id="synthetic_003", domain="refunds",
        case=EDDTestCase(
            case_id="c3", input_prompt="p",
            expected_tool_calls=[ExpectedToolCall(tool_name="lookup", args={"order_id": "4521"})],
            rubric=["Confirms order 4521 was found."],
        ),
        trace=AgentTrace(
            session_id="s", triggered_skills=[],
            executed_tools=[ToolCall(tool_name="lookup", args={"order_id": "4521"})],
            final_output="Found order 4521.", total_token_cost_usd=0.01,
        ),
    )
    assert find_hardcoded_regex_any_values([scenario]) == []


def test_no_regex_or_any_field_value_hardcoded_in_rubric():
    """Real scenario data lint: fails (by design) if any authored scenario hardcodes a
    REGEX/ANY field's literal trace value in its rubric text. A failure here names the
    exact scenario/field to fix - do not silently edit the rubric to make this pass."""
    scenarios = load_scenarios(Path("benchmarks/scenarios"))
    violations = find_hardcoded_regex_any_values(scenarios)
    assert violations == [], (
        f"{len(violations)} scenario(s) hardcode a REGEX/ANY field's literal trace value in "
        "rubric text, which creates a false contradiction whenever regex_conforming_variable_value "
        "legitimately varies that value. Fix the rubric to describe the field generically "
        "(e.g. 'mentions the session token used' instead of the literal value):\n" +
        "\n".join(
            f"  {v['scenario_id']}: {v['tool_name']}.{v['field']} ({v['mode']}) = {v['literal_value']!r}"
            for v in violations
        )
    )
