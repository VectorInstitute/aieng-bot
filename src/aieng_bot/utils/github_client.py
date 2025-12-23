"""GitHub API client using gh CLI."""

import json
import os
import re
import subprocess
import tempfile

from ..classifier.models import CheckFailure, PRContext
from .logging import log_error, log_info, log_warning


class GitHubClient:
    """GitHub API client using gh CLI.

    This client wraps the gh CLI tool to interact with GitHub API.
    It requires GITHUB_TOKEN or GH_TOKEN environment variable to be set.

    Attributes
    ----------
    github_token : str
        GitHub personal access token for API authentication.

    """

    def __init__(self, github_token: str | None = None) -> None:
        """Initialize GitHub client with token.

        Parameters
        ----------
        github_token : str, optional
            GitHub token. If None, reads from GITHUB_TOKEN or GH_TOKEN
            environment variable.

        Raises
        ------
        ValueError
            If GitHub token is not provided and not found in environment.

        """
        self.github_token = (
            github_token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        )
        if not self.github_token:
            raise ValueError(
                "GitHub token not found. Please set GITHUB_TOKEN or GH_TOKEN "
                "environment variable, or provide it via --github-token flag."
            )

    def _run_gh_command(
        self, args: list[str], check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """Run gh CLI command with proper error handling.

        Parameters
        ----------
        args : list[str]
            Command arguments to pass to gh CLI.
        check : bool, optional
            Whether to raise CalledProcessError on non-zero exit code.
            Defaults to True.

        Returns
        -------
        subprocess.CompletedProcess[str]
            Completed process with stdout, stderr, and return code.

        Raises
        ------
        subprocess.CalledProcessError
            If command fails and check=True.

        """
        env = os.environ.copy()
        if self.github_token:
            env["GH_TOKEN"] = self.github_token

        try:
            return subprocess.run(
                ["gh"] + args,
                capture_output=True,
                text=True,
                check=check,
                env=env,
                timeout=120,  # 2 minute timeout
            )
        except subprocess.TimeoutExpired:
            log_error(f"gh command timed out after 120 seconds: gh {' '.join(args)}")
            raise
        except FileNotFoundError:
            log_error(
                "gh CLI not found. Please install it from https://cli.github.com/"
            )
            raise

    def get_pr_details(self, repo: str, pr_number: int) -> PRContext:
        """Fetch PR details from GitHub API.

        Parameters
        ----------
        repo : str
            Repository in format "owner/repo".
        pr_number : int
            Pull request number.

        Returns
        -------
        PRContext
            PR context with title, author, branch names, etc.

        Raises
        ------
        subprocess.CalledProcessError
            If PR cannot be fetched.
        ValueError
            If PR data is invalid.

        """
        log_info(f"Fetching PR details for {repo}#{pr_number}")

        result = self._run_gh_command(
            [
                "pr",
                "view",
                str(pr_number),
                "--repo",
                repo,
                "--json",
                "title,author,headRefName,baseRefName,mergeable",
            ]
        )

        pr_data = json.loads(result.stdout)

        return PRContext(
            repo=repo,
            pr_number=pr_number,
            pr_title=pr_data["title"],
            pr_author=pr_data["author"]["login"],
            head_ref=pr_data["headRefName"],
            base_ref=pr_data["baseRefName"],
        )

    def get_failed_checks(self, repo: str, pr_number: int) -> list[CheckFailure]:
        """Fetch failed checks from PR.

        Parameters
        ----------
        repo : str
            Repository in format "owner/repo".
        pr_number : int
            Pull request number.

        Returns
        -------
        list[CheckFailure]
            List of failed CI checks.

        """
        log_info(f"Fetching failed checks for {repo}#{pr_number}")

        result = self._run_gh_command(
            [
                "pr",
                "view",
                str(pr_number),
                "--repo",
                repo,
                "--json",
                "statusCheckRollup",
            ]
        )

        pr_data = json.loads(result.stdout)
        status_checks = pr_data.get("statusCheckRollup", [])

        # Filter for failed checks
        return [
            CheckFailure(
                name=check.get("name", ""),
                conclusion=check.get("conclusion", ""),
                workflow_name=check.get("workflowName", ""),
                details_url=check.get("detailsUrl", ""),
                started_at=check.get("startedAt", ""),
                completed_at=check.get("completedAt", ""),
            )
            for check in status_checks
            if check.get("conclusion") == "FAILURE"
        ]

    def get_failure_logs(self, repo: str, failed_checks: list[CheckFailure]) -> str:
        """Extract failure logs from failed checks.

        Downloads full logs from all failed checks without filtering or truncation.
        Claude will use bash tool to search through the logs file.

        Parameters
        ----------
        repo : str
            Repository in format "owner/repo".
        failed_checks : list[CheckFailure]
            List of failed CI checks.

        Returns
        -------
        str
            Path to temp file containing all failure logs.

        """
        log_info(f"Extracting failure logs from {len(failed_checks)} failed checks")

        # Create temp file for logs
        total_bytes_written = 0
        runs_processed = set()  # Track runs to avoid duplicates

        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".txt", prefix="failure-logs-"
        ) as temp_file:
            logs_file = temp_file.name

            for check in failed_checks:
                if not check.details_url:
                    continue

                # Extract run ID from URL
                # Format: https://github.com/OWNER/REPO/actions/runs/RUN_ID/job/JOB_ID
                run_match = re.search(r"runs/(\d+)", check.details_url)
                if not run_match:
                    log_warning(
                        f"Could not extract run ID from URL: {check.details_url}"
                    )
                    continue

                run_id = run_match.group(1)

                # Skip if we already processed this run (multiple jobs in same run)
                if run_id in runs_processed:
                    continue

                runs_processed.add(run_id)
                log_info(f"Fetching logs for check '{check.name}' (run {run_id})")

                try:
                    # Fetch full run logs (no filtering, no truncation)
                    result = self._run_gh_command(
                        ["run", "view", run_id, "--repo", repo, "--log"], check=False
                    )

                    if result.returncode != 0:
                        error_msg = (
                            result.stderr.strip() if result.stderr else "unknown error"
                        )
                        log_warning(
                            f"Failed to fetch logs for run {run_id}: {error_msg}"
                        )
                        continue

                    # Write full logs to file
                    full_logs = result.stdout
                    temp_file.write(f"\n\n{'=' * 80}\n")
                    temp_file.write(f"Logs from check: {check.name} (run {run_id})\n")
                    temp_file.write(f"{'=' * 80}\n\n")
                    temp_file.write(full_logs)
                    total_bytes_written += len(full_logs)

                except Exception as e:
                    log_warning(f"Error processing logs for run {run_id}: {e}")
                    continue

        if total_bytes_written == 0:
            # No logs extracted, write placeholder
            with open(logs_file, "w") as f:
                f.write("No failure logs could be extracted from CI checks\n")
            log_warning("No failure logs could be extracted")
        else:
            # Convert bytes to human-readable size
            size_mb = total_bytes_written / (1024 * 1024)
            log_info(
                f"Extracted {size_mb:.2f}MB of failure logs to {logs_file} "
                f"({len(runs_processed)} runs)"
            )

        return logs_file

    def check_merge_conflicts(self, repo: str, pr_number: int) -> bool:
        """Check if PR has merge conflicts.

        Parameters
        ----------
        repo : str
            Repository in format "owner/repo".
        pr_number : int
            Pull request number.

        Returns
        -------
        bool
            True if PR has merge conflicts, False otherwise.

        """
        log_info(f"Checking merge conflict status for {repo}#{pr_number}")

        result = self._run_gh_command(
            [
                "pr",
                "view",
                str(pr_number),
                "--repo",
                repo,
                "--json",
                "mergeable",
            ]
        )

        pr_data = json.loads(result.stdout)
        mergeable = pr_data.get("mergeable", "")

        return mergeable == "CONFLICTING"
