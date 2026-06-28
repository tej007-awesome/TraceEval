import sys
import asyncio
import typer
from pathlib import Path
from typing import Optional
from agentci.loaders.file import load_test_case, load_trace
from agentci.loaders.live import run_live_pipeline
from agentci.metrics.trajectory_judge import run_evaluation
from agentci.reporting.console import render_result, console
from agentci.reporting.export import export_to_json

from rich.console import Console
_startup_console = Console()
try:
    from agentci.core.config import settings  # noqa: F401
except Exception as e:
    _startup_console.print("\n[bold red]⚠️ Configuration Error:[/bold red]")
    _startup_console.print("Missing or invalid environment variables. Please check your [bold].env[/bold] file.")
    _startup_console.print(f"[dim]Details: {e}[/dim]\n")
    sys.exit(1)


app = typer.Typer(
    name="agentci",
    help="AgentCI: CI/CD and Evaluation Infrastructure for Autonomous Agents",
    add_completion=False,
)

@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging")
):
    """
    AgentCI: The CI/CD gate for Agentic Engineering.
    """
    if verbose:
        from agentci.core.logger import set_verbose_mode
        set_verbose_mode()

@app.command()
def run(
    case_file: Path = typer.Option(..., "--case", "-c", help="Path to EDDTestCase JSON"),
    trace_file: Optional[Path] = typer.Option(None, "--trace", "-t", help="Path to static AgentTrace JSON"),
    pipeline: Optional[str] = typer.Option(None, "--pipeline", "-p", help="Live agent function (e.g. 'examples.reference_agent:process_refund')"),
    export_path: Optional[str] = typer.Option(None, "--export", "-e", help="Path to save the JSON EvaluationResult"),
):
    """Run an AgentCI evaluation against a static trace or a live agent pipeline."""
    import os
    if "OPENAI_API_KEY" not in os.environ and settings.llm_base_url is None:
        console.print("\n[bold red]Configuration Error:[/bold red]")
        console.print("Either LLM_API_KEY (or OPENAI_API_KEY) or LLM_BASE_URL must be configured.")
        raise typer.Exit(code=1)

    if not trace_file and not pipeline:
        console.print("[bold red]Error:[/bold red] You must provide either a static --trace file or a live --pipeline hook.")
        raise typer.Exit(code=1)
    
    try:
        case = load_test_case(case_file)
        
        # Determine Execution Mode (Static vs Live)
        if pipeline:
            console.print(f"[dim]Mode: Live Pipeline execution ({pipeline})[/dim]")
            trace = run_live_pipeline(pipeline, case)
        elif trace_file:
            console.print(f"[dim]Mode: Static Batch execution ({trace_file})[/dim]")
            trace = load_trace(trace_file)
        else:
            raise ValueError("No trace file or pipeline provided.")
            
    except Exception as e:
        console.print(f"[bold red]Ingestion Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    with console.status(f"[bold yellow]Evaluating Vibe Trajectory & Dimensions via {settings.llm_model_name}...", spinner="dots"):
        try:
            result = asyncio.run(run_evaluation(case, trace))
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