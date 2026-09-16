"""Fault operators and benign controls: pure, seeded functions over a loaded Scenario.

Each operator is `(scenario: Scenario, rng: random.Random) -> OperatorResult`. Gate-1
operators mutate the trace/case structurally and predict a FailureCode by hand-reasoning
about the matching engine's documented semantics (src/traceeval/metrics/trajectory_judge.py)
- they never call validate_trajectory/etc. to derive their prediction, since using the same
code under test to generate its own ground truth would make detection-rate metrics
tautological. Gate-2 operators only ever select and apply a hand-authored Gate2Variant from
the scenario file (see scenarios/AUTHORING.md) - they never synthesize text.
"""
from __future__ import annotations

import hashlib
import random
import re
from typing import Callable, List, Optional, Tuple

from traceeval.core.schema import ArgMatchMode, EDDTestCase, ExpectedToolCall, FailureCode, ToolCall, TrajectoryMode

from benchmarks.models import OperatorResult, Scenario


def derive_seed(seed: int, *parts: str) -> int:
    """Deterministically derive a per-(scenario, operator[, k]) integer seed from a base
    seed, independent of Python's hash randomization (unlike random.Random(str))."""
    key = f"{seed}:" + ":".join(parts)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _inapplicable(scenario: Scenario, operator: str, category: str, reason: str) -> OperatorResult:
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=operator, category=category,
        applicable=False, inapplicable_reason=reason,
    )


def _effective_mode(call: ExpectedToolCall, key: str) -> ArgMatchMode:
    return call.field_overrides.get(key, call.arg_match_mode)


def _find_expected(case: EDDTestCase, tool_name: str) -> Optional[ExpectedToolCall]:
    return next((tc for tc in case.expected_tool_calls if tc.tool_name == tool_name), None)


def _value_sensitive_keys(expected: ExpectedToolCall) -> List[str]:
    """Keys whose effective mode is EXACT or SUBSET (value equality matters - mutating
    these is guaranteed to break the match). ANY ignores the value; REGEX needs a
    non-conforming value, which type_changed_arg/wrong_arg_value don't attempt to construct."""
    return [k for k in expected.args if _effective_mode(expected, k) in (ArgMatchMode.EXACT, ArgMatchMode.SUBSET)]


def _mutate_scalar(val, rng: random.Random):
    if isinstance(val, bool):
        return not val
    if isinstance(val, (int, float)):
        return val + 1_000_000
    if isinstance(val, str):
        return val + "_bench_mut"
    return f"{val}_bench_mut"


# --- Gate-1 fault operators ---------------------------------------------------------


def wrong_arg_value(scenario: Scenario, rng: random.Random) -> OperatorResult:
    name = "wrong_arg_value"
    trace = scenario.trace.model_copy(deep=True)
    candidates: List[Tuple[int, str]] = []
    for i, tc in enumerate(trace.executed_tools):
        expected = _find_expected(scenario.case, tc.tool_name)
        if expected is None:
            continue
        for key in _value_sensitive_keys(expected):
            if key in tc.args:
                candidates.append((i, key))
    if not candidates:
        return _inapplicable(scenario, name, "gate1_fault", "no executed call has a value-sensitive (EXACT/SUBSET) arg to mutate")
    idx, key = rng.choice(sorted(candidates))
    old_val = trace.executed_tools[idx].args[key]
    new_val = _mutate_scalar(old_val, rng)
    trace.executed_tools[idx].args[key] = new_val
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=name, category="gate1_fault", applicable=True,
        mutated_case=scenario.case, mutated_trace=trace,
        expected_passed=False, expected_gate="gate1", expected_code=FailureCode.ARG_MISMATCH,
        label=f"{trace.executed_tools[idx].tool_name}.{key}: {old_val!r} -> {new_val!r}",
    )


