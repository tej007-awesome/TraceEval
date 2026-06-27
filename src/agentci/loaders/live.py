# src/agentci/loaders/live.py
"""Dynamic loader for live pipeline functions.

This module uses ``importlib`` to load a user‑specified module and retrieve a callable
named ``pipeline``. The callable is expected to accept a ``str`` query and return a
string answer. This enables the CLI to evaluate arbitrary pipelines without hard‑coding
them into the repository.
"""

import importlib
from types import ModuleType
from typing import Callable

def load_pipeline(module_path: str) -> Callable[[str], str]:
    """Load a ``pipeline`` function from the given module path.

    Args:
        module_path: Dotted import path to the module, e.g. ``my_pkg.pipeline``.

    Returns:
        Callable that takes a query string and returns a result string.

    Raises:
        ImportError: If the module cannot be imported.
        AttributeError: If the module does not define a ``pipeline`` callable.
    """
    module: ModuleType = importlib.import_module(module_path)
    pipeline = getattr(module, "pipeline", None)
    if not callable(pipeline):
        raise AttributeError(f"Module '{module_path}' does not define a callable 'pipeline'.")
    return pipeline
