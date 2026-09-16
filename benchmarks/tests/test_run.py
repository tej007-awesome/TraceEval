import pytest

from benchmarks.run import _outcome_from_result, _sentinel_judge, run_gate1_only
from benchmarks.operators import apply_all
from traceeval.core.schema import AgentTrace, EDDTestCase, ToolCall


@pytest.mark.asyncio
async def test_run_gate1_only_never_triggers_sentinel_on_real_scenarios(in_order_scenario, any_order_scenario):
    """The real gate1_fault operator results all genuinely break gate 1, so the sentinel
    (which raises if evaluate_dimensions is ever reached) must never fire for them."""
    outcomes = await run_gate1_only([in_order_scenario, any_order_scenario], seed=0)
    assert outcomes  # sanity: something ran
    assert all(o.category == "gate1_fault" for o in outcomes)
    assert not any(o.sentinel_triggered for o in outcomes)
    assert all(o.actual_passed is False for o in outcomes)


@pytest.mark.asyncio
async def test_sentinel_fires_and_is_flagged_when_gate1_incorrectly_passes(monkeypatch):
    """Simulates a gate-1 regression: a 'gate1_fault' item whose mutated case/trace is
    actually clean (gate 1 legitimately passes it). run_evaluation should then proceed past
    the deterministic gates and call evaluate_dimensions, which is patched to the sentinel -
    it must raise, and the resulting outcome must be flagged via sentinel_triggered=True
    (not silently folded into an ordinary judge-error count)."""
    import traceeval.metrics.trajectory_judge as tj

    monkeypatch.setattr(tj, "evaluate_dimensions", _sentinel_judge)

    case = EDDTestCase(case_id="c1", input_prompt="p", rubric=["r"])
    trace = AgentTrace(
        session_id="s1", triggered_skills=[], executed_tools=[ToolCall(tool_name="x", args={})],
        final_output="done", total_token_cost_usd=0.01,
    )

    result = await tj.run_evaluation(case, trace, max_cost=0.10, score_threshold=0.8)

    class _FakeExpected:
        expected_passed = False
        expected_gate = "gate1"
        expected_code = None
        expected_dimension = None
        label = "simulated gate-1 regression"

    outcome = _outcome_from_result(
        result, "fake_scenario", "refunds", "wrong_arg_value", "gate1_fault", _FakeExpected(),
        k=0, latency_ms=0.0, cost_usd=0.0, retries=0, from_cache=False,
    )
    assert outcome.is_judge_error is True
    assert outcome.sentinel_triggered is True


def test_apply_all_gate1_fault_results_available_for_sentinel_test(in_order_scenario):
    # Confirms the fixture data actually exercises at least one gate1_fault operator, so the
    # "never triggers sentinel" test above isn't vacuously true.
    results = apply_all(in_order_scenario, seed=0)
    gate1_faults = [r for r in results if r.applicable and r.category == "gate1_fault"]
    assert len(gate1_faults) > 0
