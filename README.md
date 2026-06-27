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
- **Multidimensional LLM-Judge:** Native integration with `google-genai` (Gemini 2.5) to score agents across Intent Satisfaction, Functional Correctness, Trajectory Quality, and Safety & RAI.
- **Terminal-Native DX:** Built on `Typer` and `Rich` for beautiful, actionable CI/CD pipeline outputs.

---

## Quickstart

### 1. Installation
AgentCI is built for speed. We recommend using `uv` for lightning-fast dependency resolution.

```bash
git clone https://github.com/yourusername/AgentCI.git
cd AgentCI
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### 2. Configuration
Create a `.env` file in the root directory and add your Google Gemini Developer API key:
```env
GEMINI_API_KEY="AIzaSy..."
```

### 3. Run Your First Evaluation
AgentCI operates on two files: a **Case** (the EDD specification) and a **Trace** (the actual runtime execution logs from the agent).

```bash
agentci run --case sample_data/case_01.json --trace sample_data/trace_01.json
```

**Expected Output:**
```text
AgentCI initializing...

⠧ Evaluating Vibe Trajectory & Dimensions via Gemini...

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
│ The agent fully satisfied the user's intent by acknowledging the     │
│ duplicate charge and confirming that a full refund has been issued.  │
│ The executed trajectory was logical and efficient, using necessary   │
│ tools (lookup_order, check_duplicate_charge, issue_refund) without   │
│ any redundant steps.                                                 │
╰──────────────────────────────────────────────────────────────────────╯
```

---

## Architecture

AgentCI decouples the **Ingestion Layer** from the **Evaluation Engine** using strict Pydantic v2 data contracts. 

1. **Deterministic Gates:** Before the LLM is invoked, AgentCI mathematically verifies the OpenTelemetry trace to ensure the agent loaded the correct `Agent Skill`, executed the required tools, and stayed under budget.
2. **Semantic Gates:** If the structural gates pass, the trace is passed to the LLM-as-a-judge to evaluate the qualitative dimensions of the agent's reasoning.

---

## 🗺️ Roadmap (V1)
- [x] **v0.1:** Static Trace Evaluation (EDD Schema, Trajectory Validator, LLM-Judge)
- [ ] **v0.2:** Live Pipeline Hook (Dynamically spawn agents, capture traces, and evaluate in real-time)
- [ ] **v0.3:** Automated Green Teaming (Auto-refactor failing `SKILL.md` files)
- [ ] **v0.4:** Prefect Orchestration (Distributed CI/CD scheduling)

---
