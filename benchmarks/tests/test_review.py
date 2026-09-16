import json
from benchmarks.review import build_review_queue


def _payload_with_one_fp_and_one_miss():
    return {
        "config": {"commit_sha": "abc123", "requested_judge_model": "openai/gpt-5.6-luna-20260709", "k": 3, "seed": 0},
        "outcomes": [
            {
                "scenario_id": "refund_001_in_order_subset_regex", "domain": "refunds",
                "operator": "clean_base", "category": "benign", "k": 0,
                "expected_passed": True, "expected_gate": "gate2", "expected_code": None, "expected_dimensions": [],
                "label": "clean base trace (unmutated)",
                "actual_passed": False, "actual_codes": ["JUDGE_BELOW_THRESHOLD"],
                "actual_dimensions": ["functional_correctness"],
                "actual_below_threshold_dimensions": ["functional_correctness"],
                "gate1_passed": True,
                "judge_reasoning": "The response omits a required detail.",
                "actual_scores": {"functional_correctness": 0.5},
                "is_judge_error": False, "sentinel_triggered": False, "retries": 0,
                "latency_ms": 100.0, "cost_usd": 0.0003, "from_cache": False,
            },
            {
                "scenario_id": "refund_001_in_order_subset_regex", "domain": "refunds",
                "operator": "incorrect_final_answer", "category": "gate2_fault", "k": 0,
                "expected_passed": False, "expected_gate": "gate2", "expected_code": None,
                "expected_dimensions": ["functional_correctness"], "label": "wrong amount",
                "actual_passed": True, "actual_codes": [], "actual_dimensions": [],
                "actual_below_threshold_dimensions": [], "gate1_passed": True,
                "judge_reasoning": "The judge didn't notice the discrepancy.",
                "actual_scores": {"functional_correctness": 0.85},
                "is_judge_error": False, "sentinel_triggered": False, "retries": 0,
                "latency_ms": 120.0, "cost_usd": 0.0003, "from_cache": False,
            },
        ],
    }


def test_build_review_queue_includes_both_fp_and_miss(tmp_path):
    payload = _payload_with_one_fp_and_one_miss()
    content = build_review_queue(payload, tmp_path / "nonexistent_scenarios_dir", include_holdout=True)
    assert "Total review groups: 2" in content
    assert "Pipeline FP: refund_001_in_order_subset_regex / clean_base" in content
    assert "Gate-2 miss: refund_001_in_order_subset_regex / incorrect_final_answer" in content


def test_build_review_queue_never_prefills_human_label(tmp_path):
    payload = _payload_with_one_fp_and_one_miss()
    content = build_review_queue(payload, tmp_path / "nonexistent_scenarios_dir", include_holdout=True)
    # The literal placeholder must appear once per group entry, with no guessed value substituted.
    assert content.count("`human_label:` [valid_fp | scenario_bug | judge_correct]") == 2
    assert "human_label: valid_fp" not in content
    assert "human_label: scenario_bug" not in content
    assert "human_label: judge_correct" not in content


def test_build_review_queue_includes_judge_reasoning_and_scores(tmp_path):
    payload = _payload_with_one_fp_and_one_miss()
    content = build_review_queue(payload, tmp_path / "nonexistent_scenarios_dir", include_holdout=True)
    assert "The response omits a required detail." in content
    assert "The judge didn't notice the discrepancy." in content
    assert "functional_correctness" in content


def test_build_review_queue_empty_when_no_fp_or_miss(tmp_path):
    payload = {
        "config": {"commit_sha": "abc123", "k": 3, "seed": 0},
        "outcomes": [{
            "scenario_id": "s", "domain": "refunds", "operator": "clean_base", "category": "benign", "k": 0,
            "expected_passed": True, "expected_gate": "gate2", "expected_code": None, "expected_dimensions": [],
            "label": "", "actual_passed": True, "actual_codes": [], "actual_dimensions": [],
            "actual_below_threshold_dimensions": [], "gate1_passed": True,
            "is_judge_error": False, "sentinel_triggered": False, "retries": 0,
            "latency_ms": 0.0, "cost_usd": 0.0, "from_cache": False,
        }],
    }
    content = build_review_queue(payload, tmp_path / "nonexistent_scenarios_dir", include_holdout=True)
    assert "Total review groups: 0" in content


