"""Status poller for PR check monitoring."""

import json
import subprocess
import time
from typing import Literal

from .models import PRQueueItem

CheckStatus = Literal["COMPLETED", "FAILED", "RUNNING", "NO_CHECKS"]


class StatusPoller:
    """Poll PR check status with exponential backoff.

    Reuses patterns from monitor-org-bot-prs.yml (lines 148-207).

    Parameters
    ----------
    gh_token : str
        GitHub personal access token.

    Attributes
    ----------
    gh_token : str
        GitHub personal access token.

    """

    def __init__(self, gh_token: str):
        """Initialize status poller.

        Parameters
        ----------
        gh_token : str
            GitHub personal access token.

        """
        self.gh_token = gh_token

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

    def check_pr_status(self, pr: PRQueueItem) -> tuple[bool, bool, str]:
        """Check PR status with retry logic.

        Implements same logic as monitor-org-bot-prs.yml:157-207.

        Parameters
        ----------
        pr : PRQueueItem
            PR to check status for.

        Returns
        -------
        tuple[bool, bool, str]
            (all_passed, has_failures, mergeable) where:
            - all_passed: True if all checks passed or skipped
            - has_failures: True if any check failed
            - mergeable: "MERGEABLE", "CONFLICTING", or "UNKNOWN"

        """
        # Initial delay for GitHub to compute status
        print("  ⏳ Waiting 15s for GitHub to compute merge status...")
        time.sleep(15)

        max_retries = 5
        retry_delay = 10

        for attempt in range(1, max_retries + 1):
            print(f"  Attempt {attempt}/{max_retries}: Checking PR status...")

            status_json = self._run_gh_command(
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr.pr_number),
                    "--repo",
                    pr.repo,
                    "--json",
                    "statusCheckRollup,mergeable",
                ]
            )

            status_data = json.loads(status_json)

            # Check if all checks passed
            rollup = status_data.get("statusCheckRollup") or []
            all_passed = all(
                check.get("conclusion") in ["SUCCESS", "NEUTRAL", "SKIPPED", None]
                for check in rollup
                if check.get("name") != "Monitor Organization Bot PRs"
            )

            # Check if any checks failed
            has_failures = any(check.get("conclusion") == "FAILURE" for check in rollup)

            mergeable = status_data.get("mergeable", "UNKNOWN")

            print(
                f"    Status: all_passed={all_passed}, "
                f"has_failures={has_failures}, mergeable={mergeable}"
            )

            if mergeable != "UNKNOWN":
                return all_passed, has_failures, mergeable

            if attempt < max_retries:
                wait_time = retry_delay * attempt
                print(f"    ⏳ Waiting {wait_time}s before retry...")
                time.sleep(wait_time)

        print("  ⚠ Mergeable status still UNKNOWN after retries")
        return all_passed, has_failures, "UNKNOWN"

    def wait_for_checks_completion(
        self,
        pr: PRQueueItem,
        timeout_minutes: int = 30,
    ) -> CheckStatus:
        """Wait for PR checks to complete.

        Polls every 30 seconds up to timeout_minutes.
        Similar to fix-remote-pr.yml:603-673.

        Parameters
        ----------
        pr : PRQueueItem
            PR to monitor.
        timeout_minutes : int, optional
            Maximum time to wait in minutes (default=30).

        Returns
        -------
        CheckStatus
            Final check status: "COMPLETED", "FAILED", "RUNNING", or "NO_CHECKS".

        """
        check_interval = 30
        max_attempts = (timeout_minutes * 60) // check_interval

        print(f"  ⏳ Waiting up to {timeout_minutes} minutes for checks to complete...")

        for attempt in range(1, max_attempts + 1):
            print(f"  Check attempt {attempt}/{max_attempts}...")

            status_json = self._run_gh_command(
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr.pr_number),
                    "--repo",
                    pr.repo,
                    "--json",
                    "statusCheckRollup",
                ]
            )

            data = json.loads(status_json)
            rollup = data.get("statusCheckRollup") or []

            if not rollup:
                if attempt > 2:  # Give checks time to start
                    print("    ⚠ No checks found")
                    return "NO_CHECKS"
                time.sleep(check_interval)
                continue

            # Check status
            any_running = any(
                check.get("conclusion") is None
                or check.get("status") in ["IN_PROGRESS", "QUEUED", "PENDING"]
                for check in rollup
            )

            any_failed = any(check.get("conclusion") == "FAILURE" for check in rollup)

            if not any_running:
                if any_failed:
                    print("  ✗ Checks failed")
                    return "FAILED"
                print("  ✓ Checks completed successfully")
                return "COMPLETED"

            if attempt < max_attempts:
                time.sleep(check_interval)

        print(f"  ⏱ Timeout: Checks still running after {timeout_minutes} minutes")
        return "RUNNING"
