# AgentCI

AgentCI is a lightweight continuous integration framework designed for evaluating LLM agents. It provides utilities for loading evaluation data, running LLM pipelines, calculating metrics (including RAGAS), and reporting results via the console or JSON export.

## Quickstart

```bash
# Clone the repository
git clone <repo-url>
cd agentci

# Install dependencies
pip install -e .

# Run the demo CLI (requires an OpenAI API key)
export OPENAI_API_KEY=your-key-here
agentci run-demo
```

The CLI loads the sample QA data in `sample_data/batch_01.json`, runs a placeholder pipeline, and prints a summary table of results.

## Architecture

```
src/agentci/
├── core/          # Configuration and Pydantic models
├── loaders/       # Data loading utilities (JSON/CSV) and dynamic pipeline imports
├── metrics/       # RAGAS and trajectory metric wrappers
├── reporting/     # Console display (Rich) and JSON export
└── cli.py         # Typer entry‑point
```

## Development

- Run tests: `pytest`
- Lint with `ruff`
- CI is defined in `.github/workflows/ci.yml` and runs on every push/PR.

## License

Apache-2.0
