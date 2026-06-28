import logging
from rich.logging import RichHandler

# Configure root logger
logging.basicConfig(
    level=logging.WARNING,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)]
)

# Create a custom logger for AgentCI
logger = logging.getLogger("agentci")
logger.setLevel(logging.WARNING)

def set_verbose_mode():
    """Sets the logger level to DEBUG for verbose output."""
    logger.setLevel(logging.DEBUG)
    # Also adjust root logger just in case
    logging.getLogger().setLevel(logging.DEBUG)
    logger.debug("Verbose mode enabled (log level set to DEBUG).")
