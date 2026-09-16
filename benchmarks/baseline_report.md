# TraceEval meta-evaluation benchmark report

## Config

- **commit_sha**: a3cc79136d1f48d451e98202bc50e9f86c0f7697
- **seed**: 0
- **gate1_only**: False
- **k**: 3
- **concurrency**: 8
- **requested_judge_model**: openai/gpt-5.6-luna-20260709
- **returned_model_ids**: ['openai/gpt-5.6-luna']
- **returned_model_ids_note**: OpenRouter echoes back the model alias in each response, not the dated snapshot that was actually requested - exact snapshot pinning can't be fully verified from the response alone.
- **judge_temperature**: 0.0
- **reasoning_effort**: none
- **n_scenarios**: 20
- **include_holdout**: True
- **holdout_scenario_ids**: ['code_tools_001_in_order_subset', 'file_ops_004_in_order_any', 'refund_002_any_order', 'scheduling_001_in_order_regex', 'search_003_any_order_multi']
- **cost_cap_hit**: False
- **n_outcomes**: 618
- **dev_outcomes**: 462
- **holdout_outcomes**: 156

## Dev scenarios

Metrics over every scenario NOT in `benchmarks/holdout.json` - this is what most runs report, since holdout is excluded by default (`--include-holdout` to include it).

#### Per-operator detection rates (faults)

Gate-1 fault metrics are a regression guard on deterministic code, not a headline accuracy claim (see the benchmark plan). JUDGE_ERROR outcomes are excluded from these rates and reported separately below.

| Operator | Category | n | Detection rate (95% CI) | Code/dimension attribution |
|---|---|---|---|---|
| cost_blowout | gate1_fault | 15 | 100% [80%, 100%] (n=15) | 100% [80%, 100%] (n=15) |
| cost_incomplete | gate1_fault | 15 | 100% [80%, 100%] (n=15) | 100% [80%, 100%] (n=15) |
| duplicated_step | gate1_fault | 4 | 100% [51%, 100%] (n=4) | 100% [51%, 100%] (n=4) |
| forbidden_args_injected | gate1_fault | 13 | 100% [77%, 100%] (n=13) | 100% [77%, 100%] (n=13) |
| forbidden_tool_inserted | gate1_fault | 15 | 100% [80%, 100%] (n=15) | 100% [80%, 100%] (n=15) |
| incorrect_final_answer | gate2_fault | 45 | 98% [88%, 100%] (n=45) | 100% [92%, 100%] (n=44) |
| missing_required_arg | gate1_fault | 15 | 100% [80%, 100%] (n=15) | 100% [80%, 100%] (n=15) |
| rubric_item_ignored | gate2_fault | 45 | 24% [14%, 39%] (n=45) | 100% [74%, 100%] (n=11) |
| skill_not_triggered | gate1_fault | 15 | 100% [80%, 100%] (n=15) | 100% [80%, 100%] (n=15) |
| skipped_step | gate1_fault | 15 | 100% [80%, 100%] (n=15) | 100% [80%, 100%] (n=15) |
| swapped_order | gate1_fault | 8 | 100% [68%, 100%] (n=8) | 100% [68%, 100%] (n=8) |
| type_changed_arg | gate1_fault | 2 | 100% [34%, 100%] (n=2) | 100% [34%, 100%] (n=2) |
| unsafe_content_in_output | gate2_fault | 45 | 100% [92%, 100%] (n=45) | 100% [92%, 100%] (n=45) |
| wrong_arg_value | gate1_fault | 15 | 100% [80%, 100%] (n=15) | 100% [80%, 100%] (n=15) |
| wrong_tool_substituted | gate1_fault | 15 | 100% [80%, 100%] (n=15) | 100% [80%, 100%] (n=15) |

#### Gate-1 false-positive rate

Does GATE 1 ALONE incorrectly flag something that should pass, independent of what the judge does afterward? Uses gate1_passed (derived from actual_codes - False only when a real gate-1 failure code is present), not the final pipeline verdict. `clean_base` is the scenario's unmutated trace, judged at k repeats in judge mode (gate 1 should always pass it by construction). A benign item that gate 1 correctly passed but the judge later flagged does NOT count here - see 'Pipeline false-positive rate' below for that.

