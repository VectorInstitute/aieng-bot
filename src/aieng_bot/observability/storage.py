"""Local trace storage utilities for agent execution traces.

Detailed per-run traces are viewed in Langfuse; this module only persists
the local trace JSON used to derive the PR-comment summary and file-change
metrics for a run.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ..utils.logging import log_success


class TraceStorage:
    """Handle local trace file storage."""

    @staticmethod
    def save_to_file(trace: dict[str, Any], filepath: str) -> None:
        """Save trace to JSON file.

        Parameters
        ----------
        trace : dict[str, Any]
            Trace data to save.
        filepath : str
            Path to save trace JSON.

        Notes
        -----
        Creates parent directories if they don't exist.

        """
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

        with open(filepath, "w") as f:
            json.dump(trace, f, indent=2)

        log_success(f"Trace saved to {filepath}")
