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
    if o.expected_dimension is not None:
        return o.expected_dimension in o.actual_dimensions
    return True


def _is_false_positive(o: EvalOutcome) -> bool:
    return o.expected_passed is True and o.actual_passed is False


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


def judge_error_rate_by_operator(outcomes: List[EvalOutcome]) -> Dict[str, WilsonInterval]:
    """Only operators that actually reach a real judge call (expected_gate == 'gate2') -
    excludes clean_base and the gate-1-decidable benign controls, which never call the
    judge for real even when the sentinel fires in --gate1-only mode."""
    by_operator: Dict[str, List[EvalOutcome]] = defaultdict(list)
    for o in outcomes:
        if o.expected_gate == "gate2":
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
    gate1_detections = [o for o in detections if o.expected_gate == "gate1"]
    return {
        "total_detections": len(detections),
        "gate1_detections": len(gate1_detections),
        "gate1_share": (len(gate1_detections) / len(detections)) if detections else 0.0,
        "llm_calls_avoided_by_gate1_short_circuit": len(gate1_detections),
    }


def flip_rate_by_scenario_operator(outcomes: List[EvalOutcome]) -> Dict[str, float]:
    """For gate-2 items run at k>1: fraction of (scenario, operator) groups whose
    actual_passed verdict was NOT unanimous across all k repeats."""
    by_key: Dict[str, List[EvalOutcome]] = defaultdict(list)
    for o in outcomes:
        if o.expected_gate == "gate2" and not o.is_judge_error:
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
    judged = [o for o in outcomes if o.expected_gate == "gate2" and not o.from_cache]
    if not judged:
        return {"n": 0, "mean_cost_usd": 0.0, "mean_latency_ms": 0.0}
    return {
        "n": len(judged),
        "mean_cost_usd": sum(o.cost_usd for o in judged) / len(judged),
        "mean_latency_ms": sum(o.latency_ms for o in judged) / len(judged),
    }
