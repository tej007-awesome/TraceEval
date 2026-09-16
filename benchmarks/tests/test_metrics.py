from benchmarks.metrics import (
    compute_operator_metrics,
    gate1_share_of_detections,
    judge_error_rate_by_operator,
    wilson_interval,
)
from benchmarks.models import EvalOutcome


def test_wilson_interval_zero_n():
    w = wilson_interval(0, 0)
    assert w == (0.0, 0.0, 0.0, 0)


def test_wilson_interval_known_bounds():
    # 8/10 successes: point estimate 0.8, interval must contain 0.8 and be non-trivial.
    w = wilson_interval(8, 10)
    assert w.point == 0.8
    assert 0.0 <= w.low < w.point < w.high <= 1.0


def test_wilson_interval_full_success_reflects_uncertainty_at_small_n():
    # At n successes / n trials the point estimate is 1.0 and the (clamped) upper bound is
    # too, but the LOWER bound stays well below 1.0 - the interval still reflects genuine
    # uncertainty from the small sample instead of overclaiming certainty.
    w = wilson_interval(5, 5)
    assert w.point == 1.0
    assert w.high == 1.0
    assert 0.0 < w.low < 1.0


def _outcome(operator, category, expected_passed, actual_passed, expected_code=None, actual_codes=None, is_judge_error=False):
    return EvalOutcome(
        scenario_id="s", domain="refunds", operator=operator, category=category,
        expected_passed=expected_passed, expected_code=expected_code,
        actual_passed=actual_passed, actual_codes=actual_codes or [], is_judge_error=is_judge_error,
    )


def test_compute_operator_metrics_detection_and_attribution():
    outcomes = [
        _outcome("wrong_arg_value", "gate1_fault", False, False, "ARG_MISMATCH", ["ARG_MISMATCH"]),
        _outcome("wrong_arg_value", "gate1_fault", False, False, "ARG_MISMATCH", ["TRAJECTORY_STEP_MISMATCH"]),  # detected, wrong code
        _outcome("wrong_arg_value", "gate1_fault", False, True),  # missed entirely
    ]
    rows = compute_operator_metrics(outcomes)
    assert len(rows) == 1
    row = rows[0]
    assert row.n == 3
    assert row.detection_rate.point == 2 / 3
    assert row.code_attribution_rate.point == 1 / 2  # 1 of 2 detections had the right code


def test_compute_operator_metrics_excludes_judge_errors():
    outcomes = [
        _outcome("incorrect_final_answer", "gate2_fault", False, False, is_judge_error=True),
        _outcome("incorrect_final_answer", "gate2_fault", False, False, "JUDGE_BELOW_THRESHOLD", ["JUDGE_BELOW_THRESHOLD"]),
    ]
    rows = compute_operator_metrics(outcomes)
    row = rows[0]
    assert row.n == 1  # the judge-error outcome is excluded from n
    assert row.n_judge_error == 1
    assert row.detection_rate.point == 1.0


def test_compute_operator_metrics_benign_false_positive_rate():
    outcomes = [
        _outcome("extra_args_under_subset", "benign", True, True),
        _outcome("extra_args_under_subset", "benign", True, False),  # false positive
    ]
    rows = compute_operator_metrics(outcomes)
    row = rows[0]
    assert row.category == "benign"
    assert row.false_positive_rate.point == 0.5


def test_gate1_share_of_detections():
    outcomes = [
        _outcome("wrong_arg_value", "gate1_fault", False, False),
        _outcome("incorrect_final_answer", "gate2_fault", False, False),
    ]
    outcomes[0].expected_gate = "gate1"
    outcomes[1].expected_gate = "gate2"
    result = gate1_share_of_detections(outcomes)
    assert result["total_detections"] == 2
    assert result["gate1_detections"] == 1
    assert result["gate1_share"] == 0.5


def test_judge_error_rate_by_operator_only_counts_gate2_items():
    o1 = _outcome("wrong_arg_value", "gate1_fault", False, False)
    o1.expected_gate = "gate1"
    o2 = _outcome("incorrect_final_answer", "gate2_fault", False, False, is_judge_error=True)
    o2.expected_gate = "gate2"
    rates = judge_error_rate_by_operator([o1, o2])
    assert "wrong_arg_value" not in rates
    assert rates["incorrect_final_answer"].point == 1.0


def test_judge_error_rate_by_operator_excludes_gate1_benign_and_clean_base():
    # clean_base and the gate-1-decidable benign controls never make a real judge call
    # (even when the sentinel fires in --gate1-only mode, is_judge_error is forced False) -
    # they must not appear in the judge-error-rate table at all.
    clean_base = _outcome("clean_base", "benign", True, True)
    clean_base.expected_gate = "gate1"
    benign = _outcome("extra_args_under_subset", "benign", True, True)
    benign.expected_gate = "gate1"
    rates = judge_error_rate_by_operator([clean_base, benign])
    assert rates == {}
