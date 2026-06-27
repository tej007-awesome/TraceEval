# src/agentci/core/exceptions.py
"""Custom exception classes for AgentCI."""

class MissingAPIKeyError(RuntimeError):
    """Raised when OPENAI_API_KEY is not set in the environment."""
    pass
