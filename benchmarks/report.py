"""Markdown report generator: purely a function of a results.json file, so it's
regenerable and diffable - never hand-edited.

Usage: python -m benchmarks.report benchmarks/results.json [--output benchmarks/report.md]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from benchmarks.holdout import load_holdout
from benchmarks.metrics import (
    compute_gate1_fp_metrics,
    compute_operator_metrics,
    flip_rate_by_scenario_operator,
    gate1_share_of_detections,
    judge_error_rate_by_operator,
    list_false_positives,
    list_gate2_misses,
    mean_cost_and_latency,
)
from benchmarks.models import EvalOutcome


def _fmt_wilson(w) -> str:
    return f"{w.point:.0%} [{w.low:.0%}, {w.high:.0%}] (n={w.n})"


def _fmt_pct(x: float) -> str:
    return f"{x:.0%}"


def _build_section(outcomes: List[EvalOutcome], config: dict) -> List[str]:
    """All the per-operator/detail tables for one set of outcomes (dev or holdout)."""
    lines: List[str] = []

    if not outcomes:
        lines.append("_No outcomes in this split._")
        lines.append("")
        return lines

    sentinel_hits = [o for o in outcomes if o.category == "gate1_fault" and o.sentinel_triggered]
    if sentinel_hits:
        lines.append("#### ⚠️ Gate-1 short-circuit regressions")
        lines.append("")
        lines.append(
            "The following gate1_fault items reached the judge (sentinel fired) instead of "
            "short-circuiting at gate 1 as expected. This indicates a real regression, not a "
            "benign judge error, and is reported separately from the judge-error-rate table."
        )
        lines.append("")
        lines.append("| Scenario | Operator | Expected code |")
        lines.append("|---|---|---|")
        for o in sentinel_hits:
            lines.append(f"| {o.scenario_id} | {o.operator} | {o.expected_code} |")
        lines.append("")

    # Split hallucinated_action into its own table per the descoping caveat: it's the only
    # gate-2 fault operator that gate 1 can never see (it mutates executed_tools to remove a
    # "soft" action while gate 1's trajectory check doesn't require that tool at all), so its
    # numbers aren't directly comparable to the other gate-2 fault operators.
    hallucinated = [o for o in outcomes if o.operator == "hallucinated_action"]
    fault_outcomes = [o for o in outcomes if o.operator != "hallucinated_action" and o.category != "benign"]
    benign_outcomes = [o for o in outcomes if o.category == "benign"]

    lines.append("#### Per-operator detection rates (faults)")
    lines.append("")
    lines.append(
        "Gate-1 fault metrics are a regression guard on deterministic code, not a headline "
        "accuracy claim (see the benchmark plan). JUDGE_ERROR outcomes are excluded from "
        "these rates and reported separately below."
    )
    lines.append("")
    lines.append("| Operator | Category | n | Detection rate (95% CI) | Code/dimension attribution |")
    lines.append("|---|---|---|---|---|")
    for m in compute_operator_metrics(fault_outcomes):
        lines.append(f"| {m.operator} | {m.category} | {m.n} | {_fmt_wilson(m.detection_rate)} | {_fmt_wilson(m.code_attribution_rate)} |")
    lines.append("")

    lines.append("#### Gate-1 false-positive rate")
    lines.append("")
    lines.append(
        "Does GATE 1 ALONE incorrectly flag something that should pass, independent of what "
        "the judge does afterward? Uses gate1_passed (derived from actual_codes - False only "
        "when a real gate-1 failure code is present), not the final pipeline verdict. "
        "`clean_base` is the scenario's unmutated trace, judged at k repeats in judge mode "
        "(gate 1 should always pass it by construction). A benign item that gate 1 correctly "
        "passed but the judge later flagged does NOT count here - see 'Pipeline "
        "false-positive rate' below for that."
    )
    lines.append("")
    lines.append("| Operator | n | Gate-1 FP rate (95% CI) |")
    lines.append("|---|---|---|")
    for m in compute_gate1_fp_metrics(outcomes):
        lines.append(f"| {m.operator} | {m.n} | {_fmt_wilson(m.false_positive_rate)} |")
    lines.append("")

    lines.append("#### Pipeline false-positive rate (final verdict)")
    lines.append("")
    lines.append(
        "Does the FULL pipeline (gate 1 + gate 2 combined) incorrectly fail something that "
        "should pass? This is a strictly-equal-or-higher rate than the gate-1-only table "
        "above, since every gate-1 FP is also a pipeline FP, but a benign item can additionally "
        "be flagged by the judge even when gate 1 was fine - that gap is exactly what the two "
        "tables together are meant to expose. `paraphrased_but_correct_final_answer` only "
        "appears when this run used judge mode (it needs a real judge)."
    )
    lines.append("")
    lines.append("| Operator | n | Pipeline FP rate (95% CI) |")
    lines.append("|---|---|---|")
    for m in compute_operator_metrics(benign_outcomes):
        lines.append(f"| {m.operator} | {m.n} | {_fmt_wilson(m.false_positive_rate)} |")
    lines.append("")

    fp_incidents = list_false_positives(outcomes)
    if fp_incidents:
        lines.append("#### False-positive incidents (detail)")
        lines.append("")
        lines.append("| Scenario | Operator | k | Failing gate | Codes | Dimensions |")
        lines.append("|---|---|---|---|---|---|")
        for r in fp_incidents:
            lines.append(
                f"| {r['scenario_id']} | {r['operator']} | {r['k']} | {r['failing_gate']} | "
                f"{', '.join(r['actual_codes']) or '—'} | {', '.join(r['actual_below_threshold_dimensions']) or '—'} |"
            )
        lines.append("")

    gate2_misses = list_gate2_misses(outcomes)
    if gate2_misses:
        lines.append("#### Gate-2 misses (detail)")
        lines.append("")
        lines.append("Fault operators the pipeline failed to catch at all (expected to fail, but passed).")
        lines.append("")
        lines.append("| Scenario | Operator | k | Expected code | Expected dimensions |")
        lines.append("|---|---|---|---|---|")
        for r in gate2_misses:
            expected_code = r["expected_code"]
            lines.append(
                f"| {r['scenario_id']} | {r['operator']} | {r['k']} | {expected_code.value if expected_code else '—'} | "
                f"{', '.join(r['expected_dimensions']) or '—'} |"
            )
        lines.append("")

    if hallucinated:
        lines.append("#### hallucinated_action (separate table — see plan caveat)")
        lines.append("")
        lines.append(
            "Reported separately: gate 1 never sees this fault by construction (the removed "
            "tool call is never in `expected_tool_calls`), so its detection rate reflects the "
            "judge alone, not the gate-1+gate-2 pipeline the other operators measure."
        )
        lines.append("")
        for m in compute_operator_metrics(hallucinated):
            lines.append(f"- n={m.n}, detection rate: {_fmt_wilson(m.detection_rate)}, attribution: {_fmt_wilson(m.code_attribution_rate)}")
        lines.append("")

    judge_error_rates = judge_error_rate_by_operator(outcomes)
    if judge_error_rates:
        lines.append("#### Judge error rate by operator")
        lines.append("")
        lines.append("| Operator | Error rate (95% CI) |")
        lines.append("|---|---|")
        for op, w in judge_error_rates.items():
            lines.append(f"| {op} | {_fmt_wilson(w)} |")
        lines.append("")

    g1 = gate1_share_of_detections(outcomes)
    lines.append("#### Gate-1 contribution")
    lines.append("")
    lines.append(f"- Total detections: {g1['total_detections']}")
    lines.append(f"- Caught by gate 1 alone: {g1['gate1_detections']} ({_fmt_pct(g1['gate1_share'])})")
    lines.append(f"- LLM calls avoided by gate-1 short-circuit: {g1['llm_calls_avoided_by_gate1_short_circuit']}")
    lines.append("")

    if not config.get("gate1_only"):
        flip = flip_rate_by_scenario_operator(outcomes)
        lines.append("#### Judge flip rate (k repeats)")
        lines.append("")
        lines.append(f"- Scenario/operator groups with k≥2 judged: {flip['groups_with_k_gte_2']}")
        lines.append(f"- Groups with a non-unanimous verdict: {flip['groups_with_a_flip']} ({_fmt_pct(flip['flip_rate'])})")
        lines.append("")

        cost = mean_cost_and_latency(outcomes)
        lines.append("#### Judge cost / latency")
        lines.append("")
        lines.append(f"- Judged items (excluding cache hits): {cost['n']}")
        lines.append(f"- Mean cost per judged item: ${cost['mean_cost_usd']:.6f}")
        lines.append(f"- Mean latency per judged item: {cost['mean_latency_ms']:.0f} ms")
        lines.append("")

    return lines


def build_report(payload: dict) -> str:
    config = payload["config"]
    all_outcomes = [EvalOutcome.model_validate(o) for o in payload["outcomes"]]
    holdout_ids = set(load_holdout())

    dev_outcomes = [o for o in all_outcomes if o.scenario_id not in holdout_ids]
    holdout_outcomes = [o for o in all_outcomes if o.scenario_id in holdout_ids]

    lines: List[str] = []
    lines.append("# TraceEval meta-evaluation benchmark report")
    lines.append("")
    lines.append("## Config")
    lines.append("")
    for key, val in config.items():
        lines.append(f"- **{key}**: {val}")
    lines.append(f"- **n_outcomes**: {len(all_outcomes)}")
    lines.append(f"- **dev_outcomes**: {len(dev_outcomes)}")
    lines.append(f"- **holdout_outcomes**: {len(holdout_outcomes)}")
    lines.append("")

    lines.append("## Dev scenarios")
    lines.append("")
    lines.append(
        "Metrics over every scenario NOT in `benchmarks/holdout.json` - this is what most "
        "runs report, since holdout is excluded by default (`--include-holdout` to include it)."
    )
    lines.append("")
    lines.extend(_build_section(dev_outcomes, config))

    lines.append("## Holdout scenarios")
    lines.append("")
    if holdout_outcomes:
        lines.append(
            "Metrics over the 5 holdout scenarios (one per domain, `benchmarks/holdout.json`), "
            "which were never used to tune operators, scenario content, or judge config - a "
            "basic check against overfitting the benchmark to itself."
        )
        lines.append("")
        lines.extend(_build_section(holdout_outcomes, config))
    else:
        lines.append(
            "No holdout outcomes in this run - holdout scenarios are excluded by default. "
            "Rerun with `--include-holdout` to include them."
        )
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate a markdown report from a benchmark results.json")
    parser.add_argument("results_file", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    payload = json.loads(args.results_file.read_text(encoding="utf-8"))
    report = build_report(payload)

    output = args.output or args.results_file.with_suffix(".md")
    output.write_text(report, encoding="utf-8")
    print(f"Wrote report to {output}")


if __name__ == "__main__":
    main()
