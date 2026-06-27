import sys
import asyncio
import typer
from pathlib import Path
from agentci.loaders.file import load_test_case, load_trace
from agentci.metrics.trajectory_judge import run_evaluation
from agentci.reporting.console import render_result, console


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
def main():
    """
    AgentCI: The CI/CD gate for Agentic Engineering.
    """
    pass

@app.command()
def run(
    case_file: Path = typer.Option(..., "--case", "-c", help="Path to EDDTestCase JSON"),
    trace_file: Path = typer.Option(..., "--trace", "-t", help="Path to AgentTrace JSON"),
):
    """Run an AgentCI evaluation against a captured agent trace."""
    console.print("[bold blue]AgentCI[/bold blue] initializing...")
    
    try:
        case = load_test_case(case_file)
        trace = load_trace(trace_file)
    except Exception as e:
        console.print(f"[bold red]Data Load Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    with console.status("[bold yellow]Evaluating Vibe Trajectory & Dimensions via Gemini...", spinner="dots"):
        try:
            result = asyncio.run(run_evaluation(case, trace))
        except Exception as e:
            console.print(f"\n[bold red]Evaluation Engine Error:[/bold red] {e}")
            raise typer.Exit(code=1)

    render_result(result)
    
    if not result.passed:
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()