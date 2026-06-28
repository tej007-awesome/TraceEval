```markdown
# AgentCI: Continuous Effective Trust for Autonomous Agents

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![YC Alignment](https://img.shields.io/badge/YC_S26_RFS-%2312_&_%2315-orange.svg)](#yc-alignment)

**AgentCI** is an open-source CI/CD evaluation framework and policy governance kernel for autonomous AI agents. 

In 2024, developers worried about what AI would *say*. In 2026, enterprises worry about what AI will *do*. Traditional testing evaluates static text outputs. AgentCI evaluates **autonomous trajectories**, acting as the CI/CD gatekeeper to prevent hallucinations, malicious prompt injections, and infinite loops from reaching production.

## The Problem: The "Vibe Coding" Danger
When agents possess ambient agency to execute code and access APIs, testing just the final output is dangerous. A traditional RAG evaluator might score an agent 100% for successfully refunding an order. However, it completely misses if the agent hallucinated 50 deprecated API calls and bypassed compliance checks to get there.

## The Solution: Evaluation-Driven Development (EDD)
AgentCI shifts the industry to **Evaluation-Driven Development**. Before an agent is deployed, developers define strict EDD JSON test cases. AgentCI then audits the agent's OpenTelemetry trace (the "Vibe Trajectory") against these criteria.

### Core Features
- **Trajectory Validation:** Enforce strict tool execution sequences (`EXACT`, `IN_ORDER`, `ANY_ORDER`) before evaluating semantic quality.
- **Cost Circuit Breakers:** Track `total_token_cost_usd` per session to automatically block deployments that exhibit "Denial of Wallet" (DoW) infinite-loop behaviors.
- **Provider-Agnostic LLM-Judge:** Bring Your Own Judge (BYOJ). Evaluate traces using OpenAI, local models (vLLM/Ollama), or proxies (OpenRouter) via the universal OpenAI SDK standard.
- **Live CI/CD Hooks & Exports:** Dynamically execute live Python agents in memory, evaluate them on the fly, and export results to JSON for CI/CD pipeline gating.
- **Middleware Observability:** Zero-performance-impact logging. Run with `--verbose` to inspect ingestion boundaries and judge latency.

---

## Quickstart

### 1. Installation

**For End-Users & CI/CD Pipelines:**
```bash
pip install agentci
```

**For Contributors:**
```bash
git clone https://github.com/tej007-awesome/AgentCI.git
cd AgentCI
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### 2. Configuration
Create a `.env` file in your root directory. AgentCI is provider-agnostic.

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
agentci run --case sample_data/case_01.json --trace sample_data/trace_01.json
```

**Mode B: Evaluate a Live Agent Pipeline**
Perfect for pre-deployment CI/CD gating. Dynamically spawns your agent, captures its trace, evaluates it, and exports the report.
```bash
agentci run --case sample_data/case_01.json --pipeline examples.reference_agent:process_refund_success --export report.json
```

*(Tip: Add `--verbose` right after `agentci` to view detailed middleware logs!)*

**Expected Output:**
```text
AgentCI initializing...
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

AgentCI decouples the **Ingestion Layer** from the **Evaluation Engine** using strict Pydantic v2 data contracts. 

1. **Deterministic Gates:** Before the LLM is invoked, AgentCI mathematically verifies the OpenTelemetry trace to ensure the agent loaded the correct `Agent Skill`, executed the required tools, and stayed under budget.
2. **Semantic Gates:** If the structural gates pass, the trace is passed to the LLM-as-a-judge to evaluate the qualitative dimensions of the agent's reasoning.

---

## Vision & What's Next (V1)

We have successfully shipped **v0** (Core EDD Schema, Trajectory Validator, BYOJ Engine, Live Pipeline Hook). To track the granular V1 roadmap, please see our [GitHub Issues](https://github.com/tej007-awesome/AgentCI/issues).

Upcoming architectural milestones include:
- **Universal OpenTelemetry Adapters:** Abstracting the Ingestion layer so AgentCI can seamlessly evaluate traces from LangGraph, OpenAI Swarm, Claude SDK, or raw MCP servers.
- **Automated Green Teaming:** Automatically auto-refactoring failing `SKILL.md` files if a trajectory triggers a security violation.
- **Prefect Orchestration:** Distributed CI/CD scheduling for high-volume enterprise workloads.

---

## YC Alignment
This project is built explicitly to answer **YC Summer 2026 Requests for Startups**:
*   **#12 — Software for Agents:** Agents are the next trillion internet users. AgentCI provides the machine-readable, programmatic testing infrastructure required to deploy them safely.
*   **#15 — The AI Operating System for Companies:** AgentCI acts as the "Kernel Panic monitor" and compliance gateway for the enterprise AI OS, making autonomous behavior legible and controllable to stakeholders.