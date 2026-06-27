# src/agentci/reporting/export.py
"""Export reporting utilities.

Provides functions to serialize evaluation results to JSON files.
"""

import json
from pathlib import Path
from typing import List

from ..core.schema import EvalResult

def export_results(results: List[EvalResult], output_path: str) -> None:
    """Export evaluation results to a JSON file.

    Args:
        results: List of ``EvalResult`` objects.
        output_path: Destination file path (will be created if missing).
    """
    serializable = []
    for r in results:
        item = {
            "question": r.record.question,
            "answer": r.record.answer,
            "metadata": r.record.metadata,
            "score": r.score,
            "details": r.details,
        }
        serializable.append(item)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)
