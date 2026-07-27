"""Public CLI exports for aieng-bot.

This module provides the main CLI entry point.
"""

# Export main CLI
from ._cli.main import cli
from ._cli.utils import get_version

__all__ = [
    "cli",
    "get_version",
]

if __name__ == "__main__":
    cli()