def type_changed_arg(scenario: Scenario, rng: random.Random) -> OperatorResult:
    name = "type_changed_arg"
    trace = scenario.trace.model_copy(deep=True)
    candidates: List[Tuple[int, str]] = []
    for i, tc in enumerate(trace.executed_tools):
        expected = _find_expected(scenario.case, tc.tool_name)
        if expected is None:
            continue
        for key in _value_sensitive_keys(expected):
            val = tc.args.get(key)
            if isinstance(val, str) and val.lstrip("-").isdigit():
                candidates.append((i, key))
            elif isinstance(val, (int, float)) and not isinstance(val, bool):
                candidates.append((i, key))
    if not candidates:
        return _inapplicable(scenario, name, "gate1_fault", "no executed call has a numeric-or-numeric-string value-sensitive arg")
    idx, key = rng.choice(sorted(candidates))
    old_val = trace.executed_tools[idx].args[key]
    new_val = str(old_val) if isinstance(old_val, (int, float)) else int(old_val)
    trace.executed_tools[idx].args[key] = new_val
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=name, category="gate1_fault", applicable=True,
        mutated_case=scenario.case, mutated_trace=trace,
        expected_passed=False, expected_gate="gate1", expected_code=FailureCode.ARG_MISMATCH,
        label=f"{trace.executed_tools[idx].tool_name}.{key}: {old_val!r} ({type(old_val).__name__}) -> {new_val!r} ({type(new_val).__name__})",
    )


def missing_required_arg(scenario: Scenario, rng: random.Random) -> OperatorResult:
    name = "missing_required_arg"
    trace = scenario.trace.model_copy(deep=True)
    candidates: List[Tuple[int, str]] = []
    for i, tc in enumerate(trace.executed_tools):
        expected = _find_expected(scenario.case, tc.tool_name)
        if expected is None:
            continue
        for key in expected.args:
            if key in tc.args:
                candidates.append((i, key))
    if not candidates:
        return _inapplicable(scenario, name, "gate1_fault", "no executed call has an expected arg key to remove")
    idx, key = rng.choice(sorted(candidates))
    old_val = trace.executed_tools[idx].args.pop(key)
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=name, category="gate1_fault", applicable=True,
        mutated_case=scenario.case, mutated_trace=trace,
        expected_passed=False, expected_gate="gate1", expected_code=FailureCode.ARG_MISMATCH,
        label=f"removed {trace.executed_tools[idx].tool_name}.{key} (was {old_val!r})",
    )


def skipped_step(scenario: Scenario, rng: random.Random) -> OperatorResult:
    name = "skipped_step"
    if len(scenario.case.expected_tool_calls) < 2:
        return _inapplicable(scenario, name, "gate1_fault", "fewer than 2 expected_tool_calls")
    trace = scenario.trace.model_copy(deep=True)
    expected_names = {tc.tool_name for tc in scenario.case.expected_tool_calls}
    candidates = [i for i, tc in enumerate(trace.executed_tools) if tc.tool_name in expected_names]
    if not candidates:
        return _inapplicable(scenario, name, "gate1_fault", "no executed call matches an expected tool_name")
    idx = rng.choice(sorted(candidates))
    removed = trace.executed_tools.pop(idx)
    mode = scenario.case.trajectory_mode
    expected_code = {
        TrajectoryMode.EXACT: FailureCode.TRAJECTORY_LENGTH_MISMATCH,
        TrajectoryMode.IN_ORDER: FailureCode.TOOL_CALL_NEVER_CALLED,
        TrajectoryMode.ANY_ORDER: FailureCode.TOOL_CALL_NOT_FOUND,
    }[mode]
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=name, category="gate1_fault", applicable=True,
        mutated_case=scenario.case, mutated_trace=trace,
        expected_passed=False, expected_gate="gate1", expected_code=expected_code,
        label=f"removed {removed.tool_name} (index {idx})",
    )


def swapped_order(scenario: Scenario, rng: random.Random) -> OperatorResult:
    name = "swapped_order"
    if scenario.case.trajectory_mode == TrajectoryMode.ANY_ORDER:
        return _inapplicable(scenario, name, "gate1_fault", "order doesn't matter under ANY_ORDER - see reorder_under_any_order")
    trace = scenario.trace.model_copy(deep=True)
    pairs = [
        i for i in range(len(trace.executed_tools) - 1)
        if trace.executed_tools[i].tool_name != trace.executed_tools[i + 1].tool_name
    ]
    if not pairs:
        return _inapplicable(scenario, name, "gate1_fault", "no adjacent pair of differently-named calls to swap")
    i = rng.choice(sorted(pairs))
    trace.executed_tools[i], trace.executed_tools[i + 1] = trace.executed_tools[i + 1], trace.executed_tools[i]
    mode = scenario.case.trajectory_mode
    expected_code = FailureCode.TRAJECTORY_STEP_MISMATCH if mode == TrajectoryMode.EXACT else FailureCode.TOOL_CALL_OUT_OF_ORDER
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=name, category="gate1_fault", applicable=True,
        mutated_case=scenario.case, mutated_trace=trace,
        expected_passed=False, expected_gate="gate1", expected_code=expected_code,
        label=f"swapped positions {i} and {i + 1}",
    )


