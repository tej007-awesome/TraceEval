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
from benchmarks.models import EvalOutcome, Scenario
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
        return response


class _TrackedChat:
    def __init__(self, inner_chat, tracker: dict):
        self.completions = _TrackedCompletions(inner_chat.completions, tracker)


class _TrackedClient:
    """Wraps the real AsyncOpenAI client to capture token usage per call, since
    evaluate_dimensions/run_evaluation don't expose it on EvaluationResult."""

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
    is_judge_error = FailureCode.JUDGE_ERROR.value in codes
    sentinel_triggered = is_judge_error and any(
        "SENTINEL" in (fd.message or "") for fd in result.failure_details
    )
    return EvalOutcome(
        scenario_id=scenario_id, domain=domain, operator=operator, category=category, k=k,
        expected_passed=expected.expected_passed, expected_gate=expected.expected_gate,
        expected_code=expected.expected_code, expected_dimension=expected.expected_dimension,
        label=expected.label,
        actual_passed=result.passed, actual_codes=codes, actual_dimensions=dims,
        is_judge_error=is_judge_error, sentinel_triggered=sentinel_triggered, retries=retries,
        latency_ms=latency_ms, cost_usd=cost_usd, from_cache=from_cache,
    )


async def run_gate1_only(scenarios: List[Scenario], seed: int) -> List[EvalOutcome]:
    import traceeval.metrics.trajectory_judge as tj

    outcomes: List[EvalOutcome] = []
    original_evaluate_dimensions = tj.evaluate_dimensions
    tj.evaluate_dimensions = _sentinel_judge
    try:
        for scenario in scenarios:
            for r in apply_all(scenario, seed):
                if not r.applicable or r.category != "gate1_fault":
                    continue
                start = time.monotonic()
                result = await tj.run_evaluation(r.mutated_case, r.mutated_trace, max_cost=0.10, score_threshold=0.8)
                latency_ms = (time.monotonic() - start) * 1000
                outcomes.append(_outcome_from_result(
                    result, scenario.id, scenario.domain, r.operator, r.category, r, k=0,
                    latency_ms=latency_ms, cost_usd=0.0, retries=0, from_cache=False,
                ))
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
    temperature: float,
    max_total_cost_usd: Optional[float],
    cache_dir: Path,
    use_cache: bool,
    pricing: dict,
) -> tuple[List[EvalOutcome], bool]:
    import traceeval.core.config as config_module
    import traceeval.metrics.trajectory_judge as tj

    cache = JudgeCache(cache_dir)
    tracker: dict = {"last_usage": None}
    real_get_client = config_module.get_judge_client
    original_settings_model = config_module.settings.llm_model_name
    config_module.settings.llm_model_name = judge_model
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
                    key = cache_key(r.mutated_case, r.mutated_trace, judge_model, temperature, k_idx)
                    cached = cache.get(key) if use_cache else None
                    if cached is not None:
                        outcomes.append(_outcome_from_result(
                            cached, scenario.id, scenario.domain, r.operator, r.category, r, k=k_idx,
                            latency_ms=0.0, cost_usd=0.0, retries=0, from_cache=True,
                        ))
                        continue

                    tracker["last_usage"] = None
                    start = time.monotonic()
                    result, attempts = await _run_with_retries(r.mutated_case, r.mutated_trace, 0.10, 0.8, max_attempts=3)
                    latency_ms = (time.monotonic() - start) * 1000

                    cost_usd = 0.0
                    if tracker["last_usage"] is not None:
                        from traceeval.loaders.otel import TokenUsage
                        usage = tracker["last_usage"]
                        cost_result = compute_cost(
                            [TokenUsage(model=judge_model, input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens)],
                            pricing,
                        )
                        cost_usd = cost_result.total_usd
                    total_cost += cost_usd

                    cache.set(key, result)
                    outcomes.append(_outcome_from_result(
                        result, scenario.id, scenario.domain, r.operator, r.category, r, k=k_idx,
                        latency_ms=latency_ms, cost_usd=cost_usd, retries=attempts - 1, from_cache=False,
                    ))
    finally:
        tj.get_judge_client = real_get_client
        config_module.settings.llm_model_name = original_settings_model

    return outcomes, cost_cap_hit


def main():
    parser = argparse.ArgumentParser(description="TraceEval meta-evaluation benchmark runner")
    parser.add_argument("--scenarios-dir", type=Path, default=Path("benchmarks/scenarios"))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--gate1-only", action="store_true")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--judge-model", type=str, default="gpt-5.6-luna")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-total-cost-usd", type=float, default=None)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results.json"))
    args = parser.parse_args()

    scenarios = load_scenarios(args.scenarios_dir)
    if not scenarios:
        print(f"No scenarios found under {args.scenarios_dir}", file=sys.stderr)
        sys.exit(1)

    cost_cap_hit = False
    if args.gate1_only:
        outcomes = asyncio.run(run_gate1_only(scenarios, args.seed))
    else:
        pricing = dict(DEFAULT_PRICING)
        outcomes, cost_cap_hit = asyncio.run(run_judge_mode(
            scenarios, args.seed, args.k, args.judge_model, args.temperature,
            args.max_total_cost_usd, args.cache_dir, use_cache=not args.no_cache, pricing=pricing,
        ))

    sentinel_hits = [o for o in outcomes if o.category == "gate1_fault" and o.sentinel_triggered]

    payload = {
        "config": {
            "commit_sha": _commit_sha(),
            "seed": args.seed,
            "gate1_only": args.gate1_only,
            "k": 0 if args.gate1_only else args.k,
            "judge_model": None if args.gate1_only else args.judge_model,
            "temperature": None if args.gate1_only else args.temperature,
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
        mismatches = [
            o for o in outcomes
            if not (o.actual_passed is False and o.expected_passed is False and (o.expected_code is None or o.expected_code.value in o.actual_codes))
        ]
        if mismatches or sentinel_hits:
            print(f"\n!!! --gate1-only regression check FAILED: {len(mismatches)} mismatch(es), {len(sentinel_hits)} sentinel hit(s).")
            for o in mismatches:
                print(f"    MISMATCH {o.scenario_id} / {o.operator}: expected_code={o.expected_code} actual_codes={o.actual_codes} actual_passed={o.actual_passed}")
            sys.exit(1)
        print(f"\n--gate1-only regression check passed: all {len(outcomes)} gate1_fault outcomes matched expectations.")


if __name__ == "__main__":
    main()
