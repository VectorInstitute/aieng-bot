"""Workflow client for GitHub operations via gh CLI."""

import json
import subprocess
import time
from typing import Literal

from .models import PRQueueItem

WorkflowStatus = Literal["SUCCESS", "FAILURE", "RUNNING", "CANCELLED", "UNKNOWN"]


class WorkflowClient:
    """Interact with GitHub workflows and PRs via gh CLI.

    Parameters
    ----------
    gh_token : str
        GitHub personal access token.
    bot_repo : str, optional
        Bot repository name (default="VectorInstitute/aieng-bot-maintain").

    Attributes
    ----------
    gh_token : str
        GitHub personal access token.
    bot_repo : str
        Bot repository name.

    """

    def __init__(
        self, gh_token: str, bot_repo: str = "VectorInstitute/aieng-bot-maintain"
    ):
        """Initialize workflow client.

        Parameters
        ----------
        gh_token : str
            GitHub personal access token.
        bot_repo : str, optional
            Bot repository name (default="VectorInstitute/aieng-bot-maintain").

        """
        self.gh_token = gh_token
        self.bot_repo = bot_repo

    def _run_gh_command(self, cmd: list[str]) -> str:
        """Execute gh CLI command.

        Parameters
        ----------
        cmd : list[str]
            Command and arguments to execute.

        Returns
        -------
        str
            Stripped stdout from command.

        Raises
        ------
        subprocess.CalledProcessError
            If command fails.

        """
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            env={"GH_TOKEN": self.gh_token},
        )
        return result.stdout.strip()

    def check_latest_comment(self, pr: PRQueueItem, author: str = "dependabot") -> str:
        """Get the latest comment from a specific author.

        Parameters
        ----------
        pr : PRQueueItem
            PR to check comments for.
        author : str, optional
            Comment author to filter by (default="dependabot").

        Returns
        -------
        str
            Latest comment body from author, or empty string if none found.

        """
        try:
            return self._run_gh_command(
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr.pr_number),
                    "--repo",
                    pr.repo,
                    "--json",
                    "comments",
                    "--jq",
                    f'.comments | map(select(.author.login == "{author}")) | .[-1].body // ""',
                ]
            )
        except subprocess.CalledProcessError:
            return ""

    def trigger_rebase(self, pr: PRQueueItem) -> bool:
        """Trigger @dependabot rebase comment.

        Parameters
        ----------
        pr : PRQueueItem
            PR to trigger rebase for.

        Returns
        -------
        bool
            True on success, False on failure.

        """
        try:
            self._run_gh_command(
                [
                    "gh",
                    "pr",
                    "comment",
                    str(pr.pr_number),
                    "--repo",
                    pr.repo,
                    "--body",
                    "@dependabot rebase",
                ]
            )
            print(f"  ✓ Rebase triggered for {pr.repo}#{pr.pr_number}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Failed to trigger rebase: {e}")
            return False

    def trigger_fix_workflow(self, pr: PRQueueItem) -> str | None:
        """Trigger fix-remote-pr.yml workflow.

        Parameters
        ----------
        pr : PRQueueItem
            PR to fix.

        Returns
        -------
        str or None
            Workflow run ID on success, None on failure.

        """
        try:
            # Trigger workflow
            self._run_gh_command(
                [
                    "gh",
                    "workflow",
                    "run",
                    "fix-remote-pr.yml",
                    "--repo",
                    self.bot_repo,
                    "--field",
                    f"target_repo={pr.repo}",
                    "--field",
                    f"pr_number={pr.pr_number}",
                ]
            )

            print(f"  ✓ Fix workflow triggered for {pr.repo}#{pr.pr_number}")

            # Wait a bit for workflow to appear in API
            time.sleep(5)

            # Get latest workflow run ID
            runs_json = self._run_gh_command(
                [
                    "gh",
                    "run",
                    "list",
                    "--repo",
                    self.bot_repo,
                    "--workflow",
                    "fix-remote-pr.yml",
                    "--limit",
                    "1",
                    "--json",
                    "databaseId",
                ]
            )

            runs = json.loads(runs_json)
            if runs:
                run_id = str(runs[0]["databaseId"])
                print(f"    Workflow run ID: {run_id}")
                return run_id

            return None

        except subprocess.CalledProcessError as e:
            print(f"  ✗ Failed to trigger fix workflow: {e}")
            return None

    def poll_workflow_status(
        self,
        run_id: str,
        timeout_minutes: int = 30,
    ) -> WorkflowStatus:
        """Poll workflow status until completion or timeout.

        Checks every 30 seconds.

        Parameters
        ----------
        run_id : str
            GitHub workflow run ID.
        timeout_minutes : int, optional
            Maximum time to wait in minutes (default=30).

        Returns
        -------
        WorkflowStatus
            Final workflow status.

        """
        check_interval = 30
        max_attempts = (timeout_minutes * 60) // check_interval

        print(f"  ⏳ Monitoring fix workflow (run {run_id})...")

        for attempt in range(1, max_attempts + 1):
            try:
                run_json = self._run_gh_command(
                    [
                        "gh",
                        "run",
                        "view",
                        run_id,
                        "--repo",
                        self.bot_repo,
                        "--json",
                        "status,conclusion",
                    ]
                )

                run_data = json.loads(run_json)

                status = run_data.get("status")
                conclusion = run_data.get("conclusion")

                # Workflow completed
                if status == "completed":
                    if conclusion == "success":
                        print("  ✓ Fix workflow succeeded")
                        return "SUCCESS"
                    if conclusion == "failure":
                        print("  ✗ Fix workflow failed")
                        return "FAILURE"
                    if conclusion == "cancelled":
                        print("  ⚠ Fix workflow cancelled")
                        return "CANCELLED"

                # Still running
                print(
                    f"  Fix workflow status: {status} "
                    f"(attempt {attempt}/{max_attempts})"
                )

                if attempt < max_attempts:
                    time.sleep(check_interval)

            except subprocess.CalledProcessError as e:
                print(f"  ✗ Error polling workflow: {e}")
                return "UNKNOWN"

        print(f"  ⏱ Timeout: Workflow still running after {timeout_minutes} minutes")
        return "RUNNING"

    def auto_merge_pr(self, pr: PRQueueItem) -> bool:
        """Approve and enable auto-merge for PR.

        Implements logic from monitor-org-bot-prs.yml:210-248.

        Parameters
        ----------
        pr : PRQueueItem
            PR to auto-merge.

        Returns
        -------
        bool
            True on success, False on failure.

        """
        try:
            # Check if already approved
            pr_json = self._run_gh_command(
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr.pr_number),
                    "--repo",
                    pr.repo,
                    "--json",
                    "reviewDecision",
                ]
            )

            pr_data = json.loads(pr_json)

            if pr_data.get("reviewDecision") != "APPROVED":
                # Approve PR
                approve_msg = (
                    "✅ All checks passed. Auto-approving bot PR.\n\n"
                    "🤖 *AI Engineering Maintenance Bot - "
                    "Maintaining Vector Institute Repositories built by AI Engineering*"
                )
                self._run_gh_command(
                    [
                        "gh",
                        "pr",
                        "review",
                        str(pr.pr_number),
                        "--repo",
                        pr.repo,
                        "--approve",
                        "--body",
                        approve_msg,
                    ]
                )

            # Enable auto-merge
            self._run_gh_command(
                [
                    "gh",
                    "pr",
                    "merge",
                    str(pr.pr_number),
                    "--repo",
                    pr.repo,
                    "--auto",
                    "--squash",
                ]
            )

            # Comment success
            success_msg = (
                "✅ All checks passed! This PR will be automatically merged.\n\n"
                "🤖 *AI Engineering Maintenance Bot - "
                "Maintaining Vector Institute Repositories built by AI Engineering*"
            )
            self._run_gh_command(
                [
                    "gh",
                    "pr",
                    "comment",
                    str(pr.pr_number),
                    "--repo",
                    pr.repo,
                    "--body",
                    success_msg,
                ]
            )

            print(f"  ✓ Auto-merge enabled for {pr.repo}#{pr.pr_number}")
            return True

        except subprocess.CalledProcessError as e:
            print(f"  ✗ Failed to enable auto-merge: {e}")
            return False
