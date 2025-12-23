"""Check waiter for monitoring PR check status."""

import json
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class CheckStatus(str, Enum):
    """PR check status."""

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RUNNING = "RUNNING"
    NO_CHECKS = "NO_CHECKS"
    TIMEOUT = "TIMEOUT"


@dataclass
class WaitResult:
    """Result of waiting for checks."""

    status: CheckStatus
    elapsed_seconds: float
    attempts: int
    message: str


class CheckWaiter:
    """Waits for PR checks to complete."""

    def __init__(
        self,
        repo: str,
        pr_number: int,
        gh_token: str,
        max_wait_seconds: int = 900,  # 15 minutes
        check_interval_seconds: int = 30,
    ) -> None:
        """Initialize check waiter.

        Args:
            repo: Repository in owner/name format
            pr_number: PR number
            gh_token: GitHub token for API access
            max_wait_seconds: Maximum time to wait
            check_interval_seconds: Seconds between status checks

        """
        self.repo = repo
        self.pr_number = pr_number
        self.gh_token = gh_token
        self.max_wait_seconds = max_wait_seconds
        self.check_interval_seconds = check_interval_seconds
        self.max_attempts = max_wait_seconds // check_interval_seconds

    def get_check_status(self) -> CheckStatus:
        """Get current check status for the PR.

        Returns:
            Current check status

        Raises:
            RuntimeError: If gh CLI command fails

        """
        try:
            # Get PR check status using gh CLI
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "view",
                    str(self.pr_number),
                    "--repo",
                    self.repo,
                    "--json",
                    "statusCheckRollup",
                ],
                capture_output=True,
                text=True,
                check=True,
                env={"GH_TOKEN": self.gh_token},
            )

            data = json.loads(result.stdout)
            return self._analyze_checks(data.get("statusCheckRollup", []))

        except subprocess.CalledProcessError as e:
            msg = f"Failed to get check status: {e.stderr}"
            raise RuntimeError(msg) from e
        except json.JSONDecodeError as e:
            msg = f"Failed to parse check status JSON: {e}"
            raise RuntimeError(msg) from e

    def _analyze_checks(self, checks: list[dict[str, Any]]) -> CheckStatus:
        """Analyze check rollup data to determine status.

        Args:
            checks: List of check status objects from GitHub API

        Returns:
            Overall check status

        """
        if not checks:
            return CheckStatus.NO_CHECKS

        # Filter out malformed/stale checks (where both status and conclusion are null)
        valid_checks = [
            c
            for c in checks
            if c.get("status") is not None or c.get("conclusion") is not None
        ]

        if not valid_checks:
            return CheckStatus.NO_CHECKS

        # Check for running/pending/queued checks
        for check in valid_checks:
            status = check.get("status")
            if status in ("IN_PROGRESS", "QUEUED", "PENDING"):
                return CheckStatus.RUNNING

        # Check for failures
        for check in valid_checks:
            conclusion = check.get("conclusion")
            if conclusion == "FAILURE":
                return CheckStatus.FAILED

        # All checks completed successfully
        return CheckStatus.COMPLETED

    def wait(self) -> WaitResult:
        """Wait for checks to complete.

        Returns:
            Wait result with status and metadata

        """
        start_time = time.time()
        attempt = 1

        while attempt <= self.max_attempts:
            try:
                status = self.get_check_status()

                # Terminal states
                if status == CheckStatus.COMPLETED:
                    elapsed = time.time() - start_time
                    return WaitResult(
                        status=CheckStatus.COMPLETED,
                        elapsed_seconds=elapsed,
                        attempts=attempt,
                        message="All checks completed successfully",
                    )

                if status == CheckStatus.FAILED:
                    elapsed = time.time() - start_time
                    return WaitResult(
                        status=CheckStatus.FAILED,
                        elapsed_seconds=elapsed,
                        attempts=attempt,
                        message="Some checks failed",
                    )

                # If no checks found after first 2 attempts, continue waiting
                # (checks might not have started yet)
                # Keep waiting for a few more attempts in case checks start late
                if status == CheckStatus.NO_CHECKS and attempt > 5:
                    elapsed = time.time() - start_time
                    return WaitResult(
                        status=CheckStatus.NO_CHECKS,
                        elapsed_seconds=elapsed,
                        attempts=attempt,
                        message="No checks found on PR after multiple attempts",
                    )

            except RuntimeError as e:
                # If we can't get status, log and continue
                print(f"Warning: {e}")

            # Sleep before next attempt (unless this is the last attempt)
            if attempt < self.max_attempts:
                time.sleep(self.check_interval_seconds)

            attempt += 1

        # Timeout
        elapsed = time.time() - start_time
        return WaitResult(
            status=CheckStatus.TIMEOUT,
            elapsed_seconds=elapsed,
            attempts=self.max_attempts,
            message=f"Checks still running after {self.max_wait_seconds}s timeout",
        )
