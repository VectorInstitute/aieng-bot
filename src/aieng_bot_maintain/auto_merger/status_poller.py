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

    @staticmethod
    def _should_check_be_counted(check: dict) -> bool:
        """Check if this check should be counted in status calculations.

        Parameters
        ----------
        check : dict
            Check object from GitHub API.

        Returns
        -------
        bool
            True if check should be counted, False if it should be ignored.

        """
        # Skip phantom StatusContext entries with no state or name
        # GitHub sometimes returns incomplete StatusContext objects
        is_phantom_status_context = (
            check.get("__typename") == "StatusContext"
            and check.get("state") is None
            and check.get("name") is None
        )
        return not is_phantom_status_context

    @staticmethod
    def _is_check_running(check: dict) -> bool:
        """Check if a check is still running.

        Parameters
        ----------
        check : dict
            Check object from GitHub API.

        Returns
        -------
        bool
            True if check is running, False otherwise.

        """
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

    @staticmethod
    def _is_check_failed(check: dict) -> bool:
        """Check if a check has failed or is in a non-passing terminal state.

        Parameters
        ----------
        check : dict
            Check object from GitHub API.

        Returns
        -------
        bool
            True if check has failed, False otherwise.

        """
        typename = check.get("__typename")
        if typename == "StatusContext":
            # StatusContext uses 'state' field
            state = check.get("state")
            return state in ["FAILURE", "ERROR"]
        # CheckRun uses 'conclusion' field
        # Treat CANCELLED, TIMED_OUT, and ACTION_REQUIRED as failures
        conclusion = check.get("conclusion")
        return conclusion in [
            "FAILURE",
            "CANCELLED",
            "TIMED_OUT",
            "ACTION_REQUIRED",
        ]

    @staticmethod
    def _is_check_passed(check: dict) -> bool:
        """Check if a check has passed or is neutral.

        Parameters
        ----------
        check : dict
            Check object from GitHub API.

        Returns
        -------
        bool
            True if check has passed, False otherwise.

        """
        typename = check.get("__typename")
        if typename == "StatusContext":
            # StatusContext uses 'state' field
            state = check.get("state")
            return state in ["SUCCESS"]
        # CheckRun uses 'conclusion' field
        conclusion = check.get("conclusion")
        return conclusion in ["SUCCESS", "NEUTRAL", "SKIPPED"]

    @staticmethod
    def _has_finalized_conclusion(check: dict) -> bool:
        """Check if a check has a finalized conclusion.

        GitHub may update the status field before the conclusion field,
        causing a race condition where checks appear "done" but don't
        have a final pass/fail state yet.

        Parameters
        ----------
        check : dict
            Check object from GitHub API.

        Returns
        -------
        bool
            True if check has finalized conclusion, False otherwise.

        """
        typename = check.get("__typename")
        if typename == "StatusContext":
            # StatusContext uses 'state' field - valid states are final
            state = check.get("state")
            return state in ["SUCCESS", "FAILURE", "ERROR"]
        # CheckRun uses 'conclusion' field - must not be None
        return check.get("conclusion") is not None

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

    def _handle_no_checks(
        self, rollup: list[dict], attempt: int, check_interval: int
    ) -> CheckStatus | None:
        """Handle case when no checks are found.

        Parameters
        ----------
        rollup : list[dict]
            Raw check rollup from GitHub API.
        attempt : int
            Current attempt number.
        check_interval : int
            Seconds to wait between checks.

        Returns
        -------
        CheckStatus | None
            "NO_CHECKS" if no checks found after initial attempts, None to continue.

        """
        if not rollup:
            if attempt > 2:  # Give checks time to start
                log_warning("    No checks found")
                return "NO_CHECKS"
            time.sleep(check_interval)
            return None

        # Filter out phantom checks
        relevant_checks = [c for c in rollup if self._should_check_be_counted(c)]
        if not relevant_checks:
            if attempt > 2:
                log_warning("    No relevant checks found")
                return "NO_CHECKS"
            time.sleep(check_interval)
            return None

        # Continue with relevant checks
        return None

    def _evaluate_check_status(
        self,
        relevant_checks: list[dict],
        stable_count_duration: int,
        min_stable_duration: int,
    ) -> CheckStatus | None:
        """Evaluate status of relevant checks.

        Parameters
        ----------
        relevant_checks : list[dict]
            Filtered checks to evaluate.
        stable_count_duration : int
            How long check count has been stable (seconds).
        min_stable_duration : int
            Minimum stability duration before declaring failure (seconds).

        Returns
        -------
        CheckStatus | None
            Final status if determined, None to continue waiting.

        """
        any_running = any(self._is_check_running(c) for c in relevant_checks)
        any_failed = any(self._is_check_failed(c) for c in relevant_checks)
        all_passed = all(self._is_check_passed(c) for c in relevant_checks)
        all_finalized = all(self._has_finalized_conclusion(c) for c in relevant_checks)

        if not any_running and all_finalized:
            if any_failed:
                # Wait for check count to stabilize before declaring failure
                if stable_count_duration >= min_stable_duration:
                    log_error("  Checks failed")
                    return "FAILED"
                log_info(
                    f"    ⏳ Some checks failed, but waiting for check count to "
                    f"stabilize ({stable_count_duration}s/{min_stable_duration}s) "
                    "to ensure all checks have appeared..."
                )
            elif all_passed:
                log_success("  Checks completed successfully")
                return "COMPLETED"
            else:
                log_info("    ⏳ Checks finalized but not all passed, waiting...")
        elif not any_running and not all_finalized:
            log_info(
                "    ⏳ Checks appear done but conclusions not finalized yet, "
                "waiting..."
            )

        return None

    def wait_for_checks_completion(
        self,
        pr: PRQueueItem,
        timeout_minutes: int = 30,
    ) -> CheckStatus:
        """Wait for PR checks to complete.

        Polls every 30 seconds up to timeout_minutes.
        Similar to fix-remote-pr.yml:603-673.

        To prevent premature failure detection, we track check count stability.
        We only return "FAILED" after the check count has been stable for 60s,
        ensuring all checks have appeared in GitHub's API.

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
        min_stable_duration = 60

        # Track check count stability to ensure all checks have appeared
        last_check_count = 0
        stable_count_duration = 0

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

            # Handle no checks case
            result = self._handle_no_checks(rollup, attempt, check_interval)
            if result == "NO_CHECKS":
                return result
            if result is None and not rollup:
                continue

            # Get relevant checks (already filtered by _handle_no_checks)
            relevant_checks = [c for c in rollup if self._should_check_be_counted(c)]
            if not relevant_checks:
                continue

            # Track check count stability
            current_check_count = len(relevant_checks)
            if current_check_count == last_check_count:
                stable_count_duration += check_interval
            else:
                stable_count_duration = 0
                last_check_count = current_check_count
                log_info(
                    f"    Check count changed to {current_check_count}, "
                    "resetting stability timer"
                )

            # Evaluate check status
            status = self._evaluate_check_status(
                relevant_checks, stable_count_duration, min_stable_duration
            )
            if status:
                return status

            if attempt < max_attempts:
                time.sleep(check_interval)

        log_info(f"  ⏱ Timeout: Checks still running after {timeout_minutes} minutes")
        return "RUNNING"
