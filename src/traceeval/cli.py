import os
import sys
import asyncio
import typer
from pathlib import Path
from typing import Optional
from traceeval.loaders.file import load_test_case, load_trace
from traceeval.loaders.live import run_live_pipeline
from traceeval.metrics.trajectory_judge import run_evaluation
from traceeval.reporting.console import render_result, console
from traceeval.reporting.export import export_to_json

from rich.console import Console
_startup_console = Console()
try:
    from traceeval.core.config import settings  # noqa: F401
except Exception as e:
    _startup_console.print("\n[bold red] Configuration Error:[/bold red]")
    _startup_console.print("Missing or invalid environment variables. Please check your [bold].env[/bold] file.")
    _startup_console.print(f"[dim]Details: {e}[/dim]\n")
    sys.exit(1)


app = typer.Typer(
    name="traceeval",
    help="TraceEval: CI/CD and Evaluation Infrastructure for Autonomous Agents",
    add_completion=False,
)

@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging")
):
    """
    TraceEval: The CI/CD gate for Agentic Engineering.
    """
    if verbose:
        from traceeval.core.logger import set_verbose_mode
        set_verbose_mode()

@app.command()
def run(
    case_file: Path = typer.Option(..., "--case", "-c", help="Path to EDDTestCase JSON"),
    trace_file: Optional[Path] = typer.Option(None, "--trace", "-t", help="Path to static AgentTrace JSON"),
    otel_trace: Optional[Path] = typer.Option(None, "--otel-trace", help="Path to OpenTelemetry trace JSON"),
    pipeline: Optional[str] = typer.Option(None, "--pipeline", "-p", help="Live agent function (e.g. 'examples.reference_agent:process_refund')"),
    pricing: Optional[Path] = typer.Option(None, "--pricing", help="Path to custom JSON pricing file"),
    export_path: Optional[str] = typer.Option(None, "--export", "-e", help="Path to save the JSON EvaluationResult"),
    max_cost: float = typer.Option(0.10, "--max-cost", help="Maximum allowable session budget in USD"),
    score_threshold: float = typer.Option(0.8, "--score-threshold", help="Minimum score (0-1) that every non-null judge dimension must meet"),
):
    """Run a TraceEval evaluation against a static trace, an OTel trace, or a live agent pipeline."""
    has_api_key = bool(settings.llm_api_key or os.environ.get("OPENAI_API_KEY"))
    has_base_url = bool(settings.llm_base_url)
    if not (has_api_key or has_base_url):
        console.print("\n[bold red]Configuration Error:[/bold red]")
        console.print("Either LLM_API_KEY (or OPENAI_API_KEY) or LLM_BASE_URL must be configured.")
        raise typer.Exit(code=1)

    provided = [x for x in [trace_file, otel_trace, pipeline] if x is not None]
    if len(provided) != 1:
        console.print(
            "[bold red]Error:[/bold red] Exactly one of --trace, --otel-trace, or --pipeline must be provided."
        )
        raise typer.Exit(code=1)

    try:
        case = load_test_case(case_file)

        # Determine Execution Mode (Static vs OTel vs Live)
        if pipeline:
            console.print(f"[dim]Mode: Live Pipeline execution ({pipeline})[/dim]")
            trace = run_live_pipeline(pipeline, case)
        elif trace_file:
            console.print(f"[dim]Mode: Static Batch execution ({trace_file})[/dim]")
            trace = load_trace(trace_file)
        elif otel_trace:
            console.print(f"[dim]Mode: OTel trace ({otel_trace})[/dim]")
            from traceeval.loaders.otel import load_otel_trace
            from traceeval.pricing import DEFAULT_PRICING, load_pricing

            pricing_table = load_pricing(pricing) if pricing else DEFAULT_PRICING
            otel_result = load_otel_trace(otel_trace, pricing=pricing_table)
            for warning in otel_result.warnings:
                console.print(f"[yellow]Warning:[/yellow] {warning}")
            trace = otel_result.trace
        else:
            raise ValueError("No valid trace or pipeline provided.")

    except Exception as e:
        console.print(f"[bold red]Ingestion Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    with console.status(f"[bold yellow]Evaluating Vibe Trajectory & Dimensions via {settings.llm_model_name}...", spinner="dots"):
        try:
            result = asyncio.run(run_evaluation(case, trace, max_cost=max_cost, score_threshold=score_threshold))
        except Exception as e:
            console.print(f"\n[bold red]Evaluation Engine Error:[/bold red] {e}")
            raise typer.Exit(code=1)

    # Render Terminal Output
    render_result(result)

    # Handle Export
    if export_path:
        export_to_json(result, export_path)
        console.print(f"\n[dim]Report successfully exported to {export_path}[/dim]")

    if not result.passed:
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()