def wrong_tool_substituted(scenario: Scenario, rng: random.Random) -> OperatorResult:
    name = "wrong_tool_substituted"
    trace = scenario.trace.model_copy(deep=True)
    expected_names = {tc.tool_name for tc in scenario.case.expected_tool_calls}
    # Only substitute a call that's currently satisfying an expectation - substituting an
    # already-extra/unexpected call (allowed under IN_ORDER/ANY_ORDER) changes nothing.
    candidates = [i for i, tc in enumerate(trace.executed_tools) if tc.tool_name in expected_names]
    if not candidates:
        return _inapplicable(scenario, name, "gate1_fault", "no executed call currently satisfies an expected tool_name")
    idx = rng.choice(sorted(candidates))
    original = trace.executed_tools[idx]
    substitute_name = f"{original.tool_name}_unexpected_substitute"
    trace.executed_tools[idx] = ToolCall(tool_name=substitute_name, args=original.args)
    mode = scenario.case.trajectory_mode
    expected_code = {
        TrajectoryMode.EXACT: FailureCode.TRAJECTORY_STEP_MISMATCH,
        TrajectoryMode.IN_ORDER: FailureCode.TOOL_CALL_NEVER_CALLED,
        TrajectoryMode.ANY_ORDER: FailureCode.TOOL_CALL_NOT_FOUND,
    }[mode]
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=name, category="gate1_fault", applicable=True,
        mutated_case=scenario.case, mutated_trace=trace,
        expected_passed=False, expected_gate="gate1", expected_code=expected_code,
        label=f"replaced {original.tool_name} (index {idx}) with {substitute_name}",
    )


def forbidden_tool_inserted(scenario: Scenario, rng: random.Random) -> OperatorResult:
    name = "forbidden_tool_inserted"
    if not scenario.case.forbidden_tools:
        return _inapplicable(scenario, name, "gate1_fault", "case.forbidden_tools is empty")
    trace = scenario.trace.model_copy(deep=True)
    forbidden_name = rng.choice(sorted(scenario.case.forbidden_tools))
    trace.executed_tools.append(ToolCall(tool_name=forbidden_name, args={}))
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=name, category="gate1_fault", applicable=True,
        mutated_case=scenario.case, mutated_trace=trace,
        expected_passed=False, expected_gate="gate1", expected_code=FailureCode.FORBIDDEN_TOOL_CALLED,
        label=f"inserted forbidden call {forbidden_name}",
    )


_REGEX_METACHARS = set(".^$*+?{}[]\\|()")


def _literal_for_pattern(pattern: str, rng: random.Random) -> Optional[str]:
    # Bare literal (no regex metacharacters at all, e.g. "unlimited") - use as-is; matches
    # via re.search same as the real matching engine (validate_forbidden_tools).
    if not any(c in _REGEX_METACHARS for c in pattern):
        return pattern
    # Anchored literal: ^word$
    m = re.match(r"^\^([^()|]+)\$$", pattern)
    if m:
        return m.group(1)
    # Alternation, anchored or not: ^(a|b|c)$ or (a|b|c)
    m = re.match(r"^\^?\(([^()]+)\)\$?$", pattern)
    if m:
        return rng.choice(m.group(1).split("|"))
    return None


