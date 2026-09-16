import json
import tempfile
from pathlib import Path

import pytest

from benchmarks.run import (
    _outcome_for_gate1_decidable,
    _outcome_from_result,
    _sentinel_judge,
    run_gate1_only,
    run_judge_mode,
)
from benchmarks.operators import apply_all
from benchmarks.models import OperatorResult
from traceeval.core.schema import AgentTrace, EDDTestCase, ToolCall

_PASSING_SCORE_JSON = json.dumps({
    "intent_satisfaction": 1.0, "functional_correctness": 1.0, "trajectory_quality": 1.0,
    "cost_efficiency": 1.0, "safety_and_rai": 1.0, "reasoning": "looks good",
})


class _FakeUsage:
    prompt_tokens = 100
    completion_tokens = 50


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content, model="openai/gpt-5.6-luna"):
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()
        self.model = model


class _FakeCompletions:
    def __init__(self, call_counter, content=_PASSING_SCORE_JSON):
        self.call_counter = call_counter
        self.content = content

    async def create(self, *args, **kwargs):
        self.call_counter["n"] += 1
        return _FakeResponse(self.content)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, call_counter, content=_PASSING_SCORE_JSON):
        self.chat = _FakeChat(_FakeCompletions(call_counter, content))


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


# --- Judge mode: clean_base/gate1-benign routing, concurrency, cache determinism ---


@pytest.mark.asyncio
async def test_run_judge_mode_runs_clean_base_and_gate1_benign_through_real_judge(monkeypatch, in_order_scenario):
    from traceeval.pricing import ModelPrice
    call_counter = {"n": 0}
    monkeypatch.setattr("traceeval.core.config.get_judge_client", lambda: _FakeClient(call_counter))
    pricing = {"openai/gpt-5.6-luna-20260709": ModelPrice(input_per_1m_usd=0.20, output_per_1m_usd=1.20)}

    with tempfile.TemporaryDirectory() as tmp:
        outcomes, cost_cap_hit, returned_models = await run_judge_mode(
            [in_order_scenario], seed=0, k=1, judge_model="openai/gpt-5.6-luna-20260709",
            judge_temperature=0.0, reasoning_effort="none", max_total_cost_usd=None,
            cache_dir=Path(tmp), use_cache=True, pricing=pricing, concurrency=4,
        )

    clean_base_outcomes = [o for o in outcomes if o.operator == "clean_base"]
    assert len(clean_base_outcomes) == 1
    assert clean_base_outcomes[0].expected_gate == "gate2"
    assert clean_base_outcomes[0].gate1_passed is True
    assert clean_base_outcomes[0].actual_passed is True
    assert clean_base_outcomes[0].cost_usd > 0  # real cost was tracked, unlike the old uncached path

    gate1_benign_ops = {"extra_args_under_subset", "reorder_under_any_order", "regex_conforming_variable_value"}
    gate1_benign_outcomes = [o for o in outcomes if o.operator in gate1_benign_ops]
    assert gate1_benign_outcomes  # at least one applicable for this scenario
    for o in gate1_benign_outcomes:
        assert o.gate1_passed is True
        assert o.cost_usd > 0  # real cost tracked now, unlike the old direct/uncached branch
    assert call_counter["n"] > 0
    assert cost_cap_hit is False
    assert returned_models == ["openai/gpt-5.6-luna"]


@pytest.mark.asyncio
async def test_run_judge_mode_cache_hits_identical_regardless_of_concurrency(monkeypatch, in_order_scenario):
    call_counter = {"n": 0}
    monkeypatch.setattr("traceeval.core.config.get_judge_client", lambda: _FakeClient(call_counter))

    with tempfile.TemporaryDirectory() as tmp:
        cache_dir = Path(tmp)
        # First run populates the cache.
        outcomes_serial, _, _ = await run_judge_mode(
            [in_order_scenario], seed=0, k=1, judge_model="openai/gpt-5.6-luna-20260709",
            judge_temperature=0.0, reasoning_effort="none", max_total_cost_usd=None,
            cache_dir=cache_dir, use_cache=True, pricing={}, concurrency=1,
        )
        calls_after_first_run = call_counter["n"]
        assert calls_after_first_run > 0

        # Second run: everything should be a cache hit, regardless of concurrency - no new
        # calls, and the resulting verdicts must match the first run exactly.
        outcomes_concurrent, _, _ = await run_judge_mode(
            [in_order_scenario], seed=0, k=1, judge_model="openai/gpt-5.6-luna-20260709",
            judge_temperature=0.0, reasoning_effort="none", max_total_cost_usd=None,
            cache_dir=cache_dir, use_cache=True, pricing={}, concurrency=8,
        )
        assert call_counter["n"] == calls_after_first_run  # no new judge calls at all

    def _key(o):
        return (o.scenario_id, o.operator, o.k)

    serial_by_key = {_key(o): o for o in outcomes_serial}
    concurrent_by_key = {_key(o): o for o in outcomes_concurrent}
    assert set(serial_by_key) == set(concurrent_by_key)
    for key, o_serial in serial_by_key.items():
        o_concurrent = concurrent_by_key[key]
        assert o_serial.actual_passed == o_concurrent.actual_passed
        assert o_serial.actual_codes == o_concurrent.actual_codes
        if o_concurrent.category != "gate1_fault":
            # gate1_fault items (Phase 1) are deliberately never cached - only the real
            # judge-calling items (Phase 2) should be cache hits on the second run.
            assert o_concurrent.from_cache is True


@pytest.mark.asyncio
async def test_run_judge_mode_respects_cost_cap(monkeypatch, in_order_scenario, any_order_scenario):
    call_counter = {"n": 0}
    monkeypatch.setattr("traceeval.core.config.get_judge_client", lambda: _FakeClient(call_counter))

    with tempfile.TemporaryDirectory() as tmp:
        # _FakeUsage is 100 prompt / 50 completion tokens; at $10,000/1M each way that's
        # exactly $1.50/call - concurrency=1 makes call ordering deterministic, so a $1.50
        # cap allows exactly the first call through and blocks every subsequent one.
        from traceeval.pricing import ModelPrice
        pricing = {"openai/gpt-5.6-luna-20260709": ModelPrice(input_per_1m_usd=10_000, output_per_1m_usd=10_000)}
        outcomes, cost_cap_hit, _ = await run_judge_mode(
            [in_order_scenario, any_order_scenario], seed=0, k=3, judge_model="openai/gpt-5.6-luna-20260709",
            judge_temperature=0.0, reasoning_effort="none", max_total_cost_usd=1.5,
            cache_dir=Path(tmp), use_cache=True, pricing=pricing, concurrency=1,
        )

    assert cost_cap_hit is True
    assert call_counter["n"] == 1
    real_gate2_outcomes = [o for o in outcomes if o.gate1_passed and not o.from_cache]
    assert len(real_gate2_outcomes) == 1
    assert real_gate2_outcomes[0].cost_usd == 1.5
