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
from typing import Dict, List, Optional, Tuple

from benchmarks.holdout import load_holdout
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


def _find_regex_diff(
    scenario: Optional[Scenario],
    mutated_case: Optional[object],
    mutated_trace: Optional[object],
) -> List[str]:
    lines: List[str] = []
    if scenario is None or mutated_case is None or mutated_trace is None:
        return lines

    swapped_arg_str = None
    old_str = None
    new_str = None
    for i, tc in enumerate(scenario.trace.executed_tools):
        if i < len(mutated_trace.executed_tools):
            m_tc = mutated_trace.executed_tools[i]
            for k, v in tc.args.items():
                if k in m_tc.args and m_tc.args[k] != v:
                    old_str = str(v)
                    new_str = str(m_tc.args[k])
                    swapped_arg_str = f"`{tc.tool_name}.{k}`: `{old_str}` -> `{new_str}`"
                    break
            if swapped_arg_str:
                break

    if not swapped_arg_str or old_str is None:
        return lines

    lines.append("**Regex value swap diff**:")
    lines.append(f"- Swapped arg: {swapped_arg_str}")

    occurrences: List[str] = []
    if old_str in mutated_case.input_prompt:
        occurrences.append("`case.input_prompt`")

    for idx, r_item in enumerate(mutated_case.rubric):
        if old_str in r_item:
            occurrences.append(f"`case.rubric[{idx}]` ({r_item})")

    for idx, etc in enumerate(mutated_case.expected_tool_calls):
        if old_str in str(etc.args) or old_str in str(etc.field_overrides):
            occurrences.append(f"`case.expected_tool_calls[{idx}]` ({etc.tool_name})")

    if old_str in str(mutated_case.forbidden_tools) or old_str in str(mutated_case.forbidden_args):
        occurrences.append("`case.forbidden_tools/forbidden_args`")

    if mutated_case.expected_skill and old_str in mutated_case.expected_skill:
        occurrences.append("`case.expected_skill`")

    if mutated_trace.session_id and old_str in mutated_trace.session_id:
        occurrences.append("`trace.session_id`")

    if old_str in str(mutated_trace.triggered_skills):
        occurrences.append("`trace.triggered_skills`")

    for idx, t_call in enumerate(mutated_trace.executed_tools):
        if old_str in str(t_call.args):
            occurrences.append(f"`trace.executed_tools[{idx}]` ({t_call.tool_name})")

    if old_str in mutated_trace.final_output:
        occurrences.append("`trace.final_output`")

    if occurrences:
        lines.append(f"- Occurrences of old value (`{old_str}`) in mutated case/trace/final_output:")
        for occ in occurrences:
            lines.append(f"  - {occ}")
    else:
        lines.append(f"- Occurrences of old value (`{old_str}`) in mutated case/trace/final_output: None")

    lines.append("")
    return lines


def _render_group_entry(
    kind: str,
    scenario_id: str,
    operator: str,
    recs: List[dict],
    case,
    trace,
    scenario: Optional[Scenario] = None,
) -> List[str]:
    lines: List[str] = []
    lines.append(f"### {kind}: {scenario_id} / {operator}")
    lines.append("")
    if operator == "regex_conforming_variable_value":
        lines.extend(_find_regex_diff(scenario, case, trace))
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

    for r in sorted(recs, key=lambda x: x["k"]):
        k_val = r["k"]
        if kind == "Pipeline FP":
            codes_str = ", ".join(r["actual_codes"]) or "—"
            dims_str = ", ".join(r["actual_below_threshold_dimensions"]) or "—"
            lines.append(f"**Repeat k={k_val}**: Failing gate: {r['failing_gate']} | Codes: {codes_str} | Dimensions: {dims_str}")
        else:
            exp_code = r["expected_code"]
            exp_code_str = exp_code.value if exp_code else "—"
            exp_dims_str = ", ".join(r["expected_dimensions"]) or "—"
            lines.append(f"**Repeat k={k_val}**: Expected code: {exp_code_str} | Expected dimensions: {exp_dims_str}")
        lines.append(f"**Judge scores (k={k_val})**: {r.get('actual_scores') or '—'}")
        lines.append(f"**Judge reasoning (k={k_val})**: {r.get('judge_reasoning') or '—'}")
        lines.append("")

    lines.append("`human_label:` [valid_fp | scenario_bug | judge_correct]")
    lines.append("")
    lines.append("`note:`")
    lines.append("")
    lines.append("---")
    lines.append("")
    return lines


