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

    Each fix is written to a unique per-run sidecar file in GCS so that
    concurrent workflow jobs never overwrite each other's entries. After writing
    the sidecar, the combined ``bot_activity_log.json`` is rebuilt from all
    sidecars plus any historical entries in the existing log.

    Parameters
    ----------
    bucket : str, optional
        GCS bucket name (default="bot-dashboard-vectorinstitute").
    log_path : str, optional
        Path to combined activity log in GCS (default="data/bot_activity_log.json").
    entries_prefix : str, optional
        GCS key prefix for individual activity entry files
        (default="data/activity_entries/").

    Attributes
    ----------
    bucket : str
        GCS bucket name.
    log_path : str
        Path to combined activity log in GCS.
    gcs_uri : str
        Full GCS URI for combined activity log.
    entries_prefix : str
        GCS key prefix for individual activity entry files.
    entries_gcs_prefix : str
        Full GCS URI prefix for individual activity entry files.

    """

    def __init__(
        self,
        bucket: str = "bot-dashboard-vectorinstitute",
        log_path: str = "data/bot_activity_log.json",
        entries_prefix: str = "data/activity_entries/",
    ):
        """Initialize activity logger.

        Parameters
        ----------
        bucket : str, optional
            GCS bucket name (default="bot-dashboard-vectorinstitute").
        log_path : str, optional
            Path to combined activity log in GCS
            (default="data/bot_activity_log.json").
        entries_prefix : str, optional
            GCS key prefix for individual activity entry files
            (default="data/activity_entries/").

        """
        self.bucket = bucket
        self.log_path = log_path
        self.gcs_uri = f"gs://{bucket}/{log_path}"
        self.entries_prefix = entries_prefix
        self.entries_gcs_prefix = f"gs://{bucket}/{entries_prefix}"

    def _gcs_upload(self, local_path: str, gcs_uri: str) -> bool:
        """Upload a local file to GCS.

        Parameters
        ----------
        local_path : str
            Local file path to upload.
        gcs_uri : str
            Destination GCS URI.

        Returns
        -------
        bool
            True on success, False on failure.

        """
        try:
            subprocess.run(
                ["gcloud", "storage", "cp", local_path, gcs_uri],
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            log_error(f"Failed to upload to {gcs_uri}: {e.stderr or e.stdout}")
            return False

    def _gcs_read_json(self, gcs_uri: str) -> dict | None:  # noqa: PYI041
        """Read and parse a JSON file from GCS.

        Parameters
        ----------
        gcs_uri : str
            GCS URI to read.

        Returns
        -------
        dict | None
            Parsed JSON dict, empty structure if file does not exist (404),
            or None on any other error (caller must not overwrite).

        """
        try:
            result = subprocess.run(
                ["gcloud", "storage", "cat", gcs_uri],
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            stderr = e.stderr or ""
            stdout = e.stdout or ""
            not_found_signals = ("No URLs matched", "NotFound", "does not exist", "404")
            if any(s in stderr or s in stdout for s in not_found_signals):
                return {"activities": [], "last_updated": None}
            log_error(f"Failed to read {gcs_uri}: {stderr or stdout}")
            return None
        except json.JSONDecodeError as e:
            log_error(f"Failed to parse JSON from {gcs_uri}: {e}")
            return None

    def _write_entry_sidecar(self, activity: dict, workflow_run_id: str) -> bool:
        """Write a single activity entry to its own unique GCS file.

        Using ``workflow_run_id`` as the filename guarantees concurrent jobs
        never write to the same path, so no read-modify-write is needed here.

        Parameters
        ----------
        activity : dict
            Activity entry data.
        workflow_run_id : str
            Unique workflow run identifier, used as the sidecar filename.

        Returns
        -------
        bool
            True on success, False on failure.

        """
        gcs_uri = f"{self.entries_gcs_prefix}{workflow_run_id}.json"
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".json"
            ) as f:
                json.dump(activity, f, indent=2)
                temp_path = f.name
            success = self._gcs_upload(temp_path, gcs_uri)
            os.unlink(temp_path)
            return success
        except Exception as e:
            log_error(f"Failed to write activity sidecar: {e}")
            return False

    def _list_entry_sidecars(self) -> list[str]:
        """List all activity entry sidecar files in GCS.

        Returns
        -------
        list[str]
            List of GCS URIs for all sidecar entry files.

        """
        try:
            result = subprocess.run(
                ["gcloud", "storage", "ls", self.entries_gcs_prefix],
                capture_output=True,
                text=True,
                check=True,
            )
            return [
                line.strip()
                for line in result.stdout.splitlines()
                if line.strip().endswith(".json")
            ]
        except subprocess.CalledProcessError:
            return []

    def _rebuild_combined_log(self) -> bool:
        """Rebuild ``bot_activity_log.json`` from all sidecar entries.

        Reads every sidecar under ``entries_prefix`` and merges them with any
        existing entries in the combined log (preserving historical records that
        predate the sidecar approach). Deduplicates by
        ``(repo, pr_number, workflow_run_id)`` and sorts by timestamp.

        Because this method only writes a freshly computed view of all known
        entries, concurrent calls are safe: the last writer will include all
        sidecars that existed at the time of its read, and any entries written
        concurrently will be picked up on the next rebuild.

        Returns
        -------
        bool
            True on success, False on failure.

        """
        # Collect entries from all sidecars
        sidecar_activities: list[dict] = []
        for uri in self._list_entry_sidecars():
            data = self._gcs_read_json(uri)
            if data and isinstance(data, dict) and "repo" in data:
                sidecar_activities.append(data)

        # Collect entries from existing combined log (historical, pre-sidecar)
        existing = self._gcs_read_json(self.gcs_uri)
        existing_activities: list[dict] = []
        if existing and isinstance(existing.get("activities"), list):
            existing_activities = existing["activities"]

        # Merge and deduplicate — sidecars are authoritative for overlapping keys
        seen: set[tuple] = set()
        merged: list[dict] = []
        for activity in sidecar_activities + existing_activities:
            key = (
                activity.get("repo", ""),
                activity.get("pr_number", 0),
                activity.get("workflow_run_id", ""),
            )
            if key not in seen:
                seen.add(key)
                merged.append(activity)

        merged.sort(key=lambda a: a.get("timestamp") or "")

        log_data = {
            "activities": merged,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".json"
            ) as f:
                json.dump(log_data, f, indent=2)
                temp_path = f.name
            success = self._gcs_upload(temp_path, self.gcs_uri)
            os.unlink(temp_path)
            return success
        except Exception as e:
            log_error(f"Failed to rebuild combined activity log: {e}")
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
        cost_usd: float | None,
        fix_time_hours: float,
    ) -> bool:
        """Log a fix and merge activity.

        Writes the activity to a unique sidecar file first (safe against
        concurrent jobs), then rebuilds the combined log from all sidecars.
        If the rebuild fails the activity is still durably recorded in the
        sidecar and will be included on the next successful rebuild.

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
        cost_usd : float or None
            Total Anthropic API cost for the fix run in USD, if known.
        fix_time_hours : float
            Time spent on fix in hours.

        Returns
        -------
        bool
            True if the activity sidecar was written successfully (combined log
            rebuild failure does not cause a False return).
            False only if the sidecar write itself failed.

        """
        log_info(f"Recording fix activity for {repo}#{pr_number}")

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
            "cost_usd": cost_usd,
            "fix_time_hours": fix_time_hours,
        }

        failure_types_str = ",".join(failure_types)

        # Step 1: Write sidecar — unique filename guarantees no concurrent clobber
        if not self._write_entry_sidecar(activity, workflow_run_id):
            log_error(f"Failed to write activity sidecar for {repo}#{pr_number}")
            return False

        log_success(
            f"Fix activity sidecar written for {repo}#{pr_number} "
            f"(status: {status}, types: {failure_types_str})"
        )

        # Step 2: Rebuild combined log — best-effort; data is safe in the sidecar
        if not self._rebuild_combined_log():
            log_error(
                f"Failed to rebuild combined activity log after {repo}#{pr_number} "
                "(activity is safe in sidecar and will appear on next rebuild)"
            )

        return True