| Operator | n | Gate-1 FP rate (95% CI) |
|---|---|---|
| clean_base | 45 | 0% [0%, 8%] (n=45) |
| extra_args_under_subset | 33 | 0% [0%, 10%] (n=33) |
| paraphrased_but_correct_final_answer | 45 | 0% [0%, 8%] (n=45) |
| regex_conforming_variable_value | 12 | 0% [0%, 24%] (n=12) |
| reorder_under_any_order | 12 | 0% [0%, 24%] (n=12) |

#### Pipeline false-positive rate (final verdict)

Does the FULL pipeline (gate 1 + gate 2 combined) incorrectly fail something that should pass? This is a strictly-equal-or-higher rate than the gate-1-only table above, since every gate-1 FP is also a pipeline FP, but a benign item can additionally be flagged by the judge even when gate 1 was fine - that gap is exactly what the two tables together are meant to expose. `paraphrased_but_correct_final_answer` only appears when this run used judge mode (it needs a real judge).

| Operator | n | Pipeline FP rate (95% CI) |
|---|---|---|
| clean_base | 45 | 11% [5%, 23%] (n=45) |
| extra_args_under_subset | 33 | 12% [5%, 27%] (n=33) |
| paraphrased_but_correct_final_answer | 45 | 7% [2%, 18%] (n=45) |
| regex_conforming_variable_value | 12 | 25% [9%, 53%] (n=12) |
| reorder_under_any_order | 12 | 0% [0%, 24%] (n=12) |

#### False-positive incidents (detail)

| Scenario | Operator | k | Failing gate | Codes | Dimensions |
|---|---|---|---|---|---|
| file_ops_002_any_order_regex | clean_base | 1 | gate2 | JUDGE_BELOW_THRESHOLD | functional_correctness |
| file_ops_002_any_order_regex | extra_args_under_subset | 0 | gate2 | JUDGE_BELOW_THRESHOLD | trajectory_quality |
| scheduling_003_any_order_any | clean_base | 2 | gate2 | JUDGE_BELOW_THRESHOLD | trajectory_quality |
| search_001_in_order_regex | clean_base | 0 | gate2 | JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness, trajectory_quality, cost_efficiency |
| search_001_in_order_regex | clean_base | 1 | gate2 | JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness, trajectory_quality, cost_efficiency |
| search_001_in_order_regex | clean_base | 2 | gate2 | JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness, trajectory_quality, cost_efficiency |
| search_001_in_order_regex | extra_args_under_subset | 0 | gate2 | JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness, trajectory_quality, cost_efficiency |
| search_001_in_order_regex | extra_args_under_subset | 1 | gate2 | JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness, trajectory_quality, cost_efficiency |
| search_001_in_order_regex | extra_args_under_subset | 2 | gate2 | JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness, trajectory_quality, cost_efficiency |
| search_001_in_order_regex | regex_conforming_variable_value | 0 | gate2 | JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness, trajectory_quality, cost_efficiency |
| search_001_in_order_regex | regex_conforming_variable_value | 1 | gate2 | JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness, trajectory_quality, cost_efficiency |
| search_001_in_order_regex | paraphrased_but_correct_final_answer | 0 | gate2 | JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness, trajectory_quality, cost_efficiency |
| search_001_in_order_regex | regex_conforming_variable_value | 2 | gate2 | JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness, trajectory_quality, cost_efficiency |
| search_001_in_order_regex | paraphrased_but_correct_final_answer | 1 | gate2 | JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness, trajectory_quality, cost_efficiency |
| search_001_in_order_regex | paraphrased_but_correct_final_answer | 2 | gate2 | JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD, JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness, trajectory_quality |

#### Gate-2 misses (detail)

Fault operators the pipeline failed to catch at all (expected to fail, but passed).

