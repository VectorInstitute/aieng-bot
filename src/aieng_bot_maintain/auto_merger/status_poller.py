"""Status poller for PR check monitoring."""

import json
import subprocess
import time
from typing import Literal

from ..utils.logging import log_error, log_info, log_success, log_warning
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
        log_info("  ⏳ Waiting 15s for GitHub to compute merge status...")
        time.sleep(15)

        max_retries = 5
        retry_delay = 10

        for attempt in range(1, max_retries + 1):
            log_info(f"  Attempt {attempt}/{max_retries}: Checking PR status...")

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

            # Check if all checks passed - handle both CheckRun and StatusContext
            rollup = status_data.get("statusCheckRollup") or []

            def is_check_passed(check: dict) -> bool:
                """Check if a check has passed or is neutral."""
                # Skip our own monitoring check
                if check.get("name") == "Monitor Organization Bot PRs":
                    return True

                typename = check.get("__typename")
                if typename == "StatusContext":
                    # StatusContext uses 'state' field
                    state = check.get("state")
                    return state in ["SUCCESS"]
                # CheckRun uses 'conclusion' field
                conclusion = check.get("conclusion")
                return conclusion in ["SUCCESS", "NEUTRAL", "SKIPPED"]

            def is_check_failed(check: dict) -> bool:
                """Check if a check has failed."""
                # Skip our own monitoring check
                if check.get("name") == "Monitor Organization Bot PRs":
                    return False

                typename = check.get("__typename")
                if typename == "StatusContext":
                    state = check.get("state")
                    return state in ["FAILURE", "ERROR"]
                return check.get("conclusion") == "FAILURE"

            all_passed = all(is_check_passed(check) for check in rollup)
            has_failures = any(is_check_failed(check) for check in rollup)

            mergeable = status_data.get("mergeable", "UNKNOWN")

            log_info(
                f"    Status: all_passed={all_passed}, "
                f"has_failures={has_failures}, mergeable={mergeable}"
            )

            if mergeable != "UNKNOWN":
                return all_passed, has_failures, mergeable

            if attempt < max_retries:
                wait_time = retry_delay * attempt
                log_info(f"    ⏳ Waiting {wait_time}s before retry...")
                time.sleep(wait_time)

        log_warning("  Mergeable status still UNKNOWN after retries")
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

        log_info(
            f"  ⏳ Waiting up to {timeout_minutes} minutes for checks to complete..."
        )

        for attempt in range(1, max_attempts + 1):
            log_info(f"  Check attempt {attempt}/{max_attempts}...")

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
                    log_warning("    No checks found")
                    return "NO_CHECKS"
                time.sleep(check_interval)
                continue

            # Check status - handle both CheckRun and StatusContext types
            def is_check_running(check: dict) -> bool:
                """Check if a check is still running."""
                typename = check.get("__typename")
                if typename == "StatusContext":
                    # StatusContext uses 'state' field
                    state = check.get("state")
                    return state in ["PENDING", "EXPECTED"]
                # CheckRun uses 'conclusion' and 'status' fields
                return check.get("conclusion") is None and check.get("status") in [
                    "IN_PROGRESS",
                    "QUEUED",
                    "PENDING",
                ]

            def is_check_failed(check: dict) -> bool:
                """Check if a check has failed."""
                typename = check.get("__typename")
                if typename == "StatusContext":
                    # StatusContext uses 'state' field
                    state = check.get("state")
                    return state in ["FAILURE", "ERROR"]
                # CheckRun uses 'conclusion' field
                return check.get("conclusion") == "FAILURE"

            any_running = any(is_check_running(check) for check in rollup)
            any_failed = any(is_check_failed(check) for check in rollup)

            # Ensure all checks have finalized conclusions before marking as complete
            def has_finalized_conclusion(check: dict) -> bool:
                """Check if a check has a finalized conclusion.

                GitHub may update the status field before the conclusion field,
                causing a race condition where checks appear "done" but don't
                have a final pass/fail state yet.
                """
                # Skip our own monitoring check
                if check.get("name") == "Monitor Organization Bot PRs":
                    return True

                typename = check.get("__typename")
                if typename == "StatusContext":
                    # StatusContext uses 'state' field - valid states are final
                    state = check.get("state")
                    return state in ["SUCCESS", "FAILURE", "ERROR"]
                # CheckRun uses 'conclusion' field - must not be None
                return check.get("conclusion") is not None

            all_finalized = all(has_finalized_conclusion(check) for check in rollup)

            if not any_running and all_finalized:
                if any_failed:
                    log_error("  Checks failed")
                    return "FAILED"
                log_success("  Checks completed successfully")
                return "COMPLETED"

            # Debug: Show why we're still waiting
            if not any_running and not all_finalized:
                log_info(
                    "    ⏳ Checks appear done but conclusions not finalized yet, "
                    "waiting..."
                )

            if attempt < max_attempts:
                time.sleep(check_interval)

        log_info(f"  ⏱ Timeout: Checks still running after {timeout_minutes} minutes")
        return "RUNNING"
