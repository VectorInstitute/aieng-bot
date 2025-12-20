"""Activity logger for recording auto-merge and bot-fix activities to GCS."""

import json
import subprocess
from datetime import UTC, datetime
from typing import Literal

from ..utils.logging import log_error, log_info, log_success

ActivityType = Literal["auto_merge", "bot_fix"]
ActivityStatus = Literal["SUCCESS", "FAILED", "PARTIAL"]


class ActivityLogger:
    """Logger for bot activities (auto-merges and bot fixes).

    Records all bot activity to a unified log file in GCS for dashboard consumption.

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
            import tempfile

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
            import os

            os.unlink(temp_path)

            return True
        except subprocess.CalledProcessError as e:
            log_error(f"Failed to upload activity log to GCS: {e}")
            return False
        except Exception as e:
            log_error(f"Failed to save activity log: {e}")
            return False

    def log_auto_merge(
        self,
        repo: str,
        pr_number: int,
        pr_title: str,
        pr_author: str,
        pr_url: str,
        workflow_run_id: str,
        github_run_url: str,
        was_rebased: bool,
        rebase_time_seconds: float | None = None,
    ) -> bool:
        """Log a successful auto-merge activity.

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
        was_rebased : bool
            Whether PR was rebased before merge.
        rebase_time_seconds : float, optional
            Time spent on rebase in seconds (if rebased).

        Returns
        -------
        bool
            True on success, False on failure.

        """
        log_info(f"Recording auto-merge activity for {repo}#{pr_number}")

        # Load existing log
        log_data = self._load_activity_log()

        # Create activity entry
        activity = {
            "type": "auto_merge",
            "repo": repo,
            "pr_number": pr_number,
            "pr_title": pr_title,
            "pr_author": pr_author,
            "pr_url": pr_url,
            "timestamp": datetime.now(UTC).isoformat(),
            "workflow_run_id": workflow_run_id,
            "github_run_url": github_run_url,
            "was_rebased": was_rebased,
        }

        if rebase_time_seconds is not None:
            activity["rebase_time_seconds"] = rebase_time_seconds

        # Append activity
        log_data["activities"].append(activity)
        log_data["last_updated"] = datetime.now(UTC).isoformat()

        # Save to GCS
        if self._save_activity_log(log_data):
            log_success(
                f"✓ Auto-merge activity recorded for {repo}#{pr_number} "
                f"(rebased: {was_rebased})"
            )
            return True

        log_error(f"✗ Failed to record auto-merge activity for {repo}#{pr_number}")
        return False

    def log_bot_fix(
        self,
        repo: str,
        pr_number: int,
        pr_title: str,
        pr_author: str,
        pr_url: str,
        workflow_run_id: str,
        github_run_url: str,
        status: ActivityStatus,
        failure_type: str,
        trace_path: str,
        fix_time_hours: float,
    ) -> bool:
        """Log a bot fix activity.

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
            Fix status (SUCCESS, FAILED, PARTIAL).
        failure_type : str
            Type of failure (test, lint, security, build, merge_conflict, unknown).
        trace_path : str
            Path to trace file in GCS.
        fix_time_hours : float
            Time spent on fix in hours.

        Returns
        -------
        bool
            True on success, False on failure.

        """
        log_info(f"Recording bot fix activity for {repo}#{pr_number}")

        # Load existing log
        log_data = self._load_activity_log()

        # Create activity entry
        activity = {
            "type": "bot_fix",
            "repo": repo,
            "pr_number": pr_number,
            "pr_title": pr_title,
            "pr_author": pr_author,
            "pr_url": pr_url,
            "timestamp": datetime.now(UTC).isoformat(),
            "workflow_run_id": workflow_run_id,
            "github_run_url": github_run_url,
            "status": status,
            "failure_type": failure_type,
            "trace_path": trace_path,
            "fix_time_hours": fix_time_hours,
        }

        # Append activity
        log_data["activities"].append(activity)
        log_data["last_updated"] = datetime.now(UTC).isoformat()

        # Save to GCS
        if self._save_activity_log(log_data):
            log_success(
                f"✓ Bot fix activity recorded for {repo}#{pr_number} "
                f"(status: {status}, type: {failure_type})"
            )
            return True

        log_error(f"✗ Failed to record bot fix activity for {repo}#{pr_number}")
        return False