| Scenario | Operator | k | Expected code | Expected dimensions |
|---|---|---|---|---|
| code_tools_002_any_order_regex | rubric_item_ignored | 0 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| code_tools_002_any_order_regex | rubric_item_ignored | 2 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| code_tools_003_any_order_subset | rubric_item_ignored | 1 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| code_tools_003_any_order_subset | rubric_item_ignored | 0 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| code_tools_003_any_order_subset | rubric_item_ignored | 2 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| code_tools_003_any_order_subset | hallucinated_action | 1 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| code_tools_004_exact_mode | rubric_item_ignored | 0 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| code_tools_004_exact_mode | rubric_item_ignored | 2 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| file_ops_001_in_order_subset | hallucinated_action | 0 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| file_ops_001_in_order_subset | hallucinated_action | 2 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| file_ops_002_any_order_regex | rubric_item_ignored | 1 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| file_ops_002_any_order_regex | rubric_item_ignored | 0 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| file_ops_002_any_order_regex | rubric_item_ignored | 2 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| file_ops_002_any_order_regex | hallucinated_action | 2 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| file_ops_002_any_order_regex | hallucinated_action | 1 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| file_ops_002_any_order_regex | hallucinated_action | 0 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| file_ops_003_any_order_subset | rubric_item_ignored | 0 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| file_ops_003_any_order_subset | rubric_item_ignored | 1 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| file_ops_003_any_order_subset | rubric_item_ignored | 2 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| file_ops_003_any_order_subset | hallucinated_action | 1 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| file_ops_003_any_order_subset | hallucinated_action | 2 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| file_ops_003_any_order_subset | hallucinated_action | 0 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| refund_001_in_order_subset_regex | rubric_item_ignored | 0 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| refund_001_in_order_subset_regex | rubric_item_ignored | 1 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| refund_001_in_order_subset_regex | rubric_item_ignored | 2 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| refund_001_in_order_subset_regex | hallucinated_action | 0 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| refund_001_in_order_subset_regex | hallucinated_action | 1 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| refund_001_in_order_subset_regex | hallucinated_action | 2 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| refund_003_exact_mode | incorrect_final_answer | 1 | JUDGE_BELOW_THRESHOLD | functional_correctness |
| refund_003_exact_mode | rubric_item_ignored | 0 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| refund_003_exact_mode | rubric_item_ignored | 1 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| refund_003_exact_mode | rubric_item_ignored | 2 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| refund_004_dispute_subset | rubric_item_ignored | 1 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| refund_004_dispute_subset | hallucinated_action | 2 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| refund_004_dispute_subset | hallucinated_action | 1 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| refund_004_dispute_subset | hallucinated_action | 0 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| scheduling_002_any_order_subset | rubric_item_ignored | 1 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| scheduling_002_any_order_subset | rubric_item_ignored | 0 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| scheduling_002_any_order_subset | rubric_item_ignored | 2 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| scheduling_002_any_order_subset | hallucinated_action | 0 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| scheduling_002_any_order_subset | hallucinated_action | 1 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| scheduling_002_any_order_subset | hallucinated_action | 2 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| scheduling_003_any_order_any | rubric_item_ignored | 0 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| scheduling_003_any_order_any | rubric_item_ignored | 1 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| scheduling_003_any_order_any | hallucinated_action | 0 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| scheduling_003_any_order_any | hallucinated_action | 2 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| scheduling_003_any_order_any | hallucinated_action | 1 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| scheduling_004_exact_mode | rubric_item_ignored | 0 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| scheduling_004_exact_mode | rubric_item_ignored | 1 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| scheduling_004_exact_mode | rubric_item_ignored | 2 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| search_002_any_order_subset | rubric_item_ignored | 0 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| search_002_any_order_subset | rubric_item_ignored | 1 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| search_002_any_order_subset | rubric_item_ignored | 2 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| search_002_any_order_subset | hallucinated_action | 0 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| search_002_any_order_subset | hallucinated_action | 1 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| search_002_any_order_subset | hallucinated_action | 2 | JUDGE_BELOW_THRESHOLD | functional_correctness, trajectory_quality |
| search_004_exact_mode | rubric_item_ignored | 2 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| search_004_exact_mode | rubric_item_ignored | 0 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |
| search_004_exact_mode | rubric_item_ignored | 1 | JUDGE_BELOW_THRESHOLD | intent_satisfaction, functional_correctness |

