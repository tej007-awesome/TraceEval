# Frozen benchmark baseline (#7)

This records the exact scenario set, holdout split, and judge configuration behind
`benchmarks/baseline_results.json` / `benchmarks/baseline_report.md` - the reference point
`#6` (and any future harness/prompt change) is measured against.

**Scenarios are frozen as of this commit.** Any later edit to a file under
`benchmarks/scenarios/` (including a rubric fix, a new `independent_call_groups` entry, or a
new scenario) must be recorded in the "Post-freeze changes" section below with a reason and
the commit that made it. Do not silently edit a scenario file without adding an entry here.

## Freeze point

- **Commit SHA**: `a3cc79136d1f48d451e98202bc50e9f86c0f7697` (merge of PR #17, "feat:
  benchmark judge run, attribution, review tooling (#7 phase 1c)", plus its two follow-up
  review-fix commits `a7865b4` and `5490ae9`)
- **Scenario count**: 20 (4 per domain x 5 domains: refunds, search, file_ops, scheduling,
  code_tools)

## Scenario file hashes (sha256)

```
e923b779cba5ef55708b49522193109b4b0aa57f91ebcf1147d508b37cdd7c9a  benchmarks/scenarios/code_tools/code_tools_001_in_order_subset.json
f33c43672c0bcf1392f8c65d3b30b011726f375c4071f9ff38ad808f3b229a87  benchmarks/scenarios/code_tools/code_tools_002_any_order_regex.json
99dd546dca16408104cbe1bcb70dcb0420507ca65f07babdef760b730c400dfd  benchmarks/scenarios/code_tools/code_tools_003_any_order_subset.json
5409cb168f1cb155164d8bde28d959c4af3b0ef21c905b23acda079c4be67ed0  benchmarks/scenarios/code_tools/code_tools_004_exact_mode.json
9ec3697210d796592fda1d2aa1095f9966215c7d5506481883d4c6f4925a63c8  benchmarks/scenarios/file_ops/file_ops_001_in_order_subset.json
dd4927f26dee2d30ed8b87ab31d8743e248abad1fc964177370073ae481a36dc  benchmarks/scenarios/file_ops/file_ops_002_any_order_regex.json
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
a28014c0f128d0514a552c9087c76b88039db1ca0541c3f4b964bdc51b9c2f6c  benchmarks/scenarios/search/search_001_in_order_regex.json
c2966ff10125c9b356960c76381f82855baaf5ed014fd93047462af0ec9c54b1  benchmarks/scenarios/search/search_002_any_order_subset.json
a621dc7c10db8699eddd38578dd7b721992c6c2f6d5eac7afe12e6ffe13373fd  benchmarks/scenarios/search/search_003_any_order_multi.json
45b4aa898c594aeb34c4dd4cd3286048c7e5390d85ef4a3bfbd87c94bebcfa62  benchmarks/scenarios/search/search_004_exact_mode.json
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
- **Cache**: refreshed for this run (`--refresh-cache`) - the scenario set changed since the
  phase 1c pilot/full runs (rubric literal fixes, `independent_call_groups` additions), so
  this baseline recomputes every judge call from scratch rather than mixing in
  pre-freeze-content cache entries.

## Post-freeze changes

_(none yet - add an entry here, with commit SHA and reason, the first time any file under
`benchmarks/scenarios/` changes after this freeze point)_
