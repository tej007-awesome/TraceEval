"""Human review export: every pipeline false positive and every gate-2 miss from a
results.json, with full context (prompt, rubric, executed tools, final_output, judge
scores/reasoning) and blank human_label/note fields for manual triage.

This tool never pre-fills or suggests a label - human_label is always left as the literal
placeholder text for a person to fill in.

Usage: python -m benchmarks.review benchmarks/results.json [--scenarios-dir DIR] [--output FILE]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional, Tuple

from benchmarks.metrics import list_false_positives, list_gate2_misses
from benchmarks.models import EvalOutcome, Scenario
from benchmarks.operators import apply_all
from benchmarks.run import load_scenarios


def _find_mutated(scenario: Scenario, operator: str, seed: int) -> Tuple[Optional[object], Optional[object]]:
    """Deterministically re-derive the exact (case, trace) an outcome's operator produced,
    since EvalOutcome only stores summary fields, not the full mutated content."""
    if operator == "clean_base":
        return scenario.case, scenario.trace
    for r in apply_all(scenario, seed):
        if r.operator == operator and r.applicable:
            return r.mutated_case, r.mutated_trace
    return None, None


def _render_entry(kind: str, record: dict, case, trace) -> List[str]:
    lines: List[str] = []
    lines.append(f"### {kind}: {record['scenario_id']} / {record['operator']} (k={record['k']})")
    lines.append("")
    if case is not None:
        lines.append(f"**Prompt**: {case.input_prompt}")
        lines.append("")
        lines.append("**Rubric**:")
        for item in case.rubric:
            lines.append(f"- {item}")
        lines.append("")
    else:
        lines.append("**Prompt/rubric**: could not be re-derived (scenario file not found or operator no longer applicable)")
        lines.append("")
    if trace is not None:
        lines.append("**Executed tools**:")
        for tc in trace.executed_tools:
            lines.append(f"- `{tc.tool_name}({tc.args})`")
        lines.append("")
        lines.append(f"**Final output**: {trace.final_output}")
        lines.append("")

    if kind == "Pipeline FP":
        lines.append(f"**Failing gate**: {record['failing_gate']}")
        lines.append(f"**Codes**: {', '.join(record['actual_codes']) or '—'}")
        lines.append(f"**Dimensions**: {', '.join(record['actual_below_threshold_dimensions']) or '—'}")
    else:
        expected_code = record["expected_code"]
        lines.append(f"**Expected code**: {expected_code.value if expected_code else '—'}")
        lines.append(f"**Expected dimensions**: {', '.join(record['expected_dimensions']) or '—'}")
    lines.append("")
    lines.append(f"**Judge scores**: {record.get('actual_scores') or '—'}")
    lines.append("")
    lines.append(f"**Judge reasoning**: {record.get('judge_reasoning') or '—'}")
    lines.append("")
    lines.append("`human_label:` [valid_fp | scenario_bug | judge_correct]")
    lines.append("")
    lines.append("`note:`")
    lines.append("")
    lines.append("---")
    lines.append("")
    return lines


def build_review_queue(payload: dict, scenarios_dir: Path, seed: Optional[int] = None) -> str:
    config = payload["config"]
    seed = seed if seed is not None else config.get("seed", 0)
    outcomes = [EvalOutcome.model_validate(o) for o in payload["outcomes"]]
    scenarios = {s.id: s for s in load_scenarios(scenarios_dir)}

    fps = list_false_positives(outcomes)
    misses = list_gate2_misses(outcomes)

    lines: List[str] = []
    lines.append("# Human review queue")
    lines.append("")
    lines.append(
        "Every pipeline false positive and every gate-2 miss from the run below. Fill in "
        "`human_label` (`valid_fp` | `scenario_bug` | `judge_correct`) and `note` for each "
        "entry - labels are intentionally left blank here, never suggested."
    )
    lines.append("")
    lines.append(f"- Source run commit: {config.get('commit_sha')}")
    lines.append(f"- Judge model: {config.get('requested_judge_model')}")
    lines.append(f"- k: {config.get('k')}")
    lines.append(f"- Pipeline FPs: {len(fps)}")
    lines.append(f"- Gate-2 misses: {len(misses)}")
    lines.append(f"- **Total review items: {len(fps) + len(misses)}**")
    lines.append("")
    lines.append("---")
    lines.append("")

    for record in fps:
        scenario = scenarios.get(record["scenario_id"])
        case, trace = (None, None)
        if scenario is not None:
            case, trace = _find_mutated(scenario, record["operator"], seed)
        lines.extend(_render_entry("Pipeline FP", record, case, trace))

    for record in misses:
        scenario = scenarios.get(record["scenario_id"])
        case, trace = (None, None)
        if scenario is not None:
            case, trace = _find_mutated(scenario, record["operator"], seed)
        lines.extend(_render_entry("Gate-2 miss", record, case, trace))

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate the human review queue from a benchmark results.json")
    parser.add_argument("results_file", type=Path)
    parser.add_argument("--scenarios-dir", type=Path, default=Path("benchmarks/scenarios"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/review/review_queue.md"))
    args = parser.parse_args()

    payload = json.loads(args.results_file.read_text(encoding="utf-8"))
    content = build_review_queue(payload, args.scenarios_dir)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"Wrote review queue to {args.output}")


if __name__ == "__main__":
    main()
