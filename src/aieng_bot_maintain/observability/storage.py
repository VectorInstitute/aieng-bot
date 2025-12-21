"""Trace storage utilities for agent execution traces.

This module provides utilities for saving traces to JSON files
and uploading them to Google Cloud Storage.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any


class TraceStorage:
    """Handle trace storage operations (local and cloud)."""

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
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, "w") as f:
            json.dump(trace, f, indent=2)

        print(f"✓ Trace saved to {filepath}")

    @staticmethod
    def upload_to_gcs(
        trace_filepath: str, bucket_name: str, destination_blob_name: str
    ) -> bool:
        """Upload trace JSON to Google Cloud Storage.

        Parameters
        ----------
        trace_filepath : str
            Local path to trace JSON file.
        bucket_name : str
            GCS bucket name (without gs:// prefix).
        destination_blob_name : str
            Target path in GCS bucket.

        Returns
        -------
        bool
            True if upload succeeded, False otherwise.

        Notes
        -----
        Uses gcloud CLI (must be authenticated in workflow).
        Prints status messages to stdout.

        """
        try:
            # Use gcloud CLI for simplicity (already authenticated in workflow)
            cmd = [
                "gcloud",
                "storage",
                "cp",
                trace_filepath,
                f"gs://{bucket_name}/{destination_blob_name}",
            ]

            subprocess.run(cmd, capture_output=True, text=True, check=True)

            print(f"✓ Trace uploaded to gs://{bucket_name}/{destination_blob_name}")
            return True

        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to upload trace to GCS: {e.stderr}")
            return False
        except Exception as e:
            print(f"✗ Unexpected error uploading to GCS: {e}")
            return False
