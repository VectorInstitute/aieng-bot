"""Activity logger for recording fix activities to GCS."""

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Literal

from aieng_bot.utils.logging import log_error, log_info, log_success

ActivityStatus = Literal["SUCCESS", "FAILED"]


class ActivityLogger:
    """Logger for bot fix and merge activities.

    Records all bot activity to a unified log file in GCS for dashboard consumption.
    Every invocation of the fix command logs an activity here.

    Parameters
    ----------
    bucket : str, optional
        GCS bucket name (default="bot-dashboard-vectorinstitute").
    log_path : str, optional
        Path to activity log in GCS (default="data/bot_activity_log.json").

    Attributes
    ----------
    bucket : str
        GCS bucket name.
    log_path : str
        Path to activity log in GCS.

    """

    def __init__(
        self,
        bucket: str = "bot-dashboard-vectorinstitute",
        log_path: str = "data/bot_activity_log.json",
    ):
        """Initialize activity logger.

        Parameters
        ----------
        bucket : str, optional
            GCS bucket name (default="bot-dashboard-vectorinstitute").
        log_path : str, optional
            Path to activity log in GCS (default="data/bot_activity_log.json").

        """
        self.bucket = bucket
        self.log_path = log_path
        self.gcs_uri = f"gs://{bucket}/{log_path}"

    def _load_activity_log(self) -> dict:
        """Load existing activity log from GCS.

        Returns
        -------
        dict
            Activity log with 'activities' list and 'last_updated' timestamp.
            Returns empty structure if file doesn't exist.

        """
        try:
            result = subprocess.run(
                ["gcloud", "storage", "cat", self.gcs_uri],
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError:
            # File doesn't exist yet
            return {"activities": [], "last_updated": None}
        except json.JSONDecodeError as e:
            log_error(f"Failed to parse activity log: {e}")
            return {"activities": [], "last_updated": None}

    def _save_activity_log(self, log_data: dict) -> bool:
        """Save activity log to GCS.

        Parameters
        ----------
        log_data : dict
            Activity log data to save.

        Returns
        -------
        bool
            True on success, False on failure.

        """
        try:
            # Write to temp file
            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".json"
            ) as f:
                json.dump(log_data, f, indent=2)
                temp_path = f.name

            # Upload to GCS
            subprocess.run(
                ["gcloud", "storage", "cp", temp_path, self.gcs_uri],
                check=True,
                capture_output=True,
            )

            # Clean up temp file
            os.unlink(temp_path)

            return True
        except subprocess.CalledProcessError as e:
            log_error(f"Failed to upload activity log to GCS: {e}")
            return False
        except Exception as e:
            log_error(f"Failed to save activity log: {e}")
            return False

    def log_fix(
        self,
        repo: str,
        pr_number: int,
        pr_title: str,
        pr_author: str,
        pr_url: str,
        workflow_run_id: str,
        github_run_url: str,
        status: ActivityStatus,
        failure_types: list[str],
        trace_path: str,
        fix_time_hours: float,
    ) -> bool:
        """Log a fix and merge activity.

        This is called every time the fix command processes a PR, whether it
        needed fixing or just rebasing and merging.

        Parameters
        ----------
        repo : str
            Repository name (owner/repo format).
        pr_number : int
            PR number.
        pr_title : str
            PR title.
        pr_author : str
            PR author.
        pr_url : str
            PR URL.
        workflow_run_id : str
            GitHub workflow run ID.
        github_run_url : str
            GitHub workflow run URL.
        status : ActivityStatus
            Fix status (SUCCESS, FAILED).
        failure_types : list[str]
            Types of failure/action (lint, test, build, security,
            merge_conflict, merge_only, unknown). Multiple types can be present.
        trace_path : str
            Path to trace file in GCS.
        fix_time_hours : float
            Time spent on fix in hours.

        Returns
        -------
        bool
            True on success, False on failure.

        """
        log_info(f"Recording fix activity for {repo}#{pr_number}")

        # Load existing log
        log_data = self._load_activity_log()

        # Create activity entry with both failure_types (new) and failure_type (backward compat)
        activity = {
            "repo": repo,
            "pr_number": pr_number,
            "pr_title": pr_title,
            "pr_author": pr_author,
            "pr_url": pr_url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "workflow_run_id": workflow_run_id,
            "github_run_url": github_run_url,
            "status": status,
            "failure_types": failure_types,
            "failure_type": failure_types[0] if failure_types else "unknown",
            "trace_path": trace_path,
            "fix_time_hours": fix_time_hours,
        }

        # Append activity
        log_data["activities"].append(activity)
        log_data["last_updated"] = datetime.now(timezone.utc).isoformat()

        # Save to GCS
        failure_types_str = ",".join(failure_types)
        if self._save_activity_log(log_data):
            log_success(
                f"Fix activity recorded for {repo}#{pr_number} "
                f"(status: {status}, types: {failure_types_str})"
            )
            return True

        log_error(f"Failed to record fix activity for {repo}#{pr_number}")
        return False