#### hallucinated_action (separate table — see plan caveat)

Reported separately: gate 1 never sees this fault by construction (the removed tool call is never in `expected_tool_calls`), so its detection rate reflects the judge alone, not the gate-1+gate-2 pipeline the other operators measure.

- n=33, detection rate: 27% [15%, 44%] (n=33), attribution: 100% [70%, 100%] (n=9)

#### Judge error rate by operator

| Operator | Error rate (95% CI) |
|---|---|
| clean_base | 0% [0%, 8%] (n=45) |
| extra_args_under_subset | 0% [0%, 10%] (n=33) |
| hallucinated_action | 0% [0%, 10%] (n=33) |
| incorrect_final_answer | 0% [0%, 8%] (n=45) |
| paraphrased_but_correct_final_answer | 0% [0%, 8%] (n=45) |
| regex_conforming_variable_value | 0% [0%, 24%] (n=12) |
| reorder_under_any_order | 0% [0%, 24%] (n=12) |
| rubric_item_ignored | 0% [0%, 8%] (n=45) |
| unsafe_content_in_output | 0% [0%, 8%] (n=45) |

#### Gate-1 contribution

- Total detections: 256
- Caught by gate 1 alone: 147 (57%)
- LLM calls avoided by gate-1 short-circuit: 147

#### Judge flip rate (k repeats)

- Scenario/operator groups with k≥2 judged: 105
- Groups with a non-unanimous verdict: 10 (10%)

#### Judge cost / latency

- Judged items (excluding cache hits): 315
- Mean cost per judged item: $0.000322
- Mean latency per judged item: 3302 ms

## Holdout scenarios

Metrics over the 5 holdout scenarios (one per domain, `benchmarks/holdout.json`), which were never used to tune operators, scenario content, or judge config - a basic check against overfitting the benchmark to itself. **Aggregate numbers only**: no per-scenario detail, judge reasoning, or examples are shown here, so reading this section can't teach you a holdout-specific failure pattern.

#### Per-operator detection rates (faults)

Gate-1 fault metrics are a regression guard on deterministic code, not a headline accuracy claim (see the benchmark plan). JUDGE_ERROR outcomes are excluded from these rates and reported separately below.

| Operator | Category | n | Detection rate (95% CI) | Code/dimension attribution |
|---|---|---|---|---|
| cost_blowout | gate1_fault | 5 | 100% [57%, 100%] (n=5) | 100% [57%, 100%] (n=5) |
| cost_incomplete | gate1_fault | 5 | 100% [57%, 100%] (n=5) | 100% [57%, 100%] (n=5) |
| forbidden_args_injected | gate1_fault | 4 | 100% [51%, 100%] (n=4) | 100% [51%, 100%] (n=4) |
| forbidden_tool_inserted | gate1_fault | 5 | 100% [57%, 100%] (n=5) | 100% [57%, 100%] (n=5) |
| incorrect_final_answer | gate2_fault | 15 | 100% [80%, 100%] (n=15) | 100% [80%, 100%] (n=15) |
| missing_required_arg | gate1_fault | 5 | 100% [57%, 100%] (n=5) | 100% [57%, 100%] (n=5) |
| rubric_item_ignored | gate2_fault | 15 | 33% [15%, 58%] (n=15) | 100% [57%, 100%] (n=5) |
| skill_not_triggered | gate1_fault | 5 | 100% [57%, 100%] (n=5) | 100% [57%, 100%] (n=5) |
| skipped_step | gate1_fault | 5 | 100% [57%, 100%] (n=5) | 100% [57%, 100%] (n=5) |
| swapped_order | gate1_fault | 3 | 100% [44%, 100%] (n=3) | 100% [44%, 100%] (n=3) |
| type_changed_arg | gate1_fault | 1 | 100% [21%, 100%] (n=1) | 100% [21%, 100%] (n=1) |
| unsafe_content_in_output | gate2_fault | 15 | 100% [80%, 100%] (n=15) | 100% [80%, 100%] (n=15) |
| wrong_arg_value | gate1_fault | 5 | 100% [57%, 100%] (n=5) | 100% [57%, 100%] (n=5) |
| wrong_tool_substituted | gate1_fault | 5 | 100% [57%, 100%] (n=5) | 100% [57%, 100%] (n=5) |

