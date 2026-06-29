# Feature: Prefect DAG Orchestration Integration

## Problem
The current `asyncio` loop works well for single CI/CD runs, but enterprise log auditing requires distributed scheduling, automatic retries, and batch processing for thousands of logs.

## Implementation
Introduce `prefect` as an optional dependency. Wrap the `run_evaluation` logic in Prefect `@task` and `@flow` decorators to allow robust batch execution and UI dashboarding.

## Acceptance Criteria
- `src/agentci/orchestration/prefect_flow.py` created.
- Can execute a batch directory of trace files concurrently with built-in retry logic for LLM rate limits.

## Labels
- `enhancement`
- `v1-milestone`
- `orchestration`
