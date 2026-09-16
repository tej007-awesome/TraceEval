from benchmarks.metrics import (
    _is_correct_attribution,
    compute_gate1_fp_metrics,
    compute_operator_metrics,
    gate1_share_of_detections,
    is_gate1_false_positive,
    judge_error_rate_by_operator,
    list_false_positives,
    list_gate2_misses,
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


def _outcome(operator, category, expected_passed, actual_passed, expected_code=None, actual_codes=None,
             is_judge_error=False, gate1_passed=True):
    return EvalOutcome(
        scenario_id="s", domain="refunds", operator=operator, category=category,
        expected_passed=expected_passed, expected_code=expected_code,
        actual_passed=actual_passed, actual_codes=actual_codes or [], is_judge_error=is_judge_error,
        gate1_passed=gate1_passed,
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
    # wrong_arg_value: gate 1 caught it alone (gate1_passed=False). incorrect_final_answer:
    # gate 1 passed and gate 2 (the judge) caught it (gate1_passed=True).
    outcomes = [
        _outcome("wrong_arg_value", "gate1_fault", False, False, gate1_passed=False),
        _outcome("incorrect_final_answer", "gate2_fault", False, False, gate1_passed=True),
    ]
    result = gate1_share_of_detections(outcomes)
    assert result["total_detections"] == 2
    assert result["gate1_detections"] == 1
    assert result["gate1_share"] == 0.5


def test_judge_error_rate_by_operator_only_counts_items_that_reached_judge():
    # wrong_arg_value correctly short-circuited at gate 1 (gate1_passed=False) - never
    # reached a real judge call, so it must not appear in the error-rate table at all.
    o1 = _outcome("wrong_arg_value", "gate1_fault", False, False, gate1_passed=False)
    o2 = _outcome("incorrect_final_answer", "gate2_fault", False, False, is_judge_error=True, gate1_passed=True)
    rates = judge_error_rate_by_operator([o1, o2])
    assert "wrong_arg_value" not in rates
    assert rates["incorrect_final_answer"].point == 1.0


def test_judge_error_rate_by_operator_includes_gate1_benign_when_it_actually_reached_judge():
    # In judge mode, clean_base and the gate-1-decidable benign controls DO make a real
    # judge call once gate 1 passes them (gate1_passed=True) - they must appear here,
    # reflecting real judge-call outcomes, not be excluded just because of their category.
    clean_base = _outcome("clean_base", "benign", True, True, gate1_passed=True)
    benign = _outcome("extra_args_under_subset", "benign", True, True, gate1_passed=True)
    rates = judge_error_rate_by_operator([clean_base, benign])
    assert set(rates.keys()) == {"clean_base", "extra_args_under_subset"}
    assert rates["clean_base"].point == 0.0


def test_judge_error_rate_by_operator_excludes_gate1_benign_when_never_reached_judge():
    # e.g. --gate1-only mode reinterpretation: gate1_passed still True there when the
    # sentinel fires (that's correct/expected), but if for some reason gate1_passed is False
    # (gate 1 itself flagged it), it must be excluded here regardless of category.
    clean_base = _outcome("clean_base", "benign", True, False, gate1_passed=False)
    rates = judge_error_rate_by_operator([clean_base])
    assert rates == {}


def _gate2_outcome(expected_dimensions, actual_below_threshold_dimensions, actual_dimensions=None):
    return EvalOutcome(
        scenario_id="s", domain="refunds", operator="rubric_item_ignored", category="gate2_fault",
        expected_passed=False, expected_gate="gate2", expected_dimensions=expected_dimensions,
        actual_passed=False,
        actual_dimensions=actual_dimensions if actual_dimensions is not None else actual_below_threshold_dimensions,
        actual_below_threshold_dimensions=actual_below_threshold_dimensions,
    )


def test_attribution_correct_when_any_expected_dimension_matches():
    o = _gate2_outcome(
        expected_dimensions=["intent_satisfaction", "functional_correctness"],
        actual_below_threshold_dimensions=["functional_correctness"],
    )
    assert _is_correct_attribution(o) is True


def test_attribution_correct_when_first_expected_dimension_matches():
    o = _gate2_outcome(
        expected_dimensions=["intent_satisfaction", "functional_correctness"],
        actual_below_threshold_dimensions=["intent_satisfaction"],
    )
    assert _is_correct_attribution(o) is True


def test_attribution_incorrect_when_no_expected_dimension_matches():
    o = _gate2_outcome(
        expected_dimensions=["intent_satisfaction", "functional_correctness"],
        actual_below_threshold_dimensions=["safety_and_rai"],
    )
    assert _is_correct_attribution(o) is False


def test_attribution_ignores_null_dimension_not_in_below_threshold_list():
    # A dimension that only shows up via JUDGE_NULL_DIMENSION (not JUDGE_BELOW_THRESHOLD)
    # must NOT count toward attribution correctness, even though it's a "detection" and even
    # though it appears in the more general actual_dimensions list.
    o = _gate2_outcome(
        expected_dimensions=["functional_correctness"],
        actual_below_threshold_dimensions=[],
        actual_dimensions=["functional_correctness"],  # only via JUDGE_NULL_DIMENSION in this scenario
    )
    assert _is_correct_attribution(o) is False


def test_compute_operator_metrics_multi_dimension_attribution_rate():
    outcomes = [
        _gate2_outcome(["intent_satisfaction", "functional_correctness"], ["functional_correctness"]),
        _gate2_outcome(["intent_satisfaction", "functional_correctness"], ["safety_and_rai"]),
    ]
    rows = compute_operator_metrics(outcomes)
    row = rows[0]
    assert row.detection_rate.point == 1.0  # both are detections (actual_passed=False, expected_passed=False)
    assert row.code_attribution_rate.point == 0.5  # only the first one's dimension matched


# --- Gate-1 vs pipeline false-positive split ---


def test_is_gate1_false_positive_true_when_gate1_itself_failed():
    o = _outcome("clean_base", "benign", True, False, gate1_passed=False)
    assert is_gate1_false_positive(o) is True


def test_is_gate1_false_positive_false_when_only_judge_failed():
    # Gate 1 passed (gate1_passed=True) but the judge flagged it anyway - a pipeline FP,
    # not a gate-1 FP.
    o = _outcome("regex_conforming_variable_value", "benign", True, False, gate1_passed=True)
    assert is_gate1_false_positive(o) is False


def test_compute_gate1_fp_metrics_excludes_judge_only_failures():
    outcomes = [
        _outcome("regex_conforming_variable_value", "benign", True, False, gate1_passed=True),  # judge-only FP
        _outcome("regex_conforming_variable_value", "benign", True, True, gate1_passed=True),   # correct pass
    ]
    rows = compute_gate1_fp_metrics(outcomes)
    row = rows[0]
    assert row.n == 2
    assert row.false_positive_rate.point == 0.0  # neither is a gate-1 FP


def test_compute_gate1_fp_metrics_counts_real_gate1_failures():
    outcomes = [
        _outcome("clean_base", "benign", True, False, gate1_passed=False),
        _outcome("clean_base", "benign", True, True, gate1_passed=True),
    ]
    rows = compute_gate1_fp_metrics(outcomes)
    row = rows[0]
    assert row.n == 2
    assert row.false_positive_rate.point == 0.5


def test_list_false_positives_distinguishes_failing_gate():
    gate1_fp = _outcome("clean_base", "benign", True, False, gate1_passed=False, actual_codes=["ARG_MISMATCH"])
    gate2_fp = _outcome("regex_conforming_variable_value", "benign", True, False, gate1_passed=True,
                         actual_codes=["JUDGE_BELOW_THRESHOLD"])
    correct_pass = _outcome("clean_base", "benign", True, True, gate1_passed=True)
    records = list_false_positives([gate1_fp, gate2_fp, correct_pass])
    assert len(records) == 2
    by_operator = {r["operator"]: r for r in records}
    assert by_operator["clean_base"]["failing_gate"] == "gate1"
    assert by_operator["regex_conforming_variable_value"]["failing_gate"] == "gate2"


def test_list_gate2_misses_only_includes_missed_faults():
    missed = _outcome("incorrect_final_answer", "gate2_fault", False, True, gate1_passed=True)
    caught = _outcome("incorrect_final_answer", "gate2_fault", False, False, gate1_passed=True)
    benign_pass = _outcome("clean_base", "benign", True, True, gate1_passed=True)
    records = list_gate2_misses([missed, caught, benign_pass])
    assert len(records) == 1
    assert records[0]["operator"] == "incorrect_final_answer"
