# Frozen benchmark baseline (#7)

This records the exact scenario set, holdout split, and judge configuration behind
`benchmarks/baseline_results.json` / `benchmarks/baseline_report.md` - the reference point
`#6` (and any future harness/prompt change) is measured against.

**This is baseline v2.** It supersedes baseline v1 (freeze commit `a3cc791`, results kept at
`benchmarks/baseline_v1_results.json` for comparison). Human review of the v1 review queue
found 6 scenario bugs - items the judge was right (or wrong) about only because the scenario
itself was broken - fixed in PR #20 (`259de8d`, "fix: scenario bugs found in baseline human
review (#7)"). v1 numbers for the affected scenarios/operators measured scenario defects, not
judge quality, so v1 must not be used as the comparison point for `#6` or later changes. See
"Post-freeze changes" below for each fix, and the "Baseline v1 vs v2" section of
`benchmarks/baseline_report.md` for the per-operator effect.

**Scenarios are frozen as of this commit.** Any later edit to a file under
`benchmarks/scenarios/` (including a rubric fix, a new `independent_call_groups` entry, or a
new scenario) must be recorded in the "Post-freeze changes" section below with a reason and
the commit that made it. Do not silently edit a scenario file without adding an entry here.

## Freeze point

- **Commit SHA**: `ab36dfab7c89d66eda73bc0ead13dc593c007369` (merge of PR #20, "fix: scenario
  bugs found in baseline human review (#7)")
- **Supersedes**: baseline v1, commit `a3cc79136d1f48d451e98202bc50e9f86c0f7697` (merge of
  PR #17 plus follow-ups `a7865b4` and `5490ae9`)
- **Scenario count**: 20 (4 per domain x 5 domains: refunds, search, file_ops, scheduling,
  code_tools)

## Scenario file hashes (sha256)

Recomputed at the v2 freeze commit. Four files differ from v1: `file_ops_002_any_order_regex`,
`search_001_in_order_regex`, `search_002_any_order_subset`, `search_004_exact_mode`.

```
e923b779cba5ef55708b49522193109b4b0aa57f91ebcf1147d508b37cdd7c9a  benchmarks/scenarios/code_tools/code_tools_001_in_order_subset.json
f33c43672c0bcf1392f8c65d3b30b011726f375c4071f9ff38ad808f3b229a87  benchmarks/scenarios/code_tools/code_tools_002_any_order_regex.json
99dd546dca16408104cbe1bcb70dcb0420507ca65f07babdef760b730c400dfd  benchmarks/scenarios/code_tools/code_tools_003_any_order_subset.json
5409cb168f1cb155164d8bde28d959c4af3b0ef21c905b23acda079c4be67ed0  benchmarks/scenarios/code_tools/code_tools_004_exact_mode.json
9ec3697210d796592fda1d2aa1095f9966215c7d5506481883d4c6f4925a63c8  benchmarks/scenarios/file_ops/file_ops_001_in_order_subset.json
d0fcba414908341dd743996288efec8833a548a4fee8d80a650ba61b8ef930cd  benchmarks/scenarios/file_ops/file_ops_002_any_order_regex.json
7be0a2fa13518508ff02756a82ca4ed3ae8aea2ff9c3641b9ff9c94caf83dfc5  benchmarks/scenarios/file_ops/file_ops_003_any_order_subset.json
30d3c34ba0dab13abdfdc09bdd8dd102e6ec5f771caafadce275519fdfaf6012  benchmarks/scenarios/file_ops/file_ops_004_in_order_any.json
27e2a686db16dd942cd22852648de10ac45fff082ad82c100e68c8be39baa45c  benchmarks/scenarios/refunds/refund_001_in_order_subset_regex.json
9e6c7f78d0631ee26cf2c50b90d862233251f7c7ace7297fc6f9f325a0f39de6  benchmarks/scenarios/refunds/refund_002_any_order.json
f53933c2dea73ee2dea8bde14621e07e2092f051d2bd32274becd11c6fe382d8  benchmarks/scenarios/refunds/refund_003_exact_mode.json
9f7c311f8f8daabd45177b9e2c1a643181383fb4d5fa7799c53a463513b73082  benchmarks/scenarios/refunds/refund_004_dispute_subset.json
4c5ff657d2afa167016f6536c40ecd7e6e343ff5732c394610d07b1a71c30561  benchmarks/scenarios/scheduling/scheduling_001_in_order_regex.json
2b47d6e5f05a2184d692011a8acf1189b388ff5ee238c0e9b0219344ac2fdc7d  benchmarks/scenarios/scheduling/scheduling_002_any_order_subset.json
fb872face6507863613602a39159c559ab3edfbe123ff61466a13a5e368b24bd  benchmarks/scenarios/scheduling/scheduling_003_any_order_any.json
0ef452f17c2d1e9cdabd2071013330ce655ece1aea4ae89d774d21d71643f67a  benchmarks/scenarios/scheduling/scheduling_004_exact_mode.json
805781b8d49969f3c18a1ccccf9ef8b6ae512c21628a38547250087c0b83e485  benchmarks/scenarios/search/search_001_in_order_regex.json
420ff13947764248bff8cc08093340e8615b876396681bdae3dc564559caf273  benchmarks/scenarios/search/search_002_any_order_subset.json
a621dc7c10db8699eddd38578dd7b721992c6c2f6d5eac7afe12e6ffe13373fd  benchmarks/scenarios/search/search_003_any_order_multi.json
3a24b5809530e46448f38963825d892ae217f8cc9c7d2f9b6a36444e0fe9d240  benchmarks/scenarios/search/search_004_exact_mode.json
```

Regenerate with: `find benchmarks/scenarios -name "*.json" | sort | xargs shasum -a 256`

## Holdout split

Recorded in the committed `benchmarks/holdout.json` (seed `20260916`, one scenario per
domain):

- `code_tools_001_in_order_subset`
- `file_ops_004_in_order_any`
- `refund_002_any_order`
- `scheduling_001_in_order_regex`
- `search_003_any_order_multi`

## Judge configuration

- **Model**: `openai/gpt-5.6-luna-20260709` (via OpenRouter)
- **Temperature**: `0.0`
- **Reasoning effort**: `none`
- **Seed** (operator mutation RNG, distinct from the holdout seed above): `0`
- **k** (judge repeats per item): `3`
- **Concurrency**: `8`
- **Cost cap**: `--max-total-cost-usd 2.00`
- **Cache**: refreshed for this run (`--refresh-cache`) - four scenario files and the regex
  operator's conforming-value generator changed since v1, so this baseline recomputes every
  judge call from scratch rather than mixing in v1-content cache entries.

Command:

```
python -m benchmarks.run --seed 0 --k 3 --include-holdout --concurrency 8 \
  --max-total-cost-usd 2.00 --refresh-cache --output benchmarks/baseline_results.json
```

## Post-freeze changes

These entries record changes made after the v1 freeze. Baseline v2 was frozen *after* all of
them; any change from here on gets a new entry below, dated against the v2 freeze commit.

### PR #20 "fix: scenario bugs found in baseline human review (#7)" (included in v2)

- **`benchmarks/operators.py`** (`regex_conforming_variable_value` generator, not a scenario
  file, listed because it changes benign items):
  - **Reason**: The conforming-value generator only matched `^https://host/.*$` patterns and
    replaced the path with unrelated pages (e.g. `docs.example.com/company-info`), so the
    "benign" variant cited an irrelevant page and the judge correctly failed it. It now
    varies the original URL (query/fragment/sub-path) and only keeps candidates the pattern
    still matches.

- **`benchmarks/scenarios/file_ops/file_ops_002_any_order_regex.json`**:
  - **Reason**: Clean trace called `write_environment_var` instead of updating `/etc/config/app.json` as requested in the prompt, and contained the typo "environment environment configuration" in `final_output`. Fixed by consistently using `write_config_value` with the filepath in `expected_tool_calls`, `forbidden_args`, and `executed_tools`, and corrected `final_output` to confirm updating `/etc/config/app.json`.

- **`benchmarks/scenarios/search/search_001_in_order_regex.json`**:
  - **Reason**: The judge penalized `docs.example.com` for not being an authoritative source, failing clean and benign items. Replaced the fictional domain with the plausible vendor docs domain `https://docs.agentsdk.dev` across `expected_tool_calls` regex, `executed_tools`, `final_output`, and all gate-2 variants.

- **`benchmarks/scenarios/search/search_002_any_order_subset.json`**:
  - **Reason**: The `rubric_item_ignored` variant retained both prices ($0.04/hr vs $0.035/hr), conveying that Cloud-B was cheaper implicitly and failing to remove the underlying comparative information required by rubric item 2. Fixed variant to report only Cloud-A pricing so the comparison is not derivable.

- **`benchmarks/scenarios/search/search_004_exact_mode.json`**:
  - **Reason**: The `rubric_item_ignored` variant attempted to omit policy document `SOC2-SEC-09` by citing clause `SOC2-SEC-09-A`, but because the clause code contains the policy code as a substring, the information was not actually removed. Updated variant to target omission of clause extraction (rubric item 2) so the required information is completely removed.

### PR "fix: search_001 substantive multi-release clean output (#7)"

- **`benchmarks/scenarios/search/search_001_in_order_regex.json`**:
  - **Reason**: The clean `final_output` only covered a single release and provided a thin summary of API changes, failing benign items when the prompt requested documentation and API changes for SDK releases (plural). Expanded the clean output (and updated all gate-2 variants and paraphrase to stay consistent) to substantively cover multiple 2026 releases (v3.0 major and v3.1 incremental) with concrete API changes (token-level streaming callbacks, strict JSON Schema 2020-12 tool validation, async multi-agent pipelines, session persistence hooks, and token-budget guards), while preserving rubric criteria and variant detectability rules.