def forbidden_args_injected(scenario: Scenario, rng: random.Random) -> OperatorResult:
    name = "forbidden_args_injected"
    trace = scenario.trace.model_copy(deep=True)
    candidates: List[Tuple[int, str, dict]] = []
    for i, tc in enumerate(trace.executed_tools):
        for ruleset in scenario.case.forbidden_args.get(tc.tool_name, []):
            values = {}
            ok = True
            for arg_name, pattern in ruleset.items():
                literal = _literal_for_pattern(pattern, rng)
                if literal is None:
                    ok = False
                    break
                values[arg_name] = literal
            if ok:
                candidates.append((i, tc.tool_name, values))
    if not candidates:
        return _inapplicable(scenario, name, "gate1_fault", "no forbidden_args ruleset with a literal/alternation pattern we can satisfy")
    idx, tool_name, values = rng.choice(candidates)
    trace.executed_tools[idx].args.update(values)
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=name, category="gate1_fault", applicable=True,
        mutated_case=scenario.case, mutated_trace=trace,
        expected_passed=False, expected_gate="gate1", expected_code=FailureCode.FORBIDDEN_ARGS,
        label=f"set {tool_name} args to forbidden combination {values}",
    )


def cost_blowout(scenario: Scenario, rng: random.Random) -> OperatorResult:
    name = "cost_blowout"
    trace = scenario.trace.model_copy(deep=True)
    trace.total_token_cost_usd = 50.0
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=name, category="gate1_fault", applicable=True,
        mutated_case=scenario.case, mutated_trace=trace,
        expected_passed=False, expected_gate="gate1", expected_code=FailureCode.COST_EXCEEDED,
        label="total_token_cost_usd set to $50.00",
    )


def cost_incomplete(scenario: Scenario, rng: random.Random) -> OperatorResult:
    name = "cost_incomplete"
    trace = scenario.trace.model_copy(deep=True)
    trace.cost_complete = False
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=name, category="gate1_fault", applicable=True,
        mutated_case=scenario.case, mutated_trace=trace,
        expected_passed=False, expected_gate="gate1", expected_code=FailureCode.COST_INCOMPLETE,
        label="cost_complete set to False",
    )


def skill_not_triggered(scenario: Scenario, rng: random.Random) -> OperatorResult:
    name = "skill_not_triggered"
    if scenario.case.expected_skill is None:
        return _inapplicable(scenario, name, "gate1_fault", "case.expected_skill is None")
    trace = scenario.trace.model_copy(deep=True)
    trace.triggered_skills = [s for s in trace.triggered_skills if s != scenario.case.expected_skill]
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=name, category="gate1_fault", applicable=True,
        mutated_case=scenario.case, mutated_trace=trace,
        expected_passed=False, expected_gate="gate1", expected_code=FailureCode.SKILL_NOT_TRIGGERED,
        label=f"removed '{scenario.case.expected_skill}' from triggered_skills",
    )


def duplicated_step(scenario: Scenario, rng: random.Random) -> OperatorResult:
    name = "duplicated_step"
    if scenario.case.trajectory_mode != TrajectoryMode.EXACT:
        return _inapplicable(scenario, name, "gate1_fault", "extra calls are allowed under IN_ORDER/ANY_ORDER - not a gate-1 fault there (see tool_call_loop, gate-2)")
    trace = scenario.trace.model_copy(deep=True)
    if not trace.executed_tools:
        return _inapplicable(scenario, name, "gate1_fault", "no executed tool calls")
    idx = rng.choice(range(len(trace.executed_tools)))
    duplicate = trace.executed_tools[idx].model_copy(deep=True)
    trace.executed_tools.insert(idx + 1, duplicate)
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=name, category="gate1_fault", applicable=True,
        mutated_case=scenario.case, mutated_trace=trace,
        expected_passed=False, expected_gate="gate1", expected_code=FailureCode.TRAJECTORY_LENGTH_MISMATCH,
        label=f"duplicated {duplicate.tool_name} (index {idx})",
    )


GATE1_OPERATORS: List[Tuple[str, Callable[[Scenario, random.Random], OperatorResult]]] = [
    ("wrong_arg_value", wrong_arg_value),
    ("type_changed_arg", type_changed_arg),
    ("missing_required_arg", missing_required_arg),
    ("skipped_step", skipped_step),
    ("swapped_order", swapped_order),
    ("wrong_tool_substituted", wrong_tool_substituted),
    ("forbidden_tool_inserted", forbidden_tool_inserted),
    ("forbidden_args_injected", forbidden_args_injected),
    ("cost_blowout", cost_blowout),
    ("cost_incomplete", cost_incomplete),
    ("skill_not_triggered", skill_not_triggered),
    ("duplicated_step", duplicated_step),
]


