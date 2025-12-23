"""Public CLI exports for aieng-bot.

This module provides the main CLI entry point.
"""

from importlib.metadata import version  # Re-export for test compatibility

# Export main CLI
from ._cli.main import cli

# Re-export utilities for backward compatibility
from ._cli.utils import get_version, parse_pr_inputs, read_failure_logs

# Re-export for backward compatibility with tests
from .agent_fixer import AgentFixer, AgentFixRequest  # noqa: F401
from .classifier import PRFailureClassifier  # noqa: F401
from .classifier.models import CheckFailure, PRContext  # noqa: F401
from .metrics import MetricsCollector  # noqa: F401

# Maintain backward compatibility for private function names
_read_failure_logs = read_failure_logs
_parse_pr_inputs = parse_pr_inputs

__all__ = [
    # Main CLI
    "cli",
    # Public utilities
    "get_version",
    # Private utilities (for backward compatibility)
    "_read_failure_logs",
    "_parse_pr_inputs",
    # Re-exports for test compatibility
    "version",
    "AgentFixer",
    "AgentFixRequest",
    "PRFailureClassifier",
    "CheckFailure",
    "PRContext",
    "MetricsCollector",
]

if __name__ == "__main__":
    cli()
