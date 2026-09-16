# Authoring a base scenario

This describes how to write one `benchmarks/scenarios/<domain>/<id>.json` file. Two
complete examples already exist in `benchmarks/scenarios/refunds/` — read both before
writing a new one; they're the templates, not just references.

## Target: ~20 scenarios total, 4 per domain, across 5 domains

Domains: `refunds`, `search`, `file_ops`, `scheduling`, `code_tools`. Use exactly these
five domain names (they're the subdirectory names). 4 scenarios per domain unless a domain
genuinely needs more to hit the mode-coverage quotas below — don't pad.

## Required top-level fields (see `benchmarks/models.py::Scenario`)

- `id`: unique string, e.g. `"refund_002_subset_regex"`. Convention: `<domain-singular>_<3-digit-number>_<short-hint>`.
- `domain`: one of the five above, must match the subdirectory.
- `case`: a full `EDDTestCase` (same schema as `sample_data/case_01.json` / `test_suite/*.json`).
- `trace`: a full `AgentTrace` — the **clean**, should-pass trace for this case.
- `gate2_variants`: list of hand-authored `Gate2Variant` objects (see below).

## Constraints every scenario must satisfy (so fault operators have something to act on)

1. **Non-empty `forbidden_tools` and/or `forbidden_args`** on `case`, even though the clean
   trace never triggers them. Pick something domain-plausible and genuinely dangerous
   (`delete_account`, `wire_transfer`, `drop_table`, `force_push`, `cancel_all_bookings` —
   not a strawman). Without this, `forbidden_tool_inserted`/`forbidden_args_injected` have
   nothing to insert against and are skipped for that scenario (logged, not silently OK).
2. **`expected_skill` is set.** Without it, `skill_not_triggered` is inapplicable.
3. **At least one expected call uses `SUBSET`, `REGEX`, or `ANY`** on at least 1/3 of all
   scenarios (across the full set of ~20, not necessarily every one) — needed for
   `extra_args_under_subset` / `regex_conforming_variable_value` and the corresponding
   `type_changed_arg`/`missing_required_arg` fault operators to have a target. If your
   scenario has no flexible-mode field, that's fine as long as *other* scenarios in the set
   cover it — check the running tally before submitting a batch.
4. **At least 1/3 of scenarios use `trajectory_mode: "ANY_ORDER"`** across the full set —
   needed for `reorder_under_any_order` and to exercise the "swapped_order routes to
   benign under ANY_ORDER" rule. The rest use `IN_ORDER` (prefer this over `EXACT` — EXACT
   scenarios can't host most benign controls, since any extra/reordered call fails EXACT by
   definition; a couple of `EXACT` scenarios are fine for `TRAJECTORY_LENGTH_MISMATCH`
   coverage, but don't make most of the set EXACT).
5. **At least 2+ expected tool calls** — `skipped_step`/`swapped_order`/`duplicated_step`
   need something to remove/swap/duplicate.

## Gate-2 variants: hand-authored, not templated

Each variant is a full alternate `final_output` string (plus, for `hallucinated_action`, a
tool name to drop). **Do not write a script that generates these from the clean
`final_output` by find-and-replace or templating** — the whole point of hand-authoring is
that an RNG cannot produce a *realistic* wrong answer or a *genuinely hard* paraphrase; a
templated one will be trivially easy for both TraceEval's judge and a human reviewer to
spot, which defeats the benchmark.

Write as many of these five kinds as apply to the scenario (not every scenario needs every
kind — `hallucinated_action` in particular only applies where there's a real "soft" action
to hallucinate):

- **`incorrect_final_answer`** (`expected_dimension: "functional_correctness"`) — state a
  wrong *concrete* fact: wrong amount, wrong order/ticket/file number, wrong date, wrong
  outcome. Not vague ("something went wrong") — specific and checkable against the trace.
- **`rubric_item_ignored`** (`expected_dimension` — usually `"intent_satisfaction"`) — drop
  acknowledgment of exactly one rubric item while keeping everything else. The answer
  should still read as complete and professional on a skim; the omission should only be
  obvious when checked against the rubric list.
- **`unsafe_content_in_output`** (`expected_dimension: "safety_and_rai"`) — a realistic,
  policy-safe-to-write violation: leaking another customer's identifying details, a
  dismissive/unprofessional tone, an inappropriate offer (e.g. "I can waive the verification
  step for you" for a security-sensitive action). Nothing genuinely offensive, nothing
  cartoonish ("I hate you" is not realistic production output — a subtle boundary violation
  is).
- **`hallucinated_action`** (`expected_dimension` — usually `"functional_correctness"`) —
  `soft_action_tool` names a tool that is **not** in `case.expected_tool_calls` (checked at
  load time) but **is** in the clean `trace.executed_tools` (also checked at load time); the
  variant's `final_output` claims that action's outcome anyway. The operator removes that
  call from the trace and swaps in this `final_output`. Reported in its own table (see
  `benchmarks/metrics.py`) with the caveat that gate 1 never sees this fault — it's purely a
  test of whether the judge notices an unsupported claim against the trajectory it does see.
- **`paraphrased_but_correct_final_answer`** (`expected_passed: true`, no
  `expected_dimension`) — reword the clean `final_output`: different sentence order,
  synonyms, tone (more casual/more formal), maybe reordering which fact comes first. **Every
  fact and every rubric-relevant point from the clean answer must still be present and
  correct.** This is the hardest one to write well and the one most likely to produce real
  judge noise — don't make it a trivial synonym swap; make it genuinely differently-phrased
  while unambiguously still correct.

## What makes a variant realistic vs. cartoonish

Realistic: a wrong dollar amount that's plausible for the scenario ($45 instead of $54, not
$999999), a dropped acknowledgment that reads as an efficient-but-slightly-incomplete reply
rather than obviously broken, an unsafe-content example that a real support agent might
plausibly slip into if not careful. Cartoonish (avoid): "I refunded you $1,000,000",
"Your request has been ignored", anything that no real agent output would resemble. If a
variant would be trivially obvious to a human skimming it in under two seconds, rewrite it.

## Detectability Rules for Gate-2 Variants

1. **Detectability for `incorrect_final_answer`**: Every changed fact in `incorrect_final_answer` must be explicitly contradicted by information visible to the LLM judge — specifically within `input_prompt`, tool call arguments in `executed_tools`, or `rubric` text. Note that the judge does NOT see tool call return values (`ToolCall` carries no result payload). If a fact (e.g. refund amount, calculated total, target file/ID) is modified in the variant, that fact must be present in the prompt, tool call args, or rubric, or added to tool call args if realistic. Change exactly one concrete fact per variant.
2. **Detectability for `hallucinated_action`**: The `final_output` (both clean and the variant) must explicitly claim that the soft action tool named in `soft_action_tool` occurred. If the clean output does not mention the soft action's outcome, update the clean output (and paraphrase/hallucinated variants) to explicitly state it, or omit the `hallucinated_action` variant if no soft action claim is natural.
3. **Mild and Realistic `unsafe_content_in_output`**: Unsafe content must reflect plausible production agent boundary violations (e.g., disclosing another customer's details/privacy, inappropriate offer to bypass policy, subtle unprofessional tone, unverified vendor claims). Avoid cartoonish or overly blatant security breaches (e.g., "steal the private API keys before they get rotated").


## Reuse

`tests/fixtures/otel/refund_happy.json` / `refund_no_args.json` are usable as two of the
refund domain's base scenarios (wrap the loaded `AgentTrace` and pair it with a matching
`EDDTestCase`) rather than writing new refund traces from scratch — but they still need
`gate2_variants` authored, since the fixtures only carry the clean trace.
