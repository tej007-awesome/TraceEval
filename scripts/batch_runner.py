import asyncio
import logging
from pathlib import Path
from rich.console import Console
from rich.table import Table
from pydantic import BaseModel
from typing import Optional

from traceeval.core.schema import EDDTestCase, AgentTrace
from traceeval.metrics.trajectory_judge import run_evaluation

# Mute the middleware logger so our batch table prints cleanly
logging.getLogger().setLevel(logging.ERROR)
console = Console()

# Define the Golden Record wrapper schema
class GoldenRecord(BaseModel):
    meta_id: str
    scenario_type: str
    expected_passed: bool
    expected_failure_reason: Optional[str] = None
    case: EDDTestCase
    trace: AgentTrace

async def evaluate_with_semaphore(record: GoldenRecord, sem: asyncio.Semaphore):
    """Wraps the evaluation engine with a concurrency limiter."""
    async with sem:
        # Enforce our strict enterprise thresholds
        result = await run_evaluation(
            record.case, 
            record.trace, 
            max_cost=0.10, 
            score_threshold=0.8
        )
        return record, result

async def main():
    test_suite_dir = Path("test_suite")
    files = list(test_suite_dir.glob("*.json"))
    
    if not files:
        console.print("[red]No golden records found in test_suite/[/red]")
        return

    # Load dataset
    records = []
    for f in files:
        with open(f, "r", encoding="utf-8") as file:
            records.append(GoldenRecord.model_validate_json(file.read()))

    console.print(f"\n[bold blue]Loaded {len(records)} golden records.[/bold blue]")
    
    with console.status("[bold yellow]Firing concurrent evaluations at LLM Provider...", spinner="dots"):
        # Set concurrency limit to 10 simultaneous requests
        sem = asyncio.Semaphore(10) 
        tasks = [evaluate_with_semaphore(r, sem) for r in records]
        
        # Execute all cases concurrently
        results = await asyncio.gather(*tasks)

    # --- Phase 3: Meta-Evaluation Analytics ---
    correctly_passed = 0
    correctly_blocked = 0
    falsely_blocked = 0
    falsely_passed = 0

    table = Table(title="TraceEval Meta-Evaluation Results", show_lines=True)
    table.add_column("Scenario ID", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Expected", justify="center")
    table.add_column("Actual", justify="center")
    table.add_column("Verdict", justify="center")

    for record, result in results:
        expected = record.expected_passed
        actual = result.passed
        
        if expected and actual:
            verdict = "[green]Correctly Passed[/green]"
            correctly_passed += 1
        elif not expected and not actual:
            verdict = "[green]Correctly Blocked[/green]"
            correctly_blocked += 1
        elif expected and not actual:
            verdict = "[yellow]Falsely Blocked (Friction)[/yellow]"
            falsely_blocked += 1
        else:
            verdict = "[bold red]Falsely Passed (DANGER)[/bold red]"
            falsely_passed += 1

        table.add_row(
            record.meta_id, 
            record.scenario_type, 
            "[green]PASS[/]" if expected else "[red]FAIL[/]", 
            "[green]PASS[/]" if actual else "[red]FAIL[/]", 
            verdict
        )

    console.print(table)
    
    # Calculate Overall Accuracy
    accuracy = (correctly_passed + correctly_blocked) / len(records) * 100
    
    console.print(f"\n[bold]Overall Engine Accuracy:[/bold] [bold cyan]{accuracy:.1f}%[/bold cyan]")
    console.print(f"✅ Correctly Passed (Happy Paths): {correctly_passed}")
    console.print(f"🛡️  Correctly Blocked (Threats caught): {correctly_blocked}")
    console.print(f"⚠️  Falsely Blocked (Developer Friction): {falsely_blocked}")
    console.print(f"🚨 Falsely Passed (Vulnerabilities leaked): {falsely_passed}\n")

if __name__ == "__main__":
    asyncio.run(main())