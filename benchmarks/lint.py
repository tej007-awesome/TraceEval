"""Scenario data-quality lint checks (separate from operator/harness correctness - these
check the authored scenario JSON files themselves, not the code that runs them).

Usage: python -m benchmarks.lint [--scenarios-dir DIR]
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List

from traceeval.core.schema import ArgMatchMode

from benchmarks.models import Scenario

_FLAGGED_MODES = (ArgMatchMode.REGEX, ArgMatchMode.ANY)


def find_hardcoded_regex_any_values(scenarios: List[Scenario]) -> List[Dict]:
    """For every expected call field whose effective mode is REGEX or ANY, find the clean
    trace's literal value for that field and check whether it appears verbatim in the
    scenario's rubric text. A REGEX/ANY field is one whose VALUE is deliberately allowed to
    vary (that's the point of those modes) - a rubric that hardcodes one specific value
    contradicts that and will make any legitimate value-varying mutation
    (regex_conforming_variable_value) look like a real failure to the judge, when it's
    actually a scenario-authoring bug."""
    violations: List[Dict] = []
    for scenario in scenarios:
        rubric_text = " ".join(scenario.case.rubric)
        for expected in scenario.case.expected_tool_calls:
            for key in expected.args:
                mode = expected.field_overrides.get(key, expected.arg_match_mode)
                if mode not in _FLAGGED_MODES:
                    continue
                for tc in scenario.trace.executed_tools:
                    if tc.tool_name != expected.tool_name or key not in tc.args:
                        continue
                    literal = str(tc.args[key])
                    if literal and literal in rubric_text:
                        violations.append({
                            "scenario_id": scenario.id,
                            "tool_name": expected.tool_name,
                            "field": key,
                            "mode": mode.value,
                            "literal_value": literal,
                        })
    return violations


def main():
    parser = argparse.ArgumentParser(description="Run scenario data-quality lint checks")
    parser.add_argument("--scenarios-dir", type=Path, default=Path("benchmarks/scenarios"))
    args = parser.parse_args()

    from benchmarks.run import load_scenarios  # local import: avoid a module-level cycle

    scenarios = load_scenarios(args.scenarios_dir)
    violations = find_hardcoded_regex_any_values(scenarios)
    if not violations:
        print("No hardcoded REGEX/ANY values found in rubric text.")
        return
    print(f"{len(violations)} violation(s):")
    for v in violations:
        print(f"  {v['scenario_id']}: {v['tool_name']}.{v['field']} ({v['mode']}) = {v['literal_value']!r}")


if __name__ == "__main__":
    main()
