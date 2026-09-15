import json
from pathlib import Path
import pytest

from traceeval.core.schema import EDDTestCase, TrajectoryMode
from traceeval.loaders.file import load_test_case
from traceeval.loaders.otel import load_otel_trace
from traceeval.metrics.trajectory_judge import validate_system_constraints, validate_trajectory

FIXTURES_DIR = Path("tests/fixtures/otel")


def test_load_otel_trace_happy_path():
    happy_file = FIXTURES_DIR / "refund_happy.json"
    result = load_otel_trace(happy_file)

    assert result.warnings == []
    trace = result.trace
    assert trace.session_id == "sess_otel_001"
    assert trace.triggered_skills == ["refund-processor"]
    assert len(trace.executed_tools) == 3

    t1, t2, t3 = trace.executed_tools
    assert t1.tool_name == "lookup_order"
    assert t1.args == {"order_id": "4521"}
    assert t2.tool_name == "check_duplicate_charge"
    assert t2.args == {"order_id": "4521"}
    assert t3.tool_name == "issue_refund"
    assert t3.args == {"order_id": "4521", "amount": "full"}

    assert trace.final_output != ""
    assert "refund has been issued" in trace.final_output

    assert len(result.token_usage) == 4
    for usage in result.token_usage:
        assert usage.model == "gpt-4o-mini"
        assert usage.input_tokens > 0
        assert usage.output_tokens > 0

    total_input = sum(u.input_tokens for u in result.token_usage)
    total_output = sum(u.output_tokens for u in result.token_usage)
    expected_cost = (total_input / 1_000_000) * 0.15 + (total_output / 1_000_000) * 0.60

    assert trace.total_token_cost_usd == expected_cost
    assert trace.total_token_cost_usd > 0
    assert trace.cost_complete is True


def test_load_otel_trace_no_args_privacy():
    no_args_file = FIXTURES_DIR / "refund_no_args.json"
    result = load_otel_trace(no_args_file)

    assert len(result.warnings) == 2
    assert "tool arguments not captured in trace; argument matching will be unreliable" in result.warnings
    assert "final output not captured in trace" in result.warnings

    trace = result.trace
    assert trace.session_id == "sess_otel_001"
    assert trace.triggered_skills == ["refund-processor"]
    assert len(trace.executed_tools) == 3

    for tool in trace.executed_tools:
        assert tool.args == {}

    assert trace.final_output == ""
    assert len(result.token_usage) == 4


def test_load_otel_trace_multiple_trace_ids(tmp_path):
    multi_trace_json = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "trace_id_1111111111111111111111",
                                "name": "span1",
                                "startTimeUnixNano": "1000",
                            },
                            {
                                "traceId": "trace_id_2222222222222222222222",
                                "name": "span2",
                                "startTimeUnixNano": "2000",
                            },
                        ]
                    }
                ]
            }
        ]
    }
    file_path = tmp_path / "multi_trace.json"
    file_path.write_text(json.dumps(multi_trace_json))

    with pytest.raises(ValueError, match="multiple trace IDs"):
        load_otel_trace(file_path)


def test_load_otel_trace_malformed_json(tmp_path):
    file_path = tmp_path / "malformed.json"
    file_path.write_text("{ this is invalid json ")

    with pytest.raises(ValueError, match="Failed to parse OTel trace JSON file"):
        load_otel_trace(file_path)


def test_load_otel_trace_gate_1_validation():
    happy_file = FIXTURES_DIR / "refund_happy.json"
    result = load_otel_trace(happy_file)

    case_path = Path("sample_data/case_01.json")
    case = load_test_case(case_path)

    trajectory_check = validate_trajectory(
        expected=case.expected_tool_calls,
        actual=result.trace.executed_tools,
        mode=case.trajectory_mode,
    )
    assert trajectory_check.passed is True

    constraints_check = validate_system_constraints(
        trace=result.trace,
        case=case,
        max_cost=0.10,
    )
    assert constraints_check.passed is True


def test_load_otel_trace_unknown_model_fails_cost_check(tmp_path):
    unknown_model_json = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "trace_id_3333333333333333333333",
                                "name": "chat mystery-model",
                                "startTimeUnixNano": "1000",
                                "attributes": [
                                    {
                                        "key": "gen_ai.operation.name",
                                        "value": {"stringValue": "chat"},
                                    },
                                    {
                                        "key": "gen_ai.request.model",
                                        "value": {"stringValue": "mystery-model"},
                                    },
                                    {
                                        "key": "gen_ai.usage.input_tokens",
                                        "value": {"intValue": "100"},
                                    },
                                    {
                                        "key": "gen_ai.usage.output_tokens",
                                        "value": {"intValue": "50"},
                                    },
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    file_path = tmp_path / "unknown_model.json"
    file_path.write_text(json.dumps(unknown_model_json))

    result = load_otel_trace(file_path)

    assert result.trace.cost_complete is False
    assert "no pricing for model(s) [mystery-model]; cost is incomplete" in result.warnings

    case = EDDTestCase(
        case_id="case_unknown_model",
        input_prompt="Test prompt",
        expected_skill=None,
        expected_tool_calls=[],
        trajectory_mode=TrajectoryMode.IN_ORDER,
        rubric=["polite"],
    )
    constraints_check = validate_system_constraints(trace=result.trace, case=case)
    assert constraints_check.passed is False
    assert (
        "cost could not be verified: pricing missing for one or more models"
        in constraints_check.reasons
    )
