from pathlib import Path
from agentci.core.schema import EDDTestCase, AgentTrace

def load_test_case(file_path: Path) -> EDDTestCase:
    """Loads an EDD test case from a JSON file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Test case file not found: {file_path}")
    return EDDTestCase.model_validate_json(file_path.read_text())

def load_trace(file_path: Path) -> AgentTrace:
    """Loads an execution trace from a JSON file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Trace file not found: {file_path}")
    return AgentTrace.model_validate_json(file_path.read_text())