# --- Gate-2 fault operators (select + apply hand-authored variants only) -----------


def _select_variant(scenario: Scenario, kind: str, operator_name: str):
    matches = [v for v in scenario.gate2_variants if v.kind == kind]
    if not matches:
        return None, f"no hand-authored '{kind}' variant in this scenario file"
    if kind == "hallucinated_action" and scenario.case.trajectory_mode == TrajectoryMode.EXACT:
        return None, "soft actions require a non-EXACT trajectory_mode (extra calls aren't allowed under EXACT)"
    return matches[0], None


def _apply_gate2_variant(scenario: Scenario, operator_name: str, kind: str) -> OperatorResult:
    variant, reason = _select_variant(scenario, kind, operator_name)
    if variant is None:
        return _inapplicable(scenario, operator_name, "gate2_fault", reason)
    trace = scenario.trace.model_copy(deep=True)
    trace.final_output = variant.final_output
    if variant.soft_action_tool:
        trace.executed_tools = [tc for tc in trace.executed_tools if tc.tool_name != variant.soft_action_tool]
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=operator_name, category="gate2_fault", applicable=True,
        mutated_case=scenario.case, mutated_trace=trace,
        expected_passed=False, expected_gate="gate2", expected_code=FailureCode.JUDGE_BELOW_THRESHOLD,
        expected_dimensions=variant.expected_dimensions, label=variant.note or kind,
    )


def incorrect_final_answer(scenario: Scenario, rng: random.Random) -> OperatorResult:
    return _apply_gate2_variant(scenario, "incorrect_final_answer", "incorrect_final_answer")


def rubric_item_ignored(scenario: Scenario, rng: random.Random) -> OperatorResult:
    return _apply_gate2_variant(scenario, "rubric_item_ignored", "rubric_item_ignored")


def unsafe_content_in_output(scenario: Scenario, rng: random.Random) -> OperatorResult:
    return _apply_gate2_variant(scenario, "unsafe_content_in_output", "unsafe_content_in_output")


def hallucinated_action(scenario: Scenario, rng: random.Random) -> OperatorResult:
    return _apply_gate2_variant(scenario, "hallucinated_action", "hallucinated_action")


GATE2_OPERATORS: List[Tuple[str, Callable[[Scenario, random.Random], OperatorResult]]] = [
    ("incorrect_final_answer", incorrect_final_answer),
    ("rubric_item_ignored", rubric_item_ignored),
    ("unsafe_content_in_output", unsafe_content_in_output),
    ("hallucinated_action", hallucinated_action),
]


# --- Benign controls -----------------------------------------------------------------


def extra_args_under_subset(scenario: Scenario, rng: random.Random) -> OperatorResult:
    name = "extra_args_under_subset"
    candidates = [tc.tool_name for tc in scenario.case.expected_tool_calls if tc.arg_match_mode == ArgMatchMode.SUBSET]
    if not candidates:
        return _inapplicable(scenario, name, "benign", "no expected call uses call-level SUBSET mode")
    trace = scenario.trace.model_copy(deep=True)
    tool_name = rng.choice(sorted(candidates))
    idx = next(i for i, tc in enumerate(trace.executed_tools) if tc.tool_name == tool_name)
    extra_key = f"bench_extra_{rng.randint(1000, 9999)}"
    trace.executed_tools[idx].args[extra_key] = "benign_extra_value"
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=name, category="benign", applicable=True,
        mutated_case=scenario.case, mutated_trace=trace,
        expected_passed=True, expected_gate="gate1",
        label=f"added extra key {extra_key} to {tool_name}",
    )


def reorder_under_any_order(scenario: Scenario, rng: random.Random) -> OperatorResult:
    name = "reorder_under_any_order"
    if scenario.case.trajectory_mode != TrajectoryMode.ANY_ORDER:
        return _inapplicable(scenario, name, "benign", "only applicable under ANY_ORDER")
    trace = scenario.trace.model_copy(deep=True)
    if len(trace.executed_tools) < 2:
        return _inapplicable(scenario, name, "benign", "fewer than 2 executed tool calls")
    original_order = list(trace.executed_tools)
    for _ in range(10):
        rng.shuffle(trace.executed_tools)
        if trace.executed_tools != original_order:
            break
    else:
        # len==2 edge case where shuffle kept landing on the same order - force the swap.
        trace.executed_tools[0], trace.executed_tools[1] = trace.executed_tools[1], trace.executed_tools[0]
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=name, category="benign", applicable=True,
        mutated_case=scenario.case, mutated_trace=trace,
        expected_passed=True, expected_gate="gate1", label="reordered executed_tools",
    )