def build_review_queue(
    payload: dict,
    scenarios_dir: Path,
    seed: Optional[int] = None,
    include_holdout: bool = False,
    holdout_file: Optional[Path] = None,
) -> str:
    config = payload["config"]
    seed = seed if seed is not None else config.get("seed", 0)
    outcomes = [EvalOutcome.model_validate(o) for o in payload["outcomes"]]

    if not include_holdout:
        holdout_path = holdout_file if holdout_file is not None else Path("benchmarks/holdout.json")
        holdout_ids = set(load_holdout(holdout_path))
        outcomes = [o for o in outcomes if o.scenario_id not in holdout_ids]

    scenarios = {s.id: s for s in load_scenarios(scenarios_dir)}

    fps = list_false_positives(outcomes)
    misses = list_gate2_misses(outcomes)

    fp_groups_dict: Dict[Tuple[str, str], List[dict]] = {}
    for r in fps:
        key = (r["scenario_id"], r["operator"])
        fp_groups_dict.setdefault(key, []).append(r)

    miss_groups_dict: Dict[Tuple[str, str], List[dict]] = {}
    for r in misses:
        key = (r["scenario_id"], r["operator"])
        miss_groups_dict.setdefault(key, []).append(r)

    sorted_fp_keys = sorted(fp_groups_dict.keys(), key=lambda k: (k[1], k[0]))
    sorted_miss_keys = sorted(miss_groups_dict.keys(), key=lambda k: (k[1], k[0]))

    lines: List[str] = []
    lines.append("# Human review queue")
    lines.append("")
    lines.append(
        "Every pipeline false positive and every gate-2 miss from the run below. Fill in "
        "`human_label` (`valid_fp` | `scenario_bug` | `judge_correct`) and `note` for each "
        "group - labels are intentionally left blank here, never suggested."
    )
    lines.append("")
    lines.append(f"- Source run commit: {config.get('commit_sha')}")
    lines.append(f"- Judge model: {config.get('requested_judge_model')}")
    lines.append(f"- k: {config.get('k')}")
    lines.append(f"- Pipeline FP groups: {len(sorted_fp_keys)}")
    lines.append(f"- Gate-2 miss groups: {len(sorted_miss_keys)}")
    lines.append(f"- **Total review groups: {len(sorted_fp_keys) + len(sorted_miss_keys)}**")
    lines.append("")
    lines.append("---")
    lines.append("")

    for scenario_id, operator in sorted_fp_keys:
        recs = fp_groups_dict[(scenario_id, operator)]
        scenario = scenarios.get(scenario_id)
        case, trace = (None, None)
        if scenario is not None:
            case, trace = _find_mutated(scenario, operator, seed)
        lines.extend(_render_group_entry("Pipeline FP", scenario_id, operator, recs, case, trace, scenario))

    for scenario_id, operator in sorted_miss_keys:
        recs = miss_groups_dict[(scenario_id, operator)]
        scenario = scenarios.get(scenario_id)
        case, trace = (None, None)
        if scenario is not None:
            case, trace = _find_mutated(scenario, operator, seed)
        lines.extend(_render_group_entry("Gate-2 miss", scenario_id, operator, recs, case, trace, scenario))

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate the human review queue from a benchmark results.json")
    parser.add_argument("results_file", type=Path)
    parser.add_argument("--scenarios-dir", type=Path, default=Path("benchmarks/scenarios"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/review/review_queue.md"))
    parser.add_argument("--include-holdout", action="store_true", help="Include holdout scenarios (excluded by default).")
    parser.add_argument("--holdout-file", type=Path, default=Path("benchmarks/holdout.json"))
    args = parser.parse_args()

    payload = json.loads(args.results_file.read_text(encoding="utf-8"))
    content = build_review_queue(
        payload,
        args.scenarios_dir,
        include_holdout=args.include_holdout,
        holdout_file=args.holdout_file,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"Wrote review queue to {args.output}")


if __name__ == "__main__":
    main()
