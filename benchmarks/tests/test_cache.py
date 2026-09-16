import tempfile
from pathlib import Path

from benchmarks.cache import JudgeCache, cache_key
from traceeval.core.schema import AgentTrace, EDDTestCase, EvaluationDimensionScore, EvaluationResult, ToolCall


def _case_and_trace():
    case = EDDTestCase(case_id="c1", input_prompt="p", rubric=["r"])
    trace = AgentTrace(
        session_id="s1", triggered_skills=[], executed_tools=[ToolCall(tool_name="x", args={})],
        final_output="done", total_token_cost_usd=0.01,
    )
    return case, trace


def test_cache_key_distinct_for_different_k():
    case, trace = _case_and_trace()
    key_k0 = cache_key(case, trace, model="gpt-5.6-luna", temperature=0.0, k=0)
    key_k1 = cache_key(case, trace, model="gpt-5.6-luna", temperature=0.0, k=1)
    assert key_k0 != key_k1


def test_cache_key_stable_for_same_inputs():
    case, trace = _case_and_trace()
    key_a = cache_key(case, trace, model="gpt-5.6-luna", temperature=0.0, k=0)
    key_b = cache_key(case, trace, model="gpt-5.6-luna", temperature=0.0, k=0)
    assert key_a == key_b


def test_cache_set_get_roundtrip_and_k_distinct_entries():
    case, trace = _case_and_trace()
    scores = EvaluationDimensionScore(
        intent_satisfaction=1.0, functional_correctness=1.0, trajectory_quality=1.0,
        cost_efficiency=1.0, safety_and_rai=1.0, reasoning="ok",
    )
    result_k0 = EvaluationResult(case_id="c1", passed=True, scores=scores, trace_summary=trace)
    result_k1 = EvaluationResult(case_id="c1", passed=False, scores=scores, trace_summary=trace, failures=["flip on repeat"])

    with tempfile.TemporaryDirectory() as tmp:
        cache = JudgeCache(cache_dir=Path(tmp))
        key0 = cache_key(case, trace, "gpt-5.6-luna", 0.0, k=0)
        key1 = cache_key(case, trace, "gpt-5.6-luna", 0.0, k=1)

        assert cache.get(key0) is None
        assert cache.get(key1) is None

        cache.set(key0, result_k0)
        cache.set(key1, result_k1)

        cached0 = cache.get(key0)
        cached1 = cache.get(key1)
        assert cached0.passed is True
        assert cached1.passed is False
        assert cached0.model_dump_json() != cached1.model_dump_json()