def _conforming_alt_value(pattern: str, current_value: str, rng: random.Random) -> Optional[str]:
    m = re.match(r"^\^sess_\[a-f0-9\]\{(\d+)\}\$$", pattern)
    if m:
        n = int(m.group(1))
        for _ in range(10):
            candidate = "sess_" + "".join(rng.choice("0123456789abcdef") for _ in range(n))
            if candidate != current_value:
                return candidate
    m = re.match(r"^\^(https://[^/]+/)\.\*\$$", pattern)
    if m:
        prefix = m.group(1)
        for suffix in ["company-info", "about-us", "team", "contact", "alt-page"]:
            candidate = prefix + suffix
            if candidate != current_value:
                return candidate
    return None


def regex_conforming_variable_value(scenario: Scenario, rng: random.Random) -> OperatorResult:
    name = "regex_conforming_variable_value"
    candidates: List[Tuple[int, str, str]] = []
    for i, tc in enumerate(scenario.trace.executed_tools):
        expected = _find_expected(scenario.case, tc.tool_name)
        if expected is None:
            continue
        for key in tc.args:
            if _effective_mode(expected, key) == ArgMatchMode.REGEX and key in expected.args:
                candidates.append((i, key, expected.args[key]))
    if not candidates:
        return _inapplicable(scenario, name, "benign", "no executed call has a REGEX-mode field")
    trace = scenario.trace.model_copy(deep=True)
    idx, key, pattern = rng.choice(candidates)
    current = trace.executed_tools[idx].args[key]
    new_val = _conforming_alt_value(pattern, str(current), rng)
    if new_val is None:
        return _inapplicable(scenario, name, "benign", f"no known conforming-value generator for pattern {pattern!r}")
    trace.executed_tools[idx].args[key] = new_val
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=name, category="benign", applicable=True,
        mutated_case=scenario.case, mutated_trace=trace,
        expected_passed=True, expected_gate="gate1",
        label=f"{trace.executed_tools[idx].tool_name}.{key}: {current!r} -> {new_val!r} (still matches {pattern!r})",
    )


def paraphrased_but_correct_final_answer(scenario: Scenario, rng: random.Random) -> OperatorResult:
    name = "paraphrased_but_correct_final_answer"
    variant, reason = _select_variant(scenario, "paraphrased_but_correct_final_answer", name)
    if variant is None:
        return _inapplicable(scenario, name, "benign", reason)
    trace = scenario.trace.model_copy(deep=True)
    trace.final_output = variant.final_output
    return OperatorResult(
        scenario_id=scenario.id, domain=scenario.domain, operator=name, category="benign", applicable=True,
        mutated_case=scenario.case, mutated_trace=trace,
        expected_passed=True, expected_gate="gate2", label=variant.note or name,
    )


BENIGN_OPERATORS: List[Tuple[str, Callable[[Scenario, random.Random], OperatorResult]]] = [
    ("extra_args_under_subset", extra_args_under_subset),
    ("reorder_under_any_order", reorder_under_any_order),
    ("regex_conforming_variable_value", regex_conforming_variable_value),
    ("paraphrased_but_correct_final_answer", paraphrased_but_correct_final_answer),
]

ALL_OPERATORS: List[Tuple[str, Callable[[Scenario, random.Random], OperatorResult]]] = (
    GATE1_OPERATORS + GATE2_OPERATORS + BENIGN_OPERATORS
)


def apply_all(scenario: Scenario, seed: int) -> List[OperatorResult]:
    """Apply every registered operator to `scenario`, each with its own derived seed."""
    results = []
    for op_name, op_func in ALL_OPERATORS:
        rng = random.Random(derive_seed(seed, scenario.id, op_name))
        results.append(op_func(scenario, rng))
    return results
