"""Workflow client for GitHub operations via gh CLI."""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Literal

from ..utils.logging import log_error, log_info, log_success, log_warning
from .models import PRQueueItem

WorkflowStatus = Literal["SUCCESS", "FAILURE", "RUNNING", "CANCELLED", "UNKNOWN"]


class WorkflowClient:
    """Interact with GitHub workflows and PRs via gh CLI.

    Parameters
    ----------
    gh_token : str
        GitHub personal access token.
    bot_repo : str, optional
        Bot repository name (default="VectorInstitute/aieng-bot").

    Attributes
    ----------
    gh_token : str
        GitHub personal access token.
    bot_repo : str
        Bot repository name.

    """

    def __init__(self, gh_token: str, bot_repo: str = "VectorInstitute/aieng-bot"):
        """Initialize workflow client.

        Parameters
        ----------
        gh_token : str
            GitHub personal access token.
        bot_repo : str, optional
            Bot repository name (default="VectorInstitute/aieng-bot").

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
        # Inherit environment and add GH_TOKEN
        env = os.environ.copy()
        env["GH_TOKEN"] = self.gh_token

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        return result.stdout.strip()

    def check_latest_comment(self, pr: PRQueueItem, author: str | None = None) -> str:
        """Get the latest comment from a specific author.

        Parameters
        ----------
        pr : PRQueueItem
            PR to check comments for.
        author : str or None, optional
            Comment author to filter by. If None, infers from pr.pr_author.

        Returns
        -------
        str
            Latest comment body from author, or empty string if none found.

        """
        # Infer author from PR if not specified
        if author is None:
            if pr.pr_author == "app/dependabot":
                author = "dependabot"
            elif pr.pr_author == "app/pre-commit-ci":
                author = "pre-commit-ci[bot]"
            else:
                author = pr.pr_author

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

    def get_pr_head_sha(self, pr: PRQueueItem) -> str | None:
        """Get current head commit SHA of PR.

        Parameters
        ----------
        pr : PRQueueItem
            PR to get head SHA for.

        Returns
        -------
        str or None
            Head commit SHA (40-character hex string), or None if failed to retrieve.

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
                    "headRefOid",
                    "--jq",
                    ".headRefOid",
                ]
            )
        except subprocess.CalledProcessError as e:
            log_error(f"Failed to get PR head SHA: {e}")
            return None

    def trigger_rebase(self, pr: PRQueueItem) -> tuple[bool, str | None, bool]:
        """Trigger bot-specific rebase command.

        For Dependabot: Post @dependabot rebase comment (async)
        For pre-commit.ci: Manually rebase via git operations (sync)

        Parameters
        ----------
        pr : PRQueueItem
            PR to trigger rebase for.

        Returns
        -------
        tuple[bool, str | None, bool]
            (success, new_sha, sha_changed) where:
            - success: True if rebase triggered/succeeded, False on failure
            - new_sha: New head SHA (only for manual rebases, None for async)
            - sha_changed: True if SHA changed (only for manual rebases, True for async to trigger polling)

        """
        # Dependabot PRs use comment-based rebase (async)
        if pr.pr_author == "app/dependabot":
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
                log_success(f"  Rebase triggered for {pr.repo}#{pr.pr_number}")
                return (True, None, True)  # Async, will poll for SHA change
            except subprocess.CalledProcessError as e:
                log_error(f"  Failed to trigger rebase: {e}")
                return (False, None, False)

        # pre-commit.ci PRs use manual git rebase (sync)
        if pr.pr_author == "app/pre-commit-ci":
            log_info("  Manually rebasing pre-commit.ci PR via git operations")
            return self._manual_rebase(pr)

        # Unknown bot author
        log_error(f"  Unknown bot author: {pr.pr_author}, cannot rebase")
        return (False, None, False)

    def _manual_rebase(self, pr: PRQueueItem) -> tuple[bool, str | None, bool]:
        """Manually rebase a PR branch via git operations.

        Clones the repo, checks out PR branch, rebases onto base, and force-pushes.

        Parameters
        ----------
        pr : PRQueueItem
            PR to rebase.

        Returns
        -------
        tuple[bool, str | None, bool]
            (success, new_sha, sha_changed) where:
            - success: True if rebase succeeded, False on failure
            - new_sha: New head SHA after rebase (None on failure)
            - sha_changed: True if rebase created new commits, False if already up-to-date

        """
        try:
            # Get PR details (head ref, base ref)
            pr_json = self._run_gh_command(
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr.pr_number),
                    "--repo",
                    pr.repo,
                    "--json",
                    "headRefName,baseRefName",
                ]
            )
            pr_data = json.loads(pr_json)
            head_ref = pr_data["headRefName"]
            base_ref = pr_data["baseRefName"]

            log_info(f"    Rebasing {head_ref} onto {base_ref}")

            # Create temporary directory for clone
            with tempfile.TemporaryDirectory() as tmpdir:
                repo_dir = Path(tmpdir) / "repo"

                # Inherit environment and add GH_TOKEN for all git operations
                env = os.environ.copy()
                env["GH_TOKEN"] = self.gh_token

                # Clone the repository
                log_info(f"    Cloning {pr.repo}...")
                subprocess.run(
                    [
                        "gh",
                        "repo",
                        "clone",
                        pr.repo,
                        str(repo_dir),
                        "--",
                        "--depth=50",
                    ],
                    check=True,
                    capture_output=True,
                    env=env,
                )

                # Configure git user for commits
                subprocess.run(
                    ["git", "config", "user.name", "aieng-bot[bot]"],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    [
                        "git",
                        "config",
                        "user.email",
                        "aieng-bot@vectorinstitute.ai",
                    ],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                )

                # Set remote URL to include token for authentication
                # Using x-access-token in URL provides auth without credential helper
                remote_url = (
                    f"https://x-access-token:{self.gh_token}@github.com/{pr.repo}.git"
                )
                subprocess.run(
                    ["git", "remote", "set-url", "origin", remote_url],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                )

                # Fetch the PR branch
                log_info(f"    Fetching branch {head_ref}...")
                subprocess.run(
                    ["git", "fetch", "origin", f"{head_ref}:{head_ref}"],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                )

                # Checkout PR branch
                subprocess.run(
                    ["git", "checkout", head_ref],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                )

                # Get SHA before rebase
                result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                sha_before = result.stdout.strip()

                # Fetch latest base branch
                subprocess.run(
                    ["git", "fetch", "origin", base_ref],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                )

                # Rebase onto base branch
                log_info(f"    Rebasing onto origin/{base_ref}...")
                subprocess.run(
                    ["git", "rebase", f"origin/{base_ref}"],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                )

                # Get SHA after rebase
                result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                sha_after = result.stdout.strip()

                # Check if rebase created new commits
                sha_changed = sha_after != sha_before

                if not sha_changed:
                    log_success(
                        f"  Branch already up-to-date with {base_ref}, no rebase needed"
                    )
                    return (True, sha_after, False)

                # Force push to PR branch (only if SHA changed)
                # Using --force instead of --force-with-lease because the shallow clone
                # doesn't set up remote tracking properly, causing "stale info" errors.
                # This is safe because we just fetched and we're the only ones modifying
                # this branch during the rebase operation.
                log_info("    Force-pushing rebased branch...")
                subprocess.run(
                    ["git", "push", "--force", "origin", head_ref],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                )

                log_success(f"  Successfully rebased {pr.repo}#{pr.pr_number}")
                return (True, sha_after, True)

        except subprocess.CalledProcessError as e:
            log_error(f"  Failed to manually rebase: {e}")
            if e.stderr:
                log_error(f"  Error output: {e.stderr.decode()}")
            return (False, None, False)
        except Exception as e:
            log_error(f"  Unexpected error during manual rebase: {e}")
            return (False, None, False)

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

            log_success(f"  Fix workflow triggered for {pr.repo}#{pr.pr_number}")

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
                log_info(f"    Workflow run ID: {run_id}")
                return run_id

            return None

        except subprocess.CalledProcessError as e:
            log_error(f"  Failed to trigger fix workflow: {e}")
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

        log_info(f"  ⏳ Monitoring fix workflow (run {run_id})...")

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
                        log_success("  Fix workflow succeeded")
                        return "SUCCESS"
                    if conclusion == "failure":
                        log_error("  Fix workflow failed")
                        return "FAILURE"
                    if conclusion == "cancelled":
                        log_warning("  ⚠ Fix workflow cancelled")
                        return "CANCELLED"

                # Still running
                log_info(
                    f"  Fix workflow status: {status} "
                    f"(attempt {attempt}/{max_attempts})"
                )

                if attempt < max_attempts:
                    time.sleep(check_interval)

            except subprocess.CalledProcessError as e:
                log_error(f"  Error polling workflow: {e}")
                return "UNKNOWN"

        log_info(f"  ⏱ Timeout: Workflow still running after {timeout_minutes} minutes")
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

            log_success(f"  Auto-merge enabled for {pr.repo}#{pr.pr_number}")
            return True

        except subprocess.CalledProcessError as e:
            log_error(f"  Failed to enable auto-merge: {e}")
            return False
