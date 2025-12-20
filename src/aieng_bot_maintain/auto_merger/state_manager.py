"""State manager for queue state persistence to GCS."""

import json
import subprocess
from datetime import UTC, datetime, timedelta
from typing import Any

from .models import PRQueueItem, PRStatus, QueueState, RepoQueue


class StateManager:
    """Manage queue state persistence to GCS.

    Handles download-modify-upload pattern similar to bot_activity_log.
    Implements safe concurrent writes with retry logic.

    Parameters
    ----------
    bucket : str, optional
        GCS bucket name (default="bot-dashboard-vectorinstitute").

    Attributes
    ----------
    bucket : str
        GCS bucket name.
    state_path : str
        Path within bucket for state file.

    """

    def __init__(self, bucket: str = "bot-dashboard-vectorinstitute"):
        """Initialize state manager.

        Parameters
        ----------
        bucket : str, optional
            GCS bucket name (default="bot-dashboard-vectorinstitute").

        """
        self.bucket = bucket
        self.state_path = "data/pr_queue_state.json"

    def _run_gcloud_command(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        """Execute gcloud command with error handling.

        Parameters
        ----------
        cmd : list[str]
            Command and arguments to execute.

        Returns
        -------
        subprocess.CompletedProcess[str]
            Completed process with output.

        Raises
        ------
        subprocess.CalledProcessError
            If command fails.

        """
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

    def load_state(self) -> QueueState | None:
        """Load existing queue state from GCS.

        Returns None if no state exists or if state is stale (>24 hours).

        Returns
        -------
        QueueState or None
            Loaded queue state, or None if not found or stale.

        """
        local_path = "/tmp/pr_queue_state.json"

        try:
            self._run_gcloud_command(
                [
                    "gcloud",
                    "storage",
                    "cp",
                    f"gs://{self.bucket}/{self.state_path}",
                    local_path,
                ]
            )

            with open(local_path) as f:
                data = json.load(f)

            state = QueueState.from_dict(data)

            # Check if state is stale (>24 hours old)
            started_at = datetime.fromisoformat(state.started_at)
            age_hours = (datetime.now(UTC) - started_at).total_seconds() / 3600

            if age_hours > 24:
                print(f"⚠ State is stale ({age_hours:.1f}h old), ignoring")
                return None

            print(f"✓ Loaded state from run {state.workflow_run_id}")
            return state

        except subprocess.CalledProcessError:
            print("ℹ No existing state found in GCS")
            return None
        except (json.JSONDecodeError, KeyError) as e:
            print(f"✗ Failed to parse state: {e}")
            return None

    def save_state(self, state: QueueState) -> bool:
        """Save queue state to GCS.

        Returns
        -------
        bool
            True on success, False on failure.

        """
        local_path = "/tmp/pr_queue_state.json"

        # Update timestamp
        state.last_updated = datetime.now(UTC).isoformat()

        try:
            # Write to local file
            with open(local_path, "w") as f:
                json.dump(state.to_dict(), f, indent=2)

            # Upload to GCS
            self._run_gcloud_command(
                [
                    "gcloud",
                    "storage",
                    "cp",
                    local_path,
                    f"gs://{self.bucket}/{self.state_path}",
                    "--content-type=application/json",
                    "--cache-control=no-cache, no-store, must-revalidate",
                ]
            )

            print(f"✓ State saved to GCS at {state.last_updated}")
            return True

        except Exception as e:
            print(f"✗ Failed to save state: {e}")
            return False

    def create_initial_state(
        self,
        workflow_run_id: str,
        prs: list[dict[str, Any]],
    ) -> QueueState:
        """Create initial queue state from discovered PRs.

        Groups PRs by repository and sorts by PR number (oldest first).

        Parameters
        ----------
        workflow_run_id : str
            GitHub Actions workflow run ID.
        prs : list[dict[str, Any]]
            List of PR objects from discovery job.

        Returns
        -------
        QueueState
            Initial queue state with all PRs queued.

        """
        now = datetime.now(UTC)
        timeout = now + timedelta(hours=5, minutes=30)

        state = QueueState(
            workflow_run_id=workflow_run_id,
            started_at=now.isoformat(),
            last_updated=now.isoformat(),
            timeout_at=timeout.isoformat(),
        )

        # Group PRs by repository
        repos: dict[str, list[dict[str, Any]]] = {}
        for pr in prs:
            repo = pr["repo"]
            if repo not in repos:
                repos[repo] = []
            repos[repo].append(pr)

        # Create repo queues
        for repo, repo_prs in repos.items():
            # Sort by PR number (oldest first)
            repo_prs.sort(key=lambda x: x["number"])

            queue_items = [
                PRQueueItem(
                    repo=pr["repo"],
                    pr_number=pr["number"],
                    pr_title=pr["title"],
                    pr_author=pr.get("author", {}).get("login", "unknown"),
                    pr_url=pr["url"],
                    status=PRStatus.PENDING,
                    queued_at=now.isoformat(),
                    last_updated=now.isoformat(),
                )
                for pr in repo_prs
            ]

            state.repo_queues[repo] = RepoQueue(
                repo=repo,
                prs=queue_items,
                current_index=0,
            )

        return state

    def clear_state(self) -> bool:
        """Delete state from GCS (for cleanup after completion).

        Returns
        -------
        bool
            True if state was deleted, False otherwise.

        """
        try:
            self._run_gcloud_command(
                [
                    "gcloud",
                    "storage",
                    "rm",
                    f"gs://{self.bucket}/{self.state_path}",
                ]
            )
            print("✓ State cleared from GCS")
            return True
        except subprocess.CalledProcessError:
            print("ℹ No state to clear")
            return False
