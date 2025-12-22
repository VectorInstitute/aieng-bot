"""PR processor for handling individual PR lifecycle."""

import time
from datetime import UTC, datetime

from ..utils.logging import log_error, log_info, log_success, log_warning
from .models import PRQueueItem, PRStatus
from .status_poller import StatusPoller
from .workflow_client import WorkflowClient


class PRProcessor:
    """Process individual PRs through the queue workflow.

    Handles: rebase → wait for checks → merge or fix → wait → merge.

    Parameters
    ----------
    workflow_client : WorkflowClient
        Client for GitHub operations.
    status_poller : StatusPoller
        Client for status polling.

    Attributes
    ----------
    workflow_client : WorkflowClient
        Client for GitHub operations.
    status_poller : StatusPoller
        Client for status polling.

    """

    def __init__(
        self,
        workflow_client: WorkflowClient,
        status_poller: StatusPoller,
    ):
        """Initialize PR processor.

        Parameters
        ----------
        workflow_client : WorkflowClient
            Client for GitHub operations.
        status_poller : StatusPoller
            Client for status polling.

        """
        self.workflow_client = workflow_client
        self.status_poller = status_poller

    def process_pr(self, pr: PRQueueItem) -> bool:
        """Process a single PR through the queue workflow.

        Workflow:
        1. Trigger rebase (if not first PR in queue)
        2. Wait for checks (up to 30 minutes)
        3. If checks pass → auto-merge
        4. If checks fail → trigger fix workflow
        5. Wait for fix completion (up to 30 minutes)
        6. Verify checks pass after fix
        7. Auto-merge if successful

        Parameters
        ----------
        pr : PRQueueItem
            PR to process.

        Returns
        -------
        bool
            True if PR should advance to next, False to retry later.

        """
        log_info("=" * 60)
        log_info(f"Processing {pr.repo}#{pr.pr_number}: {pr.pr_title}")
        log_info(f"Current status: {pr.status.value}")
        log_info("=" * 60)

        # Process PR through multiple steps in single run
        max_iterations = 10
        for _iteration in range(max_iterations):
            # Handle terminal states
            if pr.status in [PRStatus.MERGED, PRStatus.FAILED, PRStatus.SKIPPED]:
                return True

            # Process current status
            should_continue = self._process_current_status(pr)
            if should_continue:
                return True  # Done with this PR

        # Should not reach here, but return False to retry later if we do
        log_warning(f"Max iterations reached for PR {pr.repo}#{pr.pr_number}")
        return False

    def _process_current_status(self, pr: PRQueueItem) -> bool:
        """Process PR based on current status.

        Parameters
        ----------
        pr : PRQueueItem
            PR to process.

        Returns
        -------
        bool
            True if PR is done (move to next), False to continue processing.

        """
        if pr.status == PRStatus.PENDING:
            return self._trigger_rebase(pr)

        if pr.status == PRStatus.REBASING:
            return self._wait_for_checks(pr)

        if pr.status == PRStatus.CHECKS_PASSED:
            return self._attempt_auto_merge(pr)

        if pr.status == PRStatus.CHECKS_FAILED:
            return self._trigger_fix_workflow(pr)

        if pr.status == PRStatus.FIXING:
            return self._wait_for_fix_completion(pr)

        # Unknown status, retry later
        return False

    def _trigger_rebase(self, pr: PRQueueItem) -> bool:
        """Trigger rebase for a pending PR and wait for completion.

        For Dependabot PRs, polls for rebase completion by monitoring:
        1. Dependabot comments ("already up-to-date", error messages)
        2. PR head SHA changes (indicates successful force-push)

        For pre-commit.ci PRs, skips rebase (not supported) and proceeds directly.

        Parameters
        ----------
        pr : PRQueueItem
            PR to rebase.

        Returns
        -------
        bool
            True to move to next PR, False to continue processing.

        """
        log_info("→ Step 1: Triggering rebase and waiting for completion")

        # Check for merge conflicts first - no point rebasing if already conflicted
        _, _, mergeable = self.status_poller.check_pr_status(pr)
        if mergeable == "CONFLICTING":
            log_warning(
                "Merge conflict detected, skipping rebase and routing to fix workflow"
            )
            pr.status = PRStatus.CHECKS_FAILED
            pr.last_updated = datetime.now(UTC).isoformat()
            return False

        # Get current head SHA before triggering rebase
        initial_head_sha = self.workflow_client.get_pr_head_sha(pr)
        if not initial_head_sha:
            pr.error_message = "Failed to get PR head SHA"
            pr.status = PRStatus.FAILED
            pr.last_updated = datetime.now(UTC).isoformat()
            return True

        log_info(f"Current head SHA: {initial_head_sha[:7]}")

        # Trigger bot-specific rebase
        if not self.workflow_client.trigger_rebase(pr):
            pr.error_message = "Failed to trigger rebase"
            pr.status = PRStatus.FAILED
            pr.last_updated = datetime.now(UTC).isoformat()
            return True

        pr.status = PRStatus.REBASING
        pr.rebase_started_at = datetime.now(UTC).isoformat()
        pr.last_updated = datetime.now(UTC).isoformat()

        # Poll for rebase completion
        # - Dependabot: polls for comments + SHA changes
        # - pre-commit.ci: polls for SHA changes (manual rebase via git)
        return self._poll_rebase_completion(pr, initial_head_sha)

    def _poll_rebase_completion(self, pr: PRQueueItem, initial_head_sha: str) -> bool:
        """Poll for rebase completion by checking comments and head SHA.

        For Dependabot: Checks bot comments for status messages
        For pre-commit.ci: Only checks for SHA changes (manual rebase)

        Parameters
        ----------
        pr : PRQueueItem
            PR being rebased.
        initial_head_sha : str
            Head SHA before rebase was triggered.

        Returns
        -------
        bool
            True to move to next PR, False to continue processing.

        """
        # Dependabot is usually fast (seconds to ~1 min), but can take longer if busy
        # Manual rebases (pre-commit.ci) should complete immediately, but we poll
        # for a bit in case CI takes time to reflect the push
        timeout_seconds = 180  # 3 minutes
        poll_interval = 10
        elapsed = 0

        log_info("Polling for rebase completion...")

        while elapsed < timeout_seconds:
            time.sleep(poll_interval)
            elapsed += poll_interval

            # For Dependabot, check for bot response comments
            if pr.pr_author == "app/dependabot":
                latest_comment = self.workflow_client.check_latest_comment(pr)

                # Case 1: Already up-to-date - no rebase needed
                if "already up-to-date" in latest_comment.lower():
                    log_success(
                        "PR already up-to-date with base branch, proceeding immediately"
                    )
                    return False  # Proceed to check monitoring

                # Case 2: PR edited by someone else - Dependabot refuses to rebase
                # This happens when the bot previously fixed the PR
                # The PR is likely already up-to-date, so proceed to checks
                edited_by_other_phrases = [
                    "edited by someone other than dependabot",
                    "can't rebase",
                    "dependabot can't rebase",
                ]
                if any(
                    phrase in latest_comment.lower()
                    for phrase in edited_by_other_phrases
                ):
                    log_warning(
                        "PR was edited by someone else, Dependabot refuses to rebase. "
                        "Proceeding to check monitoring (PR likely already up-to-date)."
                    )
                    return False  # Proceed to check monitoring

                # Case 3: Rebase failed - route to fix workflow
                rebase_error_phrases = [
                    "could not rebase",
                    "merge conflict",
                    "unable to rebase",
                    "rebase failed",
                    "failed to rebase",
                ]
                if any(
                    phrase in latest_comment.lower() for phrase in rebase_error_phrases
                ):
                    log_warning(f"Rebase failed: {latest_comment[:100]}...")
                    pr.status = PRStatus.CHECKS_FAILED
                    pr.last_updated = datetime.now(UTC).isoformat()
                    return False  # Route to fix workflow

            # Check for SHA change (works for both Dependabot and pre-commit.ci)
            current_head_sha = self.workflow_client.get_pr_head_sha(pr)
            if current_head_sha and current_head_sha != initial_head_sha:
                log_success(
                    f"Rebase completed (SHA changed: {initial_head_sha[:7]} → "
                    f"{current_head_sha[:7]})"
                )
                # Brief wait for CI to start triggering checks
                log_info("Waiting 10s for CI to trigger...")
                time.sleep(10)
                return False  # Proceed to check monitoring

            log_info(f"  Still waiting for rebase... ({elapsed}s/{timeout_seconds}s)")

        # Timeout - rebase taking too long or stuck
        log_warning(
            f"Rebase did not complete within {timeout_seconds}s. "
            "Will retry on next workflow run."
        )
        # Keep status as REBASING - next run will check if it completed
        return True  # Move to next PR, will retry on next cron run

    def _wait_for_checks(self, pr: PRQueueItem) -> bool:
        """Wait for checks to complete after rebase.

        Parameters
        ----------
        pr : PRQueueItem
            PR to monitor.

        Returns
        -------
        bool
            True to move to next PR, False to retry later.

        """
        log_info("→ Step 2: Waiting for checks to complete")
        pr.status = PRStatus.WAITING_CHECKS
        pr.last_updated = datetime.now(UTC).isoformat()

        # Check for merge conflicts early before waiting for checks
        _, _, mergeable = self.status_poller.check_pr_status(pr)
        if mergeable == "CONFLICTING":
            log_warning("Merge conflict detected, routing to fix workflow")
            pr.status = PRStatus.CHECKS_FAILED
            pr.last_updated = datetime.now(UTC).isoformat()
            return False

        check_status = self.status_poller.wait_for_checks_completion(
            pr, timeout_minutes=30
        )

        if check_status == "COMPLETED":
            pr.status = PRStatus.CHECKS_PASSED
            pr.last_updated = datetime.now(UTC).isoformat()
            return False
        if check_status == "FAILED":
            pr.status = PRStatus.CHECKS_FAILED
            pr.last_updated = datetime.now(UTC).isoformat()
            return False

        # RUNNING or NO_CHECKS
        log_warning("Checks still running or not found, will retry next run")
        return False

    def _attempt_auto_merge(self, pr: PRQueueItem) -> bool:
        """Attempt to auto-merge a PR with passing checks.

        Parameters
        ----------
        pr : PRQueueItem
            PR to merge.

        Returns
        -------
        bool
            True to move to next PR, False to retry later.

        """
        log_info("→ Step 3: Auto-merging PR")

        all_passed, has_failures, mergeable = self.status_poller.check_pr_status(pr)

        if mergeable == "MERGEABLE" and all_passed:
            if self.workflow_client.auto_merge_pr(pr):
                pr.status = PRStatus.MERGED
                pr.last_updated = datetime.now(UTC).isoformat()
                return True
            pr.error_message = "Failed to enable auto-merge"
            pr.status = PRStatus.FAILED
            pr.last_updated = datetime.now(UTC).isoformat()
            return True

        log_warning(
            f"PR not mergeable (mergeable={mergeable}, all_passed={all_passed})"
        )
        if has_failures or mergeable == "CONFLICTING":
            # Treat merge conflicts like check failures - they can be fixed
            pr.status = PRStatus.CHECKS_FAILED
            pr.last_updated = datetime.now(UTC).isoformat()
            return False

        pr.error_message = f"PR not mergeable: {mergeable}"
        pr.status = PRStatus.FAILED
        pr.last_updated = datetime.now(UTC).isoformat()
        return True

    def _trigger_fix_workflow(self, pr: PRQueueItem) -> bool:
        """Trigger fix workflow for a PR with failing checks.

        Parameters
        ----------
        pr : PRQueueItem
            PR to fix.

        Returns
        -------
        bool
            True to move to next PR, False to retry later.

        """
        log_info("→ Step 4: Triggering fix workflow")

        run_id = self.workflow_client.trigger_fix_workflow(pr)
        if not run_id:
            pr.error_message = "Failed to trigger fix workflow"
            pr.status = PRStatus.FAILED
            pr.last_updated = datetime.now(UTC).isoformat()
            return True

        pr.fix_workflow_run_id = run_id
        pr.status = PRStatus.FIXING
        pr.fix_started_at = datetime.now(UTC).isoformat()
        pr.last_updated = datetime.now(UTC).isoformat()
        return False

    def _wait_for_fix_completion(self, pr: PRQueueItem) -> bool:
        """Wait for fix workflow to complete and verify results.

        Parameters
        ----------
        pr : PRQueueItem
            PR being fixed.

        Returns
        -------
        bool
            True to move to next PR, False to retry later.

        """
        log_info("→ Step 5: Waiting for fix workflow to complete")

        if not pr.fix_workflow_run_id:
            pr.error_message = "Missing fix workflow run ID"
            pr.status = PRStatus.FAILED
            pr.last_updated = datetime.now(UTC).isoformat()
            return True

        workflow_status = self.workflow_client.poll_workflow_status(
            pr.fix_workflow_run_id,
            timeout_minutes=30,
        )

        if workflow_status == "SUCCESS":
            return self._verify_fix_success(pr)

        if workflow_status in ["FAILURE", "CANCELLED"]:
            return self._handle_fix_failure(pr, workflow_status)

        # RUNNING or UNKNOWN
        log_warning("Fix workflow still running, will check next run")
        return False

    def _verify_fix_success(self, pr: PRQueueItem) -> bool:
        """Verify that checks pass after fix workflow succeeds.

        Parameters
        ----------
        pr : PRQueueItem
            PR that was fixed.

        Returns
        -------
        bool
            True to move to next PR, False to retry later.

        """
        log_success("Fix workflow succeeded, verifying checks")
        pr.status = PRStatus.WAITING_CHECKS
        pr.last_updated = datetime.now(UTC).isoformat()

        # Give checks time to start
        time.sleep(30)

        check_status = self.status_poller.wait_for_checks_completion(
            pr, timeout_minutes=15
        )

        if check_status == "COMPLETED":
            pr.status = PRStatus.CHECKS_PASSED
            pr.last_updated = datetime.now(UTC).isoformat()
            return False

        pr.error_message = "Checks still failing after fix"
        pr.status = PRStatus.FAILED
        pr.attempt_count += 1
        pr.last_updated = datetime.now(UTC).isoformat()

        return self._check_retry_attempts(pr)

    def _handle_fix_failure(self, pr: PRQueueItem, workflow_status: str) -> bool:
        """Handle fix workflow failure or cancellation.

        Parameters
        ----------
        pr : PRQueueItem
            PR that failed to fix.
        workflow_status : str
            Workflow status (FAILURE or CANCELLED).

        Returns
        -------
        bool
            True to move to next PR, False to retry later.

        """
        pr.error_message = f"Fix workflow {workflow_status.lower()}"
        pr.status = PRStatus.FAILED
        pr.attempt_count += 1
        pr.last_updated = datetime.now(UTC).isoformat()

        return self._check_retry_attempts(pr)

    def _check_retry_attempts(self, pr: PRQueueItem) -> bool:
        """Check if PR should retry or give up based on attempt count.

        Parameters
        ----------
        pr : PRQueueItem
            PR to check.

        Returns
        -------
        bool
            True to move to next PR, False to retry later.

        """
        if pr.attempt_count < pr.max_attempts:
            log_warning(f"Attempt {pr.attempt_count}/{pr.max_attempts}, will retry")
            pr.status = PRStatus.CHECKS_FAILED
            return False
        log_error("Max attempts reached, giving up")
        return True
