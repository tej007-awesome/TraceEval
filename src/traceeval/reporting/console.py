# src/traceeval/reporting/console.py
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from traceeval.core.schema import EvaluationResult

console = Console()

def render_result(result: EvaluationResult):
    """Renders the evaluation result as a rich terminal table."""
    status_color = "green" if result.passed else "red"
    status_text = "PASSED (Safe to Deploy)" if result.passed else "FAILED (Deployment Blocked)"
    
    console.print(f"\n[bold {status_color}]Result: {status_text}[/bold {status_color}]")
    console.print(f"Case ID: [bold]{result.case_id}[/bold]\n")

    # Dimensions Table
    table = Table(title="Evaluation Dimensions", show_header=True, header_style="bold magenta")
    table.add_column("Dimension", style="cyan")
    table.add_column("Score", justify="right")
    
    scores = result.scores
    table.add_row("Intent Satisfaction", f"{scores.intent_satisfaction}")
    table.add_row("Functional Correctness", f"{scores.functional_correctness}")
    table.add_row("Trajectory Quality", f"{scores.trajectory_quality}")
    table.add_row("Cost Efficiency", f"{scores.cost_efficiency}")
    table.add_row("Safety & RAI", f"{scores.safety_and_rai}")
    
    console.print(table)
    
    # Reasoning Panel
    console.print(Panel(
        scores.reasoning, 
        title="LLM Judge Reasoning", 
        border_style=status_color
    ))