def test_build_review_queue_excludes_holdout_by_default(tmp_path):
    holdout_file = tmp_path / "holdout.json"
    holdout_file.write_text(json.dumps({"seed": 0, "scenario_ids": ["holdout_sc_01"]}))

    payload = {
        "config": {"commit_sha": "abc123", "k": 1, "seed": 0},
        "outcomes": [
            {
                "scenario_id": "holdout_sc_01", "domain": "refunds", "operator": "clean_base", "category": "benign", "k": 0,
                "expected_passed": True, "expected_gate": "gate2", "expected_code": None, "expected_dimensions": [],
                "label": "clean base trace", "actual_passed": False, "actual_codes": ["JUDGE_BELOW_THRESHOLD"],
                "actual_dimensions": ["functional_correctness"], "actual_below_threshold_dimensions": ["functional_correctness"],
                "gate1_passed": True, "judge_reasoning": "reasoning", "actual_scores": {"functional_correctness": 0.5},
                "is_judge_error": False, "sentinel_triggered": False, "retries": 0, "latency_ms": 10.0, "cost_usd": 0.001, "from_cache": False,
            },
            {
                "scenario_id": "dev_sc_01", "domain": "refunds", "operator": "clean_base", "category": "benign", "k": 0,
                "expected_passed": True, "expected_gate": "gate2", "expected_code": None, "expected_dimensions": [],
                "label": "clean base trace", "actual_passed": False, "actual_codes": ["JUDGE_BELOW_THRESHOLD"],
                "actual_dimensions": ["functional_correctness"], "actual_below_threshold_dimensions": ["functional_correctness"],
                "gate1_passed": True, "judge_reasoning": "reasoning", "actual_scores": {"functional_correctness": 0.5},
                "is_judge_error": False, "sentinel_triggered": False, "retries": 0, "latency_ms": 10.0, "cost_usd": 0.001, "from_cache": False,
            }
        ]
    }

    # By default (include_holdout=False), holdout_sc_01 should be excluded
    content_default = build_review_queue(payload, tmp_path / "nonexistent", holdout_file=holdout_file)
    assert "Total review groups: 1" in content_default
    assert "dev_sc_01" in content_default
    assert "holdout_sc_01" not in content_default

    # When include_holdout=True, holdout_sc_01 should be included
    content_included = build_review_queue(payload, tmp_path / "nonexistent", include_holdout=True, holdout_file=holdout_file)
    assert "Total review groups: 2" in content_included
    assert "holdout_sc_01" in content_included


def test_build_review_queue_includes_regex_conforming_variable_value(tmp_path):
    payload = {
        "config": {"commit_sha": "abc123", "k": 1, "seed": 0},
        "outcomes": [
            {
                "scenario_id": "dev_sc_01", "domain": "refunds", "operator": "regex_conforming_variable_value", "category": "benign", "k": 0,
                "expected_passed": True, "expected_gate": "gate2", "expected_code": None, "expected_dimensions": [],
                "label": "benign regex control", "actual_passed": False, "actual_codes": ["JUDGE_BELOW_THRESHOLD"],
                "actual_dimensions": ["functional_correctness"], "actual_below_threshold_dimensions": ["functional_correctness"],
                "gate1_passed": True, "judge_reasoning": "reasoning", "actual_scores": {"functional_correctness": 0.5},
                "is_judge_error": False, "sentinel_triggered": False, "retries": 0, "latency_ms": 10.0, "cost_usd": 0.001, "from_cache": False,
            }
        ]
    }
    content = build_review_queue(payload, tmp_path / "nonexistent", include_holdout=True)
    assert "Total review groups: 1" in content
    assert "regex_conforming_variable_value" in content
