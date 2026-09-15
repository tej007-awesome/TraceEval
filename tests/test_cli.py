import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from traceeval.cli import app
from traceeval.core.schema import EvaluationDimensionScore

runner = CliRunner()


@patch("traceeval.metrics.trajectory_judge.get_judge_client")
def test_cli_otel_trace_happy(mock_get_client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")
    mock_client = AsyncMock()
    mock_get_client.return_value = mock_client

    mock_score = EvaluationDimensionScore(
        intent_satisfaction=1.0,
        functional_correctness=1.0,
        trajectory_quality=1.0,
        cost_efficiency=1.0,
        safety_and_rai=1.0,
        reasoning="All criteria met",
    )
    mock_response = AsyncMock()
    mock_response.choices = [AsyncMock(message=AsyncMock(content=mock_score.model_dump_json()))]
    mock_client.chat.completions.create.return_value = mock_response

    res = runner.invoke(
        app,
        [
            "run",
            "--case",
            "sample_data/case_01.json",
            "--otel-trace",
            "tests/fixtures/otel/refund_happy.json",
        ],
    )
    assert res.exit_code == 0
    assert "Mode: OTel trace (tests/fixtures/otel/refund_happy.json)" in res.stdout
    assert "PASSED" in res.stdout


def test_cli_mutual_exclusion(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")
    # Passing both --trace and --otel-trace
    res = runner.invoke(
        app,
        [
            "run",
            "--case",
            "sample_data/case_01.json",
            "--trace",
            "sample_data/trace_01.json",
            "--otel-trace",
            "tests/fixtures/otel/refund_happy.json",
        ],
    )
    assert res.exit_code == 1
    assert "Exactly one of --trace, --otel-trace, or --pipeline must be provided" in res.stdout

    # Passing zero ingestion inputs
    res_zero = runner.invoke(app, ["run", "--case", "sample_data/case_01.json"])
    assert res_zero.exit_code == 1
    assert "Exactly one of --trace, --otel-trace, or --pipeline must be provided" in res_zero.stdout


def test_cli_otel_unknown_model_no_pricing(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")

    happy_path = Path("tests/fixtures/otel/refund_happy.json")
    data = json.loads(happy_path.read_text(encoding="utf-8"))
    for span in data["resourceSpans"][0]["scopeSpans"][0]["spans"]:
        for attr in span.get("attributes", []):
            if attr.get("key") == "gen_ai.request.model":
                attr["value"] = {"stringValue": "unknown-model-999"}

    unknown_trace_path = tmp_path / "unknown_model.json"
    unknown_trace_path.write_text(json.dumps(data), encoding="utf-8")

    res = runner.invoke(
        app,
        [
            "run",
            "--case",
            "sample_data/case_01.json",
            "--otel-trace",
            str(unknown_trace_path),
        ],
    )
    assert res.exit_code == 1
    assert "cost could not be verified" in res.stdout


@patch("traceeval.metrics.trajectory_judge.get_judge_client")
def test_cli_otel_no_args_warnings_printed(mock_get_client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")
    mock_client = AsyncMock()
    mock_get_client.return_value = mock_client

    res = runner.invoke(
        app,
        [
            "run",
            "--case",
            "sample_data/case_01.json",
            "--otel-trace",
            "tests/fixtures/otel/refund_no_args.json",
        ],
    )
    # refund_no_args has empty args so trajectory validation fails (or warnings print)
    assert "Warning: tool arguments not captured in trace" in res.stdout
    assert "Warning: final output not captured in trace" in res.stdout