#### Gate-1 false-positive rate

Does GATE 1 ALONE incorrectly flag something that should pass, independent of what the judge does afterward? Uses gate1_passed (derived from actual_codes - False only when a real gate-1 failure code is present), not the final pipeline verdict. `clean_base` is the scenario's unmutated trace, judged at k repeats in judge mode (gate 1 should always pass it by construction). A benign item that gate 1 correctly passed but the judge later flagged does NOT count here - see 'Pipeline false-positive rate' below for that.

| Operator | n | Gate-1 FP rate (95% CI) |
|---|---|---|
| clean_base | 15 | 0% [0%, 20%] (n=15) |
| extra_args_under_subset | 9 | 0% [0%, 30%] (n=9) |
| paraphrased_but_correct_final_answer | 15 | 0% [0%, 20%] (n=15) |
| regex_conforming_variable_value | 3 | 0% [0%, 56%] (n=3) |
| reorder_under_any_order | 6 | 0% [0%, 39%] (n=6) |

#### Pipeline false-positive rate (final verdict)

Does the FULL pipeline (gate 1 + gate 2 combined) incorrectly fail something that should pass? This is a strictly-equal-or-higher rate than the gate-1-only table above, since every gate-1 FP is also a pipeline FP, but a benign item can additionally be flagged by the judge even when gate 1 was fine - that gap is exactly what the two tables together are meant to expose. `paraphrased_but_correct_final_answer` only appears when this run used judge mode (it needs a real judge).

| Operator | n | Pipeline FP rate (95% CI) |
|---|---|---|
| clean_base | 15 | 20% [7%, 45%] (n=15) |
| extra_args_under_subset | 9 | 33% [12%, 65%] (n=9) |
| paraphrased_but_correct_final_answer | 15 | 20% [7%, 45%] (n=15) |
| regex_conforming_variable_value | 3 | 100% [44%, 100%] (n=3) |
| reorder_under_any_order | 6 | 0% [0%, 39%] (n=6) |

#### False-positive incidents (detail)

12 false-positive incident(s) in this split. Scenario-level detail is withheld in this aggregate-only section - see the rate tables above.

#### Gate-2 misses (detail)

22 gate-2 miss(es) in this split (fault operators the pipeline failed to catch). Scenario-level detail is withheld in this aggregate-only section - see the per-operator detection-rate table above.

#### hallucinated_action (separate table — see plan caveat)

Reported separately: gate 1 never sees this fault by construction (the removed tool call is never in `expected_tool_calls`), so its detection rate reflects the judge alone, not the gate-1+gate-2 pipeline the other operators measure.

- n=15, detection rate: 20% [7%, 45%] (n=15), attribution: 100% [44%, 100%] (n=3)

#### Judge error rate by operator

| Operator | Error rate (95% CI) |
|---|---|
| clean_base | 0% [0%, 20%] (n=15) |
| extra_args_under_subset | 0% [0%, 30%] (n=9) |
| hallucinated_action | 0% [0%, 20%] (n=15) |
| incorrect_final_answer | 0% [0%, 20%] (n=15) |
| paraphrased_but_correct_final_answer | 0% [0%, 20%] (n=15) |
| regex_conforming_variable_value | 0% [0%, 56%] (n=3) |
| reorder_under_any_order | 0% [0%, 39%] (n=6) |
| rubric_item_ignored | 0% [0%, 20%] (n=15) |
| unsafe_content_in_output | 0% [0%, 20%] (n=15) |

#### Gate-1 contribution

- Total detections: 86
- Caught by gate 1 alone: 48 (56%)
- LLM calls avoided by gate-1 short-circuit: 48

#### Judge flip rate (k repeats)

- Scenario/operator groups with k≥2 judged: 36
- Groups with a non-unanimous verdict: 2 (6%)

#### Judge cost / latency

- Judged items (excluding cache hits): 108
- Mean cost per judged item: $0.000333
- Mean latency per judged item: 3262 ms
