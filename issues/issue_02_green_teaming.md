# Feature: Automated Green Teaming (Auto-Refactor SKILL.md)

## Problem
When a trajectory fails a security or cost constraint, developers must manually rewrite the Agent Skill instructions.

## Implementation
Implement the "Green Team" pattern from the 2026 Security Whitepapers. If `run_evaluation` fails deterministically, trigger a secondary LLM pipeline that ingests the failed trace and the source `SKILL.md`, and autonomously proposes a patched `SKILL.md` to fix the vulnerability.

## Acceptance Criteria
- `agentci auto-fix --trace <trace>` command added.
- Outputs a git patch or modified `SKILL.md` file.

## Labels
- `enhancement`
- `v1-milestone`
- `agentic-security`
