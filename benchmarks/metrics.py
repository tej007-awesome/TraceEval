"""Wilson score confidence intervals and metric aggregation over a list of EvalOutcome.

No scipy/statsmodels dependency - the Wilson interval is a ~10-line closed form, and adding
a stats library for one formula would be overkill for benchmarks/ (which stays outside the
[project.optional-dependencies] surface for Phase 1a).
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, List, NamedTuple

from benchmarks.models import EvalOutcome


class WilsonInterval(NamedTuple):
    point: float
    low: float
    high: float
    n: int


def wilson_interval(successes: int, n: int, z: float = 1.96) -> WilsonInterval:
    """95% (default z=1.96) Wilson score interval for a binomial proportion."""
    if n == 0:
        return WilsonInterval(point=0.0, low=0.0, high=0.0, n=0)
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) / n) + (z**2 / (4 * n**2)))) / denom
    return WilsonInterval(point=p, low=max(0.0, center - margin), high=min(1.0, center + margin), n=n)


class OperatorMetric(NamedTuple):
    operator: str
    category: str
    n: int
    n_judge_error: int
    detection_rate: WilsonInterval  # fault operators: caught (actual_passed == expected_passed == False)
    code_attribution_rate: WilsonInterval  # of detections, how many had the exact expected code/dimension
    false_positive_rate: WilsonInterval  # benign operators: incorrectly failed (actual_passed=False when expected True)


def _is_detection(o: EvalOutcome) -> bool:
    return o.actual_passed is False and o.expected_passed is False


def _is_correct_attribution(o: EvalOutcome) -> bool:
    if not _is_detection(o):
        return False
    if o.expected_code is not None:
        return o.expected_code.value in o.actual_codes if hasattr(o.expected_code, "value") else o.expected_code in o.actual_codes
    if o.expected_dimensions:
        # Correct if the judge's JUDGE_BELOW_THRESHOLD result named ANY of the expected
        # dimensions - not just any dimension it happened to mention (e.g. JUDGE_NULL_
        # DIMENSION is a different failure mode and doesn't count toward attribution).
        return any(d in o.actual_below_threshold_dimensions for d in o.expected_dimensions)
    return True


def _is_false_positive(o: EvalOutcome) -> bool:
    """Pipeline-level false positive: the FINAL verdict (gate 1 + gate 2 combined) wrongly
    failed something that should have passed."""
    return o.expected_passed is True and o.actual_passed is False


def is_gate1_false_positive(o: EvalOutcome) -> bool:
    """Gate-1-level false positive: gate 1 ALONE wrongly failed something that should have
    passed (derived from gate1_passed, which is False only when a real gate-1 failure code
    is present in actual_codes). Every gate-1 FP is necessarily also a pipeline FP (gate 1
    failing short-circuits the whole pipeline to failed) - the reverse isn't true: a pipeline
    FP where gate1_passed is True means gate 1 was fine and gate 2 (the judge) caused it."""
    return o.expected_passed is True and o.gate1_passed is False


def compute_operator_metrics(outcomes: List[EvalOutcome]) -> List[OperatorMetric]:
    """One row per operator. JUDGE_ERROR outcomes are excluded from every rate's numerator
    AND denominator (per the amendment: they get their own separate error-rate report,
    computed alongside this one), so a flaky/retried-out judge call doesn't silently count
    as either a correct or incorrect verdict."""
    by_operator: Dict[str, List[EvalOutcome]] = defaultdict(list)
    for o in outcomes:
        by_operator[o.operator].append(o)

    rows = []
    for operator, items in sorted(by_operator.items()):
        category = items[0].category
        n_judge_error = sum(1 for o in items if o.is_judge_error)
        scored = [o for o in items if not o.is_judge_error]

        if category == "benign":
            fp = sum(1 for o in scored if _is_false_positive(o))
            rows.append(OperatorMetric(
                operator=operator, category=category, n=len(scored), n_judge_error=n_judge_error,
                detection_rate=wilson_interval(0, 0), code_attribution_rate=wilson_interval(0, 0),
                false_positive_rate=wilson_interval(fp, len(scored)),
            ))
        else:
            detections = sum(1 for o in scored if _is_detection(o))
            correct_attributions = sum(1 for o in scored if _is_correct_attribution(o))
            rows.append(OperatorMetric(
                operator=operator, category=category, n=len(scored), n_judge_error=n_judge_error,
                detection_rate=wilson_interval(detections, len(scored)),
                code_attribution_rate=wilson_interval(correct_attributions, max(detections, 0)),
                false_positive_rate=wilson_interval(0, 0),
            ))
    return rows


def compute_gate1_fp_metrics(outcomes: List[EvalOutcome]) -> List[OperatorMetric]:
    """Gate-1-ONLY false-positive rate per benign operator (including clean_base): uses
    gate1_passed instead of actual_passed, so a benign item that gate 1 correctly passed but
    the JUDGE later flagged (a real, distinct failure mode - see is_gate1_false_positive)
    does NOT count against gate 1 here. Pair with compute_operator_metrics's benign rows
    (which use actual_passed, i.e. the pipeline verdict) for the "Pipeline FP" table."""
    by_operator: Dict[str, List[EvalOutcome]] = defaultdict(list)
    for o in outcomes:
        if o.category == "benign":
            by_operator[o.operator].append(o)

    rows = []
    for operator, items in sorted(by_operator.items()):
        n_judge_error = sum(1 for o in items if o.is_judge_error)
        scored = [o for o in items if not o.is_judge_error]
        fp = sum(1 for o in scored if is_gate1_false_positive(o))
        rows.append(OperatorMetric(
            operator=operator, category="benign", n=len(scored), n_judge_error=n_judge_error,
            detection_rate=wilson_interval(0, 0), code_attribution_rate=wilson_interval(0, 0),
            false_positive_rate=wilson_interval(fp, len(scored)),
        ))
    return rows


def list_false_positives(outcomes: List[EvalOutcome]) -> List[Dict]:
    """One record per false positive (gate-1 or pipeline), with which gate is at fault and
    the codes/dimensions/reasoning involved, for direct inspection rather than only an
    aggregate rate."""
    records = []
    for o in outcomes:
        if o.expected_passed is not True or o.actual_passed:
            continue
        # If gate 1 failed, the whole pipeline necessarily failed too (short-circuit) - so
        # "gate1" is the correct attribution whenever gate1_passed is False; otherwise gate 1
        # was fine and gate 2 (the judge) is what caused the false positive.
        failing_gate = "gate1" if not o.gate1_passed else "gate2"
        records.append({
            "scenario_id": o.scenario_id, "operator": o.operator, "k": o.k,
            "failing_gate": failing_gate,
            "actual_codes": o.actual_codes,
            "actual_below_threshold_dimensions": o.actual_below_threshold_dimensions,
            "judge_reasoning": o.judge_reasoning,
            "actual_scores": o.actual_scores,
        })
    return records


def list_gate2_misses(outcomes: List[EvalOutcome]) -> List[Dict]:
    """One record per gate-2 miss: a fault operator (any category) that the pipeline failed
    to catch (expected_passed=False, actual_passed=True), with judge reasoning/scores."""
    records = []
    for o in outcomes:
        if o.expected_passed is not False or not o.actual_passed:
            continue
        records.append({
            "scenario_id": o.scenario_id, "operator": o.operator, "k": o.k,
            "expected_code": o.expected_code, "expected_dimensions": o.expected_dimensions,
            "judge_reasoning": o.judge_reasoning, "actual_scores": o.actual_scores,
        })
    return records


def judge_error_rate_by_operator(outcomes: List[EvalOutcome]) -> Dict[str, WilsonInterval]:
    """Only operators/items that actually reached a real judge call (gate1_passed=True) -
    excludes gate1_fault items that correctly short-circuited at gate 1."""
    by_operator: Dict[str, List[EvalOutcome]] = defaultdict(list)
    for o in outcomes:
        if o.gate1_passed:
            by_operator[o.operator].append(o)
    return {
        op: wilson_interval(sum(1 for o in items if o.is_judge_error), len(items))
        for op, items in sorted(by_operator.items())
    }


def gate1_share_of_detections(outcomes: List[EvalOutcome]) -> Dict[str, float]:
    """What fraction of all successful detections came from gate 1 alone (no LLM call
    needed), and how many LLM calls that avoided."""
    fault_outcomes = [o for o in outcomes if o.expected_passed is False and not o.is_judge_error]
    detections = [o for o in fault_outcomes if _is_detection(o)]
    gate1_detections = [o for o in detections if not o.gate1_passed]
    return {
        "total_detections": len(detections),
        "gate1_detections": len(gate1_detections),
        "gate1_share": (len(gate1_detections) / len(detections)) if detections else 0.0,
        "llm_calls_avoided_by_gate1_short_circuit": len(gate1_detections),
    }


def flip_rate_by_scenario_operator(outcomes: List[EvalOutcome]) -> Dict[str, float]:
    """For items that reached a real judge call, run at k>1: fraction of (scenario,
    operator) groups whose actual_passed verdict was NOT unanimous across all k repeats."""
    by_key: Dict[str, List[EvalOutcome]] = defaultdict(list)
    for o in outcomes:
        if o.gate1_passed and not o.is_judge_error:
            by_key[f"{o.scenario_id}::{o.operator}"].append(o)
    flipped = 0
    total = 0
    for key, items in by_key.items():
        if len(items) < 2:
            continue
        total += 1
        verdicts = {o.actual_passed for o in items}
        if len(verdicts) > 1:
            flipped += 1
    return {"groups_with_k_gte_2": total, "groups_with_a_flip": flipped, "flip_rate": (flipped / total) if total else 0.0}


def mean_cost_and_latency(outcomes: List[EvalOutcome]) -> Dict[str, float]:
    judged = [o for o in outcomes if o.gate1_passed and not o.from_cache]
    if not judged:
        return {"n": 0, "mean_cost_usd": 0.0, "mean_latency_ms": 0.0}
    return {
        "n": len(judged),
        "mean_cost_usd": sum(o.cost_usd for o in judged) / len(judged),
        "mean_latency_ms": sum(o.latency_ms for o in judged) / len(judged),
    }
