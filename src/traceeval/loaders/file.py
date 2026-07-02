from pathlib import Path
from traceeval.core.schema import EDDTestCase, AgentTrace
from traceeval.core.logger import logger

def load_test_case(file_path: Path) -> EDDTestCase:
    """Loads an EDD test case from a JSON file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Test case file not found: {file_path}")
    logger.info(f"Loading test case from {file_path}...")
    case = EDDTestCase.model_validate_json(file_path.read_text())
    logger.debug(f"Successfully loaded test case ID: {case.case_id}")
    return case

def load_trace(file_path: Path) -> AgentTrace:
    """Loads an execution trace from a JSON file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Trace file not found: {file_path}")
    logger.info(f"Loading execution trace from {file_path}...")
    trace = AgentTrace.model_validate_json(file_path.read_text())
    logger.debug(f"Successfully loaded execution trace session ID: {trace.session_id}")
    return trace