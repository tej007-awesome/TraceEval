# TraceEval: Continuous Effective Trust for Autonomous Agents

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![YC Alignment](https://img.shields.io/badge/YC_S26_RFS-%2312_&_%2315-orange.svg)](#yc-alignment)

**TraceEval** is an open-source CI/CD evaluation framework and policy governance kernel for autonomous AI agents. 

In 2024, developers worried about what AI would *say*. In 2026, enterprises worry about what AI will *do*. Traditional testing evaluates static text outputs. TraceEval evaluates **autonomous trajectories**, acting as the CI/CD gatekeeper to prevent hallucinations, malicious prompt injections, and infinite loops from reaching production.

## The Problem: The "Vibe Coding" Danger
When agents possess ambient agency to execute code and access APIs, testing just the final output is dangerous. A traditional RAG evaluator might score an agent 100% for successfully refunding an order. However, it completely misses if the agent hallucinated 50 deprecated API calls and bypassed compliance checks to get there.

## The Solution: Evaluation-Driven Development (EDD)
TraceEval shifts the industry to **Evaluation-Driven Development**. Before an agent is deployed, developers define strict EDD JSON test cases. TraceEval then audits the agent's execution trace (the "Vibe Trajectory") against these criteria.

### Core Features
- **Trajectory Validation:** Enforce strict tool execution sequences (`EXACT`, `IN_ORDER`, `ANY_ORDER`) before evaluating semantic quality.
- **Post-Run Budget Gate:** After each evaluation run, TraceEval checks `total_token_cost_usd` against a configurable ceiling and blocks deployment if the session exceeded it — preventing "Denial of Wallet" (DoW) infinite-loop behaviors from reaching production.
- **Provider-Agnostic LLM-Judge:** Bring Your Own Judge (BYOJ). Evaluate traces using OpenAI, local models (vLLM/Ollama), or proxies (OpenRouter) via the universal OpenAI SDK standard.
- **Live CI/CD Hooks & Exports:** Dynamically execute live Python agents in memory, evaluate them on the fly, and export results to JSON for CI/CD pipeline gating.
- **Middleware Observability:** Zero-performance-impact logging. Run with `--verbose` to inspect ingestion boundaries and judge latency.

---

## Quickstart

### 1. Installation

**For End-Users & CI/CD Pipelines:**
```bash
pip install traceeval-cli
```
*(Note: The CLI command (`traceeval`) and Python package import (`import traceeval`) remain `traceeval`.)*

**For Contributors:**
```bash
git clone https://github.com/tej007-awesome/TraceEval.git
cd TraceEval
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### 2. Configuration
Create a `.env` file in your root directory. TraceEval is provider-agnostic.

```env
# Example A: Standard OpenAI
LLM_API_KEY="sk-proj-..."
LLM_MODEL_NAME="gpt-4o-mini"

# Example B: Local/Proxy (e.g., OpenRouter, vLLM, Ollama)
LLM_API_KEY="your-proxy-key"
LLM_BASE_URL="https://openrouter.ai/api/v1"
LLM_MODEL_NAME="nvidia/nemotron-3-ultra-550b-a55b:free"
```

### 3. Run an Evaluation

**Mode A: Evaluate a Static/Historical Trace**
Perfect for daily log auditing and regression testing.
```bash
traceeval run --case sample_data/case_01.json --trace sample_data/trace_01.json
```

**Mode B: Evaluate a Live Agent Pipeline**
Perfect for pre-deployment CI/CD gating. Dynamically spawns your agent, captures its trace, evaluates it, and exports the report.
```bash
traceeval run --case sample_data/case_01.json --pipeline examples.reference_agent:process_refund_success --export report.json
```
**Mode C: Evaluate an OpenTelemetry (OTel) Trace**
Audit OpenTelemetry traces adhering to GenAI semantic conventions.
```bash
traceeval run --case sample_data/case_01.json --otel-trace tests/fixtures/otel/refund_happy.json
```

*(Tip: Add `--verbose` right after `traceeval` to view detailed middleware logs!)*

**Expected Output:**
```text
TraceEval initializing...
Mode: Live Pipeline execution (examples.reference_agent:process_refund_success)

⠧ Evaluating Vibe Trajectory & Dimensions via nvidia/nemotron-3-ultra-550b-a55b:free...

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
╭──────────────────────── LLM Judge Reasoning ─────────────────────────╮
│ The agent fully addressed the user's intent by verifying the         │
│ duplicate charge and issuing a full refund, as reflected in the      │
│ final output. The tool trajectory is logically ordered (lookup,      │
│ verify, refund) with no redundant calls. The process is efficient,   │
│ using only necessary steps. No safety or ethical concerns present.   │
╰──────────────────────────────────────────────────────────────────────╯
Report successfully exported to report.json
```

---

## Architecture

TraceEval decouples the **Ingestion Layer** from the **Evaluation Engine** using strict Pydantic v2 data contracts. 

1. **Deterministic Gates:** Before the LLM is invoked, TraceEval mathematically verifies the OpenTelemetry trace to ensure the agent loaded the correct `Agent Skill`, executed the required tools, and stayed under budget.
2. **Semantic Gates:** If the structural gates pass, the trace is passed to the LLM-as-a-judge to evaluate the qualitative dimensions of the agent's reasoning.

---

## Evaluating OpenTelemetry Traces

TraceEval natively ingests OpenTelemetry (OTel) JSON traces adhering to the **OTel GenAI Semantic Conventions**.

```bash
traceeval run --case sample_data/case_01.json --otel-trace tests/fixtures/otel/refund_happy.json
```

### Attributes Ingested
TraceEval inspects the following GenAI span attributes:
- `gen_ai.operation.name`: Identifies span types (`invoke_agent`, `chat`, `execute_tool`).
- `gen_ai.agent.name` & `gen_ai.conversation.id`: Extracts agent skills and session metadata.
- `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`: Tracks per-model token consumption.
- `gen_ai.tool.name` & `gen_ai.tool.call.arguments`: Maps tool trajectories and parameters.
- `gen_ai.output.messages`: Captures the agent's final text response.

### Cost Computation & Custom Pricing
Session token costs are automatically computed by matching `gen_ai.request.model` and token counts against model pricing rates. If pricing is missing for an unknown model, the cost check fails (`"cost could not be verified"`) to prevent unmonitored financial risk.

You can supply custom pricing via `--pricing my_pricing.json`:
```json
{
  "my-custom-model": {
    "input_usd_per_1k": 0.00015,
    "output_usd_per_1k": 0.0006
  }
}
```

> **Privacy Note:** Standard OTel instrumentation often redacts `gen_ai.tool.call.arguments` and `gen_ai.output.messages` to comply with privacy policies. When arguments are omitted, TraceEval outputs non-blocking warnings, and argument matching defaults to `{}`.

---

## Roadmap

v0.2 adds OpenTelemetry GenAI trace ingestion with computed cost and specific failure reasons. Planned next:

- **Flexible argument matching and forbidden tools:** match tool arguments exactly, partially, or not at all (for privacy-redacted traces), and fail any trajectory that calls a denied tool.
- **More reliable LLM judge:** per-rubric-item verdicts, multiple samples, retries, and an offline mock judge for CI pipelines that can't call an external LLM.
- **Meta-evaluation benchmark:** a labelled set of good and bad traces that measures how accurately TraceEval itself catches failures.

To track granular progress, see our [GitHub Issues](https://github.com/tej007-awesome/TraceEval/issues).

---

## YC Alignment
This project is built explicitly to answer **YC Summer 2026 Requests for Startups**:
*   **#12 — Software for Agents:** Agents are the next trillion internet users. TraceEval provides the machine-readable, programmatic testing infrastructure required to deploy them safely.
*   **#15 — The AI Operating System for Companies:** TraceEval acts as the "Kernel Panic monitor" and compliance gateway for the enterprise AI OS, making autonomous behavior legible and controllable to stakeholders.