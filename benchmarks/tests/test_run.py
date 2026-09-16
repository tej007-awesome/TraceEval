import pytest

from benchmarks.run import _outcome_for_gate1_decidable, _outcome_from_result, _sentinel_judge, run_gate1_only
from benchmarks.operators import apply_all
from benchmarks.models import OperatorResult
from traceeval.core.schema import AgentTrace, EDDTestCase, ToolCall


@pytest.mark.asyncio
async def test_run_gate1_only_never_triggers_sentinel_for_faults(in_order_scenario, any_order_scenario):
    """gate1_fault operator results all genuinely break gate 1, so the sentinel (which
    raises if evaluate_dimensions is ever reached) must never fire for them."""
    outcomes = await run_gate1_only([in_order_scenario, any_order_scenario], seed=0)
    fault_outcomes = [o for o in outcomes if o.category == "gate1_fault"]
    assert fault_outcomes  # sanity: something ran
    assert not any(o.sentinel_triggered for o in fault_outcomes)
    assert all(o.actual_passed is False for o in fault_outcomes)


@pytest.mark.asyncio
async def test_run_gate1_only_includes_clean_base_and_reports_it_as_passing(in_order_scenario, any_order_scenario):
    """The clean, unmutated base trace must also run (a false-positive check): gate 1
    legitimately passes it, so it reaches the sentinel, which must be interpreted as the
    CORRECT outcome (actual_passed=True), not an error."""
    outcomes = await run_gate1_only([in_order_scenario, any_order_scenario], seed=0)
    clean_bases = [o for o in outcomes if o.operator == "clean_base"]
    assert len(clean_bases) == 2  # one per scenario
    for o in clean_bases:
        assert o.category == "benign"
        assert o.expected_passed is True
        assert o.actual_passed is True
        assert o.sentinel_triggered is True
        assert o.is_judge_error is False


@pytest.mark.asyncio
async def test_run_gate1_only_includes_gate1_benign_controls_as_passing(in_order_scenario, any_order_scenario):
    """extra_args_under_subset / reorder_under_any_order / regex_conforming_variable_value
    are gate-1-decidable benign controls: they must run in --gate1-only mode and be reported
    as passing (sentinel firing = gate 1 correctly did NOT flag them)."""
    outcomes = await run_gate1_only([in_order_scenario, any_order_scenario], seed=0)
    gate1_benign_ops = {"extra_args_under_subset", "reorder_under_any_order", "regex_conforming_variable_value"}
    benign_outcomes = [o for o in outcomes if o.operator in gate1_benign_ops]
    assert benign_outcomes  # sanity: at least one of these is applicable across the 2 scenarios
    for o in benign_outcomes:
        assert o.category == "benign"
        assert o.expected_passed is True
        assert o.actual_passed is True


@pytest.mark.asyncio
async def test_run_gate1_only_excludes_gate2_only_operators(in_order_scenario, any_order_scenario):
    """gate2_fault operators and the paraphrase benign control need a real judge and must
    never be run against the sentinel in --gate1-only mode."""
    outcomes = await run_gate1_only([in_order_scenario, any_order_scenario], seed=0)
    gate2_only_ops = {
        "incorrect_final_answer", "rubric_item_ignored", "unsafe_content_in_output",
        "hallucinated_action", "paraphrased_but_correct_final_answer",
    }
    assert not any(o.operator in gate2_only_ops for o in outcomes)


def test_outcome_for_gate1_decidable_treats_sentinel_as_pass():
    class _FakeFailureReason:
        code = None
        dimension = None
        message = "SENTINEL: evaluate_dimensions was invoked"

        def __init__(self):
            from traceeval.core.schema import FailureCode
            self.code = FailureCode.JUDGE_ERROR

    class _FakeResult:
        passed = False
        failure_details = [_FakeFailureReason()]

    expected = OperatorResult(
        scenario_id="s", domain="refunds", operator="extra_args_under_subset", category="benign",
        applicable=True, expected_passed=True, expected_gate="gate1", label="test",
    )
    outcome = _outcome_for_gate1_decidable(_FakeResult(), "s", "refunds", "extra_args_under_subset", "benign", expected, latency_ms=1.0)
    assert outcome.actual_passed is True
    assert outcome.sentinel_triggered is True
    assert outcome.is_judge_error is False
    assert outcome.actual_codes == []


def test_outcome_for_gate1_decidable_treats_real_gate1_failure_as_false_positive():
    from traceeval.core.schema import FailureCode

    class _FakeFailureReason:
        code = FailureCode.ARG_MISMATCH
        dimension = None
        message = "step 0: expected x, got y"

    class _FakeResult:
        passed = False
        failure_details = [_FakeFailureReason()]

    expected = OperatorResult(
        scenario_id="s", domain="refunds", operator="clean_base", category="benign",
        applicable=True, expected_passed=True, expected_gate="gate1", label="test",
    )
    outcome = _outcome_for_gate1_decidable(_FakeResult(), "s", "refunds", "clean_base", "benign", expected, latency_ms=1.0)
    assert outcome.actual_passed is False  # a real false positive, not sentinel-related
    assert outcome.sentinel_triggered is False


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
        expected_dimensions = []
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
