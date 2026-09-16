# TraceEval

[![PyPI](https://img.shields.io/pypi/v/traceeval-cli.svg)](https://pypi.org/project/traceeval-cli/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**TraceEval is a CLI for testing AI agent trajectories in CI.** You write a test case describing what an agent *should* do: which tools it calls, in what order, within what budget, and what a good answer looks like. TraceEval checks the agent's trace against it and exits non-zero if it fails, so a pipeline can block the deploy.

## Why trajectories

Checking only an agent's final answer misses how it got there. An agent can reply "your refund has been issued" while skipping the duplicate-charge check, calling tools in the wrong order, or spending far more than it should. TraceEval tests the path, not just the output.

## How it works

Evaluation runs in two gates:

1. **Deterministic gate (free, instant).** Checks the tool sequence against the test case (`EXACT`, `IN_ORDER`, or `ANY_ORDER`), confirms the expected agent skill ran, and checks the session cost against a budget. If anything fails, evaluation stops here with specific reasons, and no LLM is called.
2. **Semantic gate (LLM-as-judge).** Only if gate 1 passes, an LLM scores the output on five dimensions against your rubric. Any score below the threshold fails the case, and a missing score on a required dimension also fails it.

Every failure explains itself, for example:

```text
✗ expected check_duplicate_charge(order_id='4521') at position 1 was never called
✗ cost $5.5000 exceeds budget $0.1000
```

## Features

- **Three trace sources:** TraceEval JSON traces, OpenTelemetry GenAI traces, or a live Python agent function run in-process
- **OpenTelemetry ingestion:** reads OTel GenAI semantic-convention spans directly, with no OpenTelemetry runtime dependency
- **Computed cost:** from OTel token usage × a pricing table; unknown model pricing fails the budget check instead of reporting $0
- **Flexible argument matching:** exact, subset, regex, or presence-only, set per call or per field
- **Forbidden tools:** fail the case if a denied tool is called at all, or called with specific arguments
- **Specific failure reasons** for every deterministic and semantic failure
- **Bring your own judge:** any OpenAI-compatible endpoint, including OpenAI, OpenRouter, vLLM, and Ollama
- **CI-friendly:** exit code 1 on failure, plus JSON export of results

## Quickstart

### Install

```bash
pip install traceeval-cli
```

The command and the Python import are both `traceeval`.

### Configure the judge

Create a `.env` file:

```env
# OpenAI
LLM_API_KEY="sk-proj-..."
LLM_MODEL_NAME="gpt-4o-mini"

# Or any OpenAI-compatible endpoint (OpenRouter, vLLM, Ollama)
LLM_API_KEY="your-key"
LLM_BASE_URL="https://openrouter.ai/api/v1"
LLM_MODEL_NAME="your-model-name"
```

### Run an evaluation

The examples below use files from this repository, so clone it first to try them.

**A TraceEval JSON trace:**
```bash
traceeval run --case sample_data/case_01.json --trace sample_data/trace_01.json
```

**An OpenTelemetry trace:**
```bash
traceeval run --case sample_data/case_01.json --otel-trace tests/fixtures/otel/refund_happy.json
```

**A live agent function**, exporting the result:
```bash
traceeval run --case sample_data/case_01.json --pipeline examples.reference_agent:process_refund_success --export report.json
```

Add `--verbose` after `traceeval` for detailed logs.

**Example output:**
```text
Mode: OTel trace (tests/fixtures/otel/refund_happy.json)

Result: PASSED (Safe to Deploy)
Case ID: refund_001

      Evaluation Dimensions
┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Dimension              ┃ Score ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ Intent Satisfaction    │   1.0 │
│ Functional Correctness │   1.0 │
│ Trajectory Quality     │   1.0 │
│ Cost Efficiency        │   1.0 │
│ Safety & RAI           │   1.0 │
└────────────────────────┴───────┘
```

## Writing a test case

```json
{
  "case_id": "refund_001",
  "input_prompt": "I was charged twice for order #4521. Please fix this.",
  "expected_skill": "refund-processor",
  "expected_tool_calls": [
    {"tool_name": "lookup_order", "args": {"order_id": "4521"}},
    {"tool_name": "check_duplicate_charge", "args": {"order_id": "4521"}},
    {"tool_name": "issue_refund", "args": {"order_id": "4521", "amount": "full"}}
  ],
  "trajectory_mode": "IN_ORDER",
  "rubric": [
    "Acknowledges the duplicate charge.",
    "Confirms the refund has been processed.",
    "Maintains a polite, professional tone."
  ]
}
```

| Mode | Passes when |
|---|---|
| `EXACT` | The trace contains exactly these calls, in this order, with nothing extra |
| `IN_ORDER` | These calls appear in this order; other calls may occur in between |
| `ANY_ORDER` | All these calls appear, in any order; other calls may occur |

## Argument matching

Each entry in `expected_tool_calls` can set `arg_match_mode` to control how its `args` are
compared against the actual call. The default, `EXACT`, preserves the original all-or-nothing
behavior.

| Mode | Passes when |
|---|---|
| `EXACT` (default) | The actual args have exactly the same keys as expected, with equal values |
| `SUBSET` | Every expected key is present with an equal value; extra actual keys are allowed |
| `REGEX` | Every expected key is present and its value, stringified, matches the expected value as a regex pattern (`re.search`, so anchor with `^...$` for a full match) |
| `ANY` | Every expected key is merely present; its value is ignored |

Only `EXACT` requires the actual args to have exactly the expected keys and no more.
`SUBSET`/`REGEX`/`ANY` all allow extra, unlisted actual keys.

Individual fields can override the call's mode with `field_overrides` (a map of arg name to
mode). Note that `EXACT` stays key-set-strict even when a field is overridden — an extra actual
key still fails the call, even if the overridden field's own comparison would have matched:

```json
{
  "tool_name": "check_duplicate_charge",
  "args": { "order_id": "4521", "session_token": "^sess_[a-f0-9]{8}$" },
  "arg_match_mode": "EXACT",
  "field_overrides": { "session_token": "REGEX" }
}
```

`REGEX` mode stringifies non-string actual values before matching (`str(value)`), so a boolean
becomes the literal string `"True"`/`"False"` and a dict or list becomes its Python `repr()`-like
string form — write patterns with that in mind for non-string fields.

## Forbidden tools

A test case can declare tools that must never appear anywhere in the trajectory, and arg patterns
that make an otherwise-allowed tool forbidden under specific conditions:

```json
{
  "forbidden_tools": ["delete_account", "wire_transfer"],
  "forbidden_args": {
    "issue_refund": [
      { "amount": "unlimited" },
      { "currency": "^(RUB|KPW)$" }
    ]
  }
}
```

`forbidden_args` maps a tool name to a list of rule-sets; a call is forbidden if **all** patterns
in **any one** rule-set match (rule-sets are OR'd, patterns within a rule-set are AND'd). A tool
name cannot appear in both `expected_tool_calls` and `forbidden_tools` — that's a
self-contradictory test case and is rejected when the file is loaded, not when it's evaluated.
Any forbidden-tool or forbidden-args hit is a deterministic gate-1 failure: it's checked with zero
LLM calls and short-circuits the semantic gate exactly like a trajectory or cost failure does.

## Evaluating OpenTelemetry traces

TraceEval reads OTLP JSON traces that follow the OpenTelemetry GenAI semantic conventions:

| Span attribute | Used for |
|---|---|
| `gen_ai.operation.name` | Span type: `invoke_agent`, `chat`, `execute_tool` |
| `gen_ai.tool.name`, `gen_ai.tool.call.arguments` | Tool calls, ordered by span start time |
| `gen_ai.agent.name` | The agent skill that ran |
| `gen_ai.conversation.id` | Session ID (falls back to the trace ID) |
| `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` | Cost |
| `gen_ai.output.messages` | Final output |

The GenAI conventions are still evolving, so attribute names live in a single module (`otel_attributes.py`).

### Cost and pricing

Cost is computed from each `chat` span's token counts and a pricing table. The built-in table covers only `gpt-4o-mini`. For any other model, supply a pricing file with prices per million tokens:

```json
{
  "your-model-name": {
    "input_per_1m_usd": 0.15,
    "output_per_1m_usd": 0.60
  }
}
```

```bash
traceeval run --case case.json --otel-trace trace.json --pricing pricing.json
```

If any model in the trace has no price, the budget check **fails** with "cost could not be verified." Prices change, so treat the built-in table as a starting point, not a billing source.

### Privacy-redacted traces

Many OTel instrumentations don't record tool arguments or message content by default. TraceEval still loads these traces and prints a warning, but the missing arguments are treated as empty, so `EXACT` argument matching will fail. Use `SUBSET` or `ANY` mode on the affected calls if the redacted arguments aren't essential to the check.

## Limitations

- `SUBSET`/`REGEX` argument matching only inspects the top level of an arg's value; a nested dict or list is compared as a whole (via equality for `SUBSET`, stringified for `REGEX`), not recursively.
- `IN_ORDER` and `ANY_ORDER` allow extra tool calls, so they won't catch an unexpected dangerous call by themselves — pair them with `forbidden_tools`/`forbidden_args`, or use `EXACT`.
- The judge makes a single call per case, with no multi-sample aggregation yet.
- JSON traces report their own cost. Only OTel traces have computed cost.
- The bundled benchmark in `test_suite/` is small and synthetic.

## How it compares

Established tools cover much of this space and do more. [DeepEval](https://github.com/confident-ai/deepeval) offers a large metric library with pytest integration, and LangChain's [agentevals](https://github.com/langchain-ai/agentevals) provides trajectory-match evaluators with configurable modes. TraceEval is deliberately small: a single CLI that combines deterministic trajectory checks, cost budgets, and an LLM judge into one pass/fail gate, with OTel traces as a first-class input.

## Roadmap

- **More reliable LLM judge:** per-rubric verdicts, multiple samples, retries, and an offline mock judge for CI ([#6](https://github.com/tej007-awesome/TraceEval/issues/6))
- **Meta-evaluation benchmark:** a labelled set of good and bad traces that measures how accurately TraceEval catches failures ([#7](https://github.com/tej007-awesome/TraceEval/issues/7))

## Contributing

```bash
git clone https://github.com/tej007-awesome/TraceEval.git
cd TraceEval
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest && ruff check .
```

## License

MIT