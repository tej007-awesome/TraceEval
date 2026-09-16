"""Benchmark runner: applies every operator to every scenario and evaluates the result
through TraceEval's real run_evaluation.

Usage:
    python -m benchmarks.run --gate1-only [--seed N] [--scenarios-dir DIR] [--output FILE]
    python -m benchmarks.run --k 3 --judge-model gpt-5.6-luna [--max-total-cost-usd 5.0]

--gate1-only needs no API key: only gate1_fault-category operator results are run, each
through run_evaluation with a sentinel judge patched in place of evaluate_dimensions. The
sentinel always raises if invoked - for a gate1_fault item, gate 1 failing should short-
circuit run_evaluation before evaluate_dimensions is ever called, so the sentinel firing
means gate 1 incorrectly let a fault through (a wiring/regression bug), reported separately
from ordinary judge errors. benign/gate2_fault items are skipped entirely in this mode
(they inherently need a real judge) rather than run against the sentinel pointlessly.

Full (judge) mode runs every applicable operator result. gate1_fault/benign-gate1 items run
once (gate 1 is deterministic - repeats would be pointless). gate2_fault items and the
paraphrase benign control run k times each, with up to 3 judge-call attempts (exponential
backoff) per (item, k) before recording JUDGE_ERROR, and a JSON file cache keyed on
sha256(case, trace, model, temperature, k) so reruns don't re-spend.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from traceeval.core.schema import EDDTestCase, FailureCode
from traceeval.pricing import DEFAULT_PRICING, compute_cost

from benchmarks.cache import DEFAULT_CACHE_DIR, JudgeCache, cache_key
from benchmarks.models import EvalOutcome, OperatorResult, Scenario
from benchmarks.operators import apply_all


def load_scenarios(scenarios_dir: Path) -> List[Scenario]:
    scenarios = []
    for path in sorted(scenarios_dir.glob("*/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        scenarios.append(Scenario.model_validate(data))
    return scenarios


def _commit_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


class _TrackedCompletions:
    def __init__(self, inner, tracker: dict):
        self._inner = inner
        self._tracker = tracker

    async def create(self, *args, **kwargs):
        response = await self._inner.create(*args, **kwargs)
        self._tracker["last_usage"] = response.usage
        self._tracker["last_model"] = getattr(response, "model", None)
        return response


class _TrackedChat:
    def __init__(self, inner_chat, tracker: dict):
        self.completions = _TrackedCompletions(inner_chat.completions, tracker)


class _TrackedClient:
    """Wraps the real AsyncOpenAI client to capture token usage and the response's `model`
    field per call, since evaluate_dimensions/run_evaluation don't expose either on
    EvaluationResult. The returned `model` is recorded separately from the requested model
    ID in the report - OpenRouter (this repo's configured provider) echoes back the model
    alias, not the dated snapshot that was actually requested, so exact snapshot pinning
    can't be fully verified from the response alone."""

    def __init__(self, inner_client, tracker: dict):
        self.chat = _TrackedChat(inner_client.chat, tracker)


async def _sentinel_judge(trace, case):
    raise RuntimeError(
        "SENTINEL: evaluate_dimensions was invoked in --gate1-only mode - gate 1 failed to "
        "short-circuit before the judge for what should have been a deterministic failure."
    )


def _outcome_from_result(result, scenario_id, domain, operator, category, expected, k, latency_ms, cost_usd, retries, from_cache) -> EvalOutcome:
    codes = [fd.code.value for fd in result.failure_details]
    dims = [fd.dimension for fd in result.failure_details if fd.dimension]
    below_threshold_dims = [
        fd.dimension for fd in result.failure_details
        if fd.code == FailureCode.JUDGE_BELOW_THRESHOLD and fd.dimension
    ]
    is_judge_error = FailureCode.JUDGE_ERROR.value in codes
    sentinel_triggered = is_judge_error and any(
        "SENTINEL" in (fd.message or "") for fd in result.failure_details
    )
    return EvalOutcome(
        scenario_id=scenario_id, domain=domain, operator=operator, category=category, k=k,
        expected_passed=expected.expected_passed, expected_gate=expected.expected_gate,
        expected_code=expected.expected_code, expected_dimensions=expected.expected_dimensions,
        label=expected.label,
        actual_passed=result.passed, actual_codes=codes, actual_dimensions=dims,
        actual_below_threshold_dimensions=below_threshold_dims,
        is_judge_error=is_judge_error, sentinel_triggered=sentinel_triggered, retries=retries,
        latency_ms=latency_ms, cost_usd=cost_usd, from_cache=from_cache,
    )


def _outcome_for_gate1_decidable(result, scenario_id, domain, operator, category, expected, latency_ms) -> EvalOutcome:
    """For clean bases and gate-1-decidable benign controls: if the sentinel fired, gate 1
    legitimately PASSED and reached the judge stage - the correct, expected outcome for
    these items, not an error. Only gate1_fault items (handled by _outcome_from_result)
    treat a sentinel hit as a regression."""
    codes = [fd.code.value for fd in result.failure_details]
    dims = [fd.dimension for fd in result.failure_details if fd.dimension]
    is_judge_error = FailureCode.JUDGE_ERROR.value in codes
    sentinel_triggered = is_judge_error and any(
        "SENTINEL" in (fd.message or "") for fd in result.failure_details
    )
    actual_passed = True if sentinel_triggered else result.passed
    actual_codes = [] if sentinel_triggered else codes
    return EvalOutcome(
        scenario_id=scenario_id, domain=domain, operator=operator, category=category, k=0,
        expected_passed=expected.expected_passed, expected_gate=expected.expected_gate,
        expected_code=expected.expected_code, expected_dimensions=expected.expected_dimensions,
        label=expected.label,
        actual_passed=actual_passed, actual_codes=actual_codes, actual_dimensions=dims,
        is_judge_error=False, sentinel_triggered=sentinel_triggered, retries=0,
        latency_ms=latency_ms, cost_usd=0.0, from_cache=False,
    )


async def run_gate1_only(scenarios: List[Scenario], seed: int) -> List[EvalOutcome]:
    """Runs everything gate 1 can decide on its own: gate1_fault operator results (sentinel
    hit = regression), the clean base trace itself, and the three gate-1-decidable benign
    controls (extra_args_under_subset, reorder_under_any_order, regex_conforming_variable_value
    - sentinel hit = correct/expected). gate2_fault operators and the paraphrase benign
    control are skipped entirely - they inherently need a real judge."""
    import traceeval.metrics.trajectory_judge as tj

    outcomes: List[EvalOutcome] = []
    original_evaluate_dimensions = tj.evaluate_dimensions
    tj.evaluate_dimensions = _sentinel_judge
    try:
        for scenario in scenarios:
            clean_expected = OperatorResult(
                scenario_id=scenario.id, domain=scenario.domain, operator="clean_base", category="benign",
                applicable=True, expected_passed=True, expected_gate="gate1",
                label="clean base trace (unmutated)",
            )
            start = time.monotonic()
            result = await tj.run_evaluation(scenario.case, scenario.trace, max_cost=0.10, score_threshold=0.8)
            latency_ms = (time.monotonic() - start) * 1000
            outcomes.append(_outcome_for_gate1_decidable(
                result, scenario.id, scenario.domain, "clean_base", "benign", clean_expected, latency_ms,
            ))

            for r in apply_all(scenario, seed):
                if not r.applicable:
                    continue
                if r.category == "gate1_fault":
                    start = time.monotonic()
                    result = await tj.run_evaluation(r.mutated_case, r.mutated_trace, max_cost=0.10, score_threshold=0.8)
                    latency_ms = (time.monotonic() - start) * 1000
                    outcomes.append(_outcome_from_result(
                        result, scenario.id, scenario.domain, r.operator, r.category, r, k=0,
                        latency_ms=latency_ms, cost_usd=0.0, retries=0, from_cache=False,
                    ))
                elif r.category == "benign" and r.expected_gate == "gate1":
                    start = time.monotonic()
                    result = await tj.run_evaluation(r.mutated_case, r.mutated_trace, max_cost=0.10, score_threshold=0.8)
                    latency_ms = (time.monotonic() - start) * 1000
                    outcomes.append(_outcome_for_gate1_decidable(
                        result, scenario.id, scenario.domain, r.operator, r.category, r, latency_ms,
                    ))
                # gate2_fault operators, and the paraphrase benign control (expected_gate ==
                # "gate2"), are skipped here - they inherently need a real judge call.
    finally:
        tj.evaluate_dimensions = original_evaluate_dimensions
    return outcomes


async def _run_with_retries(case: EDDTestCase, trace, max_cost, score_threshold, max_attempts: int):
    import traceeval.metrics.trajectory_judge as tj

    attempts = 0
    result = None
    while attempts < max_attempts:
        attempts += 1
        result = await tj.run_evaluation(case, trace, max_cost=max_cost, score_threshold=score_threshold)
        is_error = any(fd.code == FailureCode.JUDGE_ERROR for fd in result.failure_details)
        if not is_error:
            return result, attempts
        if attempts < max_attempts:
            await asyncio.sleep(1.0 * (2 ** (attempts - 1)))
    return result, attempts


async def run_judge_mode(
    scenarios: List[Scenario],
    seed: int,
    k: int,
    judge_model: str,
    judge_temperature: Optional[float],
    reasoning_effort: Optional[str],
    max_total_cost_usd: Optional[float],
    cache_dir: Path,
    use_cache: bool,
    pricing: dict,
) -> tuple[List[EvalOutcome], bool, List[str]]:
    import traceeval.core.config as config_module
    import traceeval.metrics.trajectory_judge as tj

    cache = JudgeCache(cache_dir)
    tracker: dict = {"last_usage": None, "last_model": None}
    returned_models: set = set()
    real_get_client = config_module.get_judge_client
    original_settings_model = config_module.settings.llm_model_name
    original_settings_temperature = config_module.settings.judge_temperature
    original_settings_reasoning = config_module.settings.judge_reasoning_effort
    config_module.settings.llm_model_name = judge_model
    config_module.settings.judge_temperature = judge_temperature
    config_module.settings.judge_reasoning_effort = reasoning_effort
    tj.get_judge_client = lambda: _TrackedClient(real_get_client(), tracker)

    outcomes: List[EvalOutcome] = []
    total_cost = 0.0
    cost_cap_hit = False

    try:
        for scenario in scenarios:
            if cost_cap_hit:
                break
            for r in apply_all(scenario, seed):
                if cost_cap_hit:
                    break
                if not r.applicable:
                    continue

                if r.category == "gate1_fault" or (r.category == "benign" and r.expected_gate == "gate1"):
                    start = time.monotonic()
                    result = await tj.run_evaluation(r.mutated_case, r.mutated_trace, max_cost=0.10, score_threshold=0.8)
                    latency_ms = (time.monotonic() - start) * 1000
                    outcomes.append(_outcome_from_result(
                        result, scenario.id, scenario.domain, r.operator, r.category, r, k=0,
                        latency_ms=latency_ms, cost_usd=0.0, retries=0, from_cache=False,
                    ))
                    continue

                # gate2_fault, or the paraphrase benign control: k repeats, cached, retried.
                for k_idx in range(k):
                    if max_total_cost_usd is not None and total_cost >= max_total_cost_usd:
                        cost_cap_hit = True
                        break
                    key = cache_key(r.mutated_case, r.mutated_trace, judge_model, judge_temperature, k_idx)
                    cached = cache.get(key) if use_cache else None
                    if cached is not None:
                        outcomes.append(_outcome_from_result(
                            cached, scenario.id, scenario.domain, r.operator, r.category, r, k=k_idx,
                            latency_ms=0.0, cost_usd=0.0, retries=0, from_cache=True,
                        ))
                        continue

                    tracker["last_usage"] = None
                    tracker["last_model"] = None
                    start = time.monotonic()
                    result, attempts = await _run_with_retries(r.mutated_case, r.mutated_trace, 0.10, 0.8, max_attempts=3)
                    latency_ms = (time.monotonic() - start) * 1000

                    if tracker["last_model"]:
                        returned_models.add(tracker["last_model"])

                    cost_usd = 0.0
                    if tracker["last_usage"] is not None:
                        from traceeval.loaders.otel import TokenUsage
                        usage = tracker["last_usage"]
                        cost_result = compute_cost(
                            [TokenUsage(model=judge_model, input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens)],
                            pricing,
                        )
                        cost_usd = cost_result.total_usd
                        if cost_result.unknown_models:
                            print(
                                f"WARNING: no pricing entry for model(s) {cost_result.unknown_models} - "
                                f"cost reported as $0 for this call; add a pricing entry to get real cost tracking.",
                                file=sys.stderr,
                            )
                    total_cost += cost_usd

                    cache.set(key, result)
                    outcomes.append(_outcome_from_result(
                        result, scenario.id, scenario.domain, r.operator, r.category, r, k=k_idx,
                        latency_ms=latency_ms, cost_usd=cost_usd, retries=attempts - 1, from_cache=False,
                    ))
    finally:
        tj.get_judge_client = real_get_client
        config_module.settings.llm_model_name = original_settings_model
        config_module.settings.judge_temperature = original_settings_temperature
        config_module.settings.judge_reasoning_effort = original_settings_reasoning

    return outcomes, cost_cap_hit, sorted(returned_models)


def main():
    parser = argparse.ArgumentParser(description="TraceEval meta-evaluation benchmark runner")
    parser.add_argument("--scenarios-dir", type=Path, default=Path("benchmarks/scenarios"))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--gate1-only", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N scenarios (sorted by path) - for pilots.")
    parser.add_argument("--k", type=int, default=3)
    # Dated snapshot (not the alias), per OpenRouter's public /models catalog
    # (canonical_slug "openai/gpt-5.6-luna-20260709"). This is the model string that works
    # through THIS repo's configured LLM_BASE_URL (OpenRouter); direct-OpenAI users should
    # override with OpenAI's own dated snapshot ID. Note: OpenRouter echoes back the alias
    # in response.model, not this dated string - see returned_model_ids in the report.
    parser.add_argument("--judge-model", type=str, default="openai/gpt-5.6-luna-20260709")
    # Verified live (see PR discussion): temperature=0.0 is accepted by gpt-5.6-luna via
    # OpenRouter. Defaulting to 0.0 for deterministic, low-variance judge output.
    parser.add_argument("--judge-temperature", type=float, default=0.0)
    # Lowest of gpt-5.6-luna's supported_efforts (max/xhigh/high/medium/low/none). Verified
    # live: "none" is honoured (accepted and changes behavior, not silently ignored).
    parser.add_argument("--reasoning-effort", type=str, default="none")
    parser.add_argument("--max-total-cost-usd", type=float, default=None)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results.json"))
    args = parser.parse_args()

    scenarios = load_scenarios(args.scenarios_dir)
    if not scenarios:
        print(f"No scenarios found under {args.scenarios_dir}", file=sys.stderr)
        sys.exit(1)
    if args.limit is not None:
        scenarios = scenarios[: args.limit]

    cost_cap_hit = False
    returned_model_ids: List[str] = []
    if args.gate1_only:
        outcomes = asyncio.run(run_gate1_only(scenarios, args.seed))
    else:
        pricing = dict(DEFAULT_PRICING)
        outcomes, cost_cap_hit, returned_model_ids = asyncio.run(run_judge_mode(
            scenarios, args.seed, args.k, args.judge_model, args.judge_temperature, args.reasoning_effort,
            args.max_total_cost_usd, args.cache_dir, use_cache=not args.no_cache, pricing=pricing,
        ))

    sentinel_hits = [o for o in outcomes if o.category == "gate1_fault" and o.sentinel_triggered]

    payload = {
        "config": {
            "commit_sha": _commit_sha(),
            "seed": args.seed,
            "gate1_only": args.gate1_only,
            "k": 0 if args.gate1_only else args.k,
            "requested_judge_model": None if args.gate1_only else args.judge_model,
            "returned_model_ids": returned_model_ids,
            "returned_model_ids_note": (
                None if args.gate1_only else
                "OpenRouter echoes back the model alias in each response, not the dated "
                "snapshot that was actually requested - exact snapshot pinning can't be "
                "fully verified from the response alone."
            ),
            "judge_temperature": None if args.gate1_only else args.judge_temperature,
            "reasoning_effort": None if args.gate1_only else args.reasoning_effort,
            "n_scenarios": len(scenarios),
            "cost_cap_hit": cost_cap_hit,
        },
        "outcomes": [o.model_dump(mode="json") for o in outcomes],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Wrote {len(outcomes)} outcomes to {args.output}")
    if sentinel_hits:
        print(f"\n!!! {len(sentinel_hits)} gate1_fault item(s) incorrectly reached the judge (sentinel fired):")
        for o in sentinel_hits:
            print(f"    {o.scenario_id} / {o.operator}: expected {o.expected_code}")
    if cost_cap_hit:
        print("\n!!! --max-total-cost-usd cap was hit; partial results written.")

    if args.gate1_only:
        fault_mismatches = [
            o for o in outcomes
            if o.category == "gate1_fault"
            and not (o.actual_passed is False and o.expected_passed is False and (o.expected_code is None or o.expected_code.value in o.actual_codes))
        ]
        false_positives = [
            o for o in outcomes
            if o.category != "gate1_fault" and o.expected_passed is True and o.actual_passed is False
        ]
        if fault_mismatches or false_positives or sentinel_hits:
            print(
                f"\n!!! --gate1-only regression check FAILED: {len(fault_mismatches)} fault mismatch(es), "
                f"{len(false_positives)} false positive(s), {len(sentinel_hits)} sentinel hit(s)."
            )
            for o in fault_mismatches:
                print(f"    FAULT MISMATCH {o.scenario_id} / {o.operator}: expected_code={o.expected_code} actual_codes={o.actual_codes} actual_passed={o.actual_passed}")
            for o in false_positives:
                print(f"    FALSE POSITIVE {o.scenario_id} / {o.operator}: expected_passed=True actual_passed=False actual_codes={o.actual_codes}")
            sys.exit(1)
        print(f"\n--gate1-only regression check passed: all {len(outcomes)} outcomes matched expectations.")


if __name__ == "__main__":
    main()
