"""CLI entry points for aieng-bot-maintain.

This module has been refactored into a modular structure under the cli/ package.
This file maintains backward compatibility by re-exporting the CLI functions.
"""

from importlib.metadata import version  # Re-export for test compatibility

# Re-export all CLI entry points from the _cli module
from ._cli import (
    apply_agent_fix_cli,
    classify_pr_failure_cli,
    collect_metrics_cli,
    get_version,
    parse_pr_inputs,
    process_repo_queue_cli,
    read_failure_logs,
)

# Re-export for backward compatibility with tests
from .agent_fixer import AgentFixer, AgentFixRequest  # noqa: F401
from .classifier import PRFailureClassifier  # noqa: F401
from .classifier.models import CheckFailure, PRContext  # noqa: F401
from .metrics import MetricsCollector  # noqa: F401

# Maintain backward compatibility for private function names
_read_failure_logs = read_failure_logs
_parse_pr_inputs = parse_pr_inputs

__all__ = [
    # CLI entry points
    "classify_pr_failure_cli",
    "apply_agent_fix_cli",
    "collect_metrics_cli",
    "process_repo_queue_cli",
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
    classify_pr_failure_cli()
