from pathlib import Path
from traceeval.core.schema import EvaluationResult

def export_to_json(result: EvaluationResult, export_path: str) -> None:
    """Exports the EvaluationResult to a JSON file."""
    path = Path(export_path)
    
    # Ensure the parent directories exist
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write the Pydantic model to JSON
    with open(path, "w", encoding="utf-8") as f:
        f.write(result.model_dump_json(indent=2))