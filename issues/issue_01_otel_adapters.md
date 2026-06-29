# Feature: Universal OpenTelemetry Adapters (Vendor Agnosticism)

## Problem
AgentCI currently relies on custom `AgentTrace` JSON structures. To support the broader enterprise ecosystem, we must natively ingest standard OTel traces.

## Implementation
Create a `src/agentci/loaders/adapters/` module. Implement parsers that convert standard Generative AI OTel semantic conventions (from LangGraph, OpenAI Swarm, Claude SDK, and raw MCP servers) into our Pydantic `AgentTrace` contract.

## Acceptance Criteria
- `OpenTelemetryAdapter` class implemented.
- Can ingest a raw `.json` OTel trace and map `genai.tool.name` and `genai.system.prompt` accurately.

## Labels
- `enhancement`
- `v1-milestone`
- `core-architecture`
