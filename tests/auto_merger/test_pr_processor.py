"""Tests for PR processor."""

from unittest.mock import MagicMock, patch

import pytest

from aieng_bot_maintain.auto_merger.models import PRQueueItem, PRStatus
from aieng_bot_maintain.auto_merger.pr_processor import PRProcessor


@pytest.fixture
def pr_processor():
    """Create a PRProcessor instance with mocked dependencies."""
    mock_workflow_client = MagicMock()
    mock_status_poller = MagicMock()
    return PRProcessor(
        workflow_client=mock_workflow_client,
        status_poller=mock_status_poller,
    )


@pytest.fixture
def sample_pr():
    """Sample Dependabot PR for testing."""
    return PRQueueItem(
        repo="VectorInstitute/test-repo",
        pr_number=123,
        pr_title="Bump dependency",
        pr_author="app/dependabot",
        pr_url="https://github.com/VectorInstitute/test-repo/pull/123",
        status=PRStatus.PENDING,
        queued_at="2025-01-15T10:00:00Z",
        last_updated="2025-01-15T10:00:00Z",
    )


class TestPRProcessor:
    """Test suite for PRProcessor."""

    def test_init(self):
        """Test PRProcessor initialization."""
        mock_workflow = MagicMock()
        mock_poller = MagicMock()
        processor = PRProcessor(
            workflow_client=mock_workflow,
            status_poller=mock_poller,
        )
        assert processor.workflow_client == mock_workflow
        assert processor.status_poller == mock_poller

    @patch("time.sleep")
    def test_trigger_rebase_success_sha_change(
        self, mock_sleep, pr_processor, sample_pr
    ):
        """Test successful rebase triggering with SHA change detection."""
        initial_sha = "abc123def456abc123def456abc123def456abc1"
        new_sha = "def789ghi012def789ghi012def789ghi012def7"

        # Mock status check to show no conflicts
        pr_processor.status_poller.check_pr_status.return_value = (
            True,
            False,
            "MERGEABLE",
        )
        # Mock get_pr_head_sha to return initial SHA, then new SHA (simulating rebase)
        pr_processor.workflow_client.get_pr_head_sha.side_effect = [
            initial_sha,  # Initial SHA before rebase
            new_sha,  # New SHA after rebase (first poll)
        ]
        pr_processor.workflow_client.trigger_rebase.return_value = True
        # Mock check_latest_comment to return empty string (no messages)
        pr_processor.workflow_client.check_latest_comment.return_value = ""

        result = pr_processor._trigger_rebase(sample_pr)

        assert result is False  # False means continue processing
        assert sample_pr.status == PRStatus.REBASING
        assert sample_pr.rebase_started_at is not None
        pr_processor.status_poller.check_pr_status.assert_called_once_with(sample_pr)
        pr_processor.workflow_client.trigger_rebase.assert_called_once_with(sample_pr)
        # Should poll twice: initial check + one poll that detects SHA change
        assert pr_processor.workflow_client.get_pr_head_sha.call_count == 2
        # Should sleep 10s for polling interval, then 10s for CI to start
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(10)  # Polling interval

    @patch("time.sleep")
    def test_trigger_rebase_failure_no_sha(self, mock_sleep, pr_processor, sample_pr):
        """Test rebase triggering failure when SHA cannot be retrieved."""
        # Mock status check to show no conflicts
        pr_processor.status_poller.check_pr_status.return_value = (
            True,
            False,
            "MERGEABLE",
        )
        # Mock get_pr_head_sha to fail
        pr_processor.workflow_client.get_pr_head_sha.return_value = None

        result = pr_processor._trigger_rebase(sample_pr)

        assert result is True  # True means move to next PR
        assert sample_pr.status == PRStatus.FAILED
        assert sample_pr.error_message == "Failed to get PR head SHA"

    @patch("time.sleep")
    def test_trigger_rebase_failure_comment_failed(
        self, mock_sleep, pr_processor, sample_pr
    ):
        """Test rebase triggering failure when posting comment fails."""
        # Mock status check to show no conflicts
        pr_processor.status_poller.check_pr_status.return_value = (
            True,
            False,
            "MERGEABLE",
        )
        pr_processor.workflow_client.get_pr_head_sha.return_value = "abc123"
        pr_processor.workflow_client.trigger_rebase.return_value = False

        result = pr_processor._trigger_rebase(sample_pr)

        assert result is True  # True means move to next PR
        assert sample_pr.status == PRStatus.FAILED
        assert sample_pr.error_message == "Failed to trigger rebase"

    @patch("time.sleep")
    def test_trigger_rebase_already_up_to_date(
        self, mock_sleep, pr_processor, sample_pr
    ):
        """Test that we proceed immediately when dependabot says already up-to-date."""
        initial_sha = "abc123def456abc123def456abc123def456abc1"

        # Mock status check to show no conflicts
        pr_processor.status_poller.check_pr_status.return_value = (
            True,
            False,
            "MERGEABLE",
        )
        pr_processor.workflow_client.get_pr_head_sha.return_value = initial_sha
        pr_processor.workflow_client.trigger_rebase.return_value = True
        # Mock check_latest_comment to return up-to-date message
        pr_processor.workflow_client.check_latest_comment.return_value = (
            "Looks like this PR is already up-to-date with main!"
        )

        result = pr_processor._trigger_rebase(sample_pr)

        assert result is False  # False means continue processing
        assert sample_pr.status == PRStatus.REBASING
        pr_processor.workflow_client.check_latest_comment.assert_called_once_with(
            sample_pr
        )
        # Should only call sleep(10) once for polling interval
        mock_sleep.assert_called_once_with(10)

    @patch("time.sleep")
    def test_trigger_rebase_error_detected(self, mock_sleep, pr_processor, sample_pr):
        """Test rebase error detection from Dependabot comment."""
        initial_sha = "abc123def456abc123def456abc123def456abc1"

        pr_processor.status_poller.check_pr_status.return_value = (
            True,
            False,
            "MERGEABLE",
        )
        pr_processor.workflow_client.get_pr_head_sha.return_value = initial_sha
        pr_processor.workflow_client.trigger_rebase.return_value = True
        # Mock check_latest_comment to return error message
        pr_processor.workflow_client.check_latest_comment.return_value = (
            "Dependabot could not rebase this PR due to conflicts"
        )

        result = pr_processor._trigger_rebase(sample_pr)

        assert result is False  # Route to fix workflow
        assert sample_pr.status == PRStatus.CHECKS_FAILED
        mock_sleep.assert_called_once_with(10)

    @patch("time.sleep")
    def test_trigger_rebase_timeout(self, mock_sleep, pr_processor, sample_pr):
        """Test rebase timeout when it takes too long."""
        initial_sha = "abc123def456abc123def456abc123def456abc1"

        pr_processor.status_poller.check_pr_status.return_value = (
            True,
            False,
            "MERGEABLE",
        )
        # Mock get_pr_head_sha to always return same SHA (no rebase completion)
        pr_processor.workflow_client.get_pr_head_sha.return_value = initial_sha
        pr_processor.workflow_client.trigger_rebase.return_value = True
        # Mock check_latest_comment to return empty (no messages)
        pr_processor.workflow_client.check_latest_comment.return_value = ""

        result = pr_processor._trigger_rebase(sample_pr)

        assert result is True  # Move to next PR, will retry later
        assert sample_pr.status == PRStatus.REBASING
        # Should poll 18 times (180s timeout / 10s interval)
        assert mock_sleep.call_count == 18

    def test_trigger_rebase_skips_if_conflict(self, pr_processor, sample_pr):
        """Test that rebase is skipped if conflict detected early."""
        # Mock status check to show conflict
        pr_processor.status_poller.check_pr_status.return_value = (
            True,
            False,
            "CONFLICTING",
        )

        result = pr_processor._trigger_rebase(sample_pr)

        assert result is False  # Route to fix workflow
        assert sample_pr.status == PRStatus.CHECKS_FAILED
        # Should NOT call trigger_rebase if conflict detected
        pr_processor.workflow_client.trigger_rebase.assert_not_called()

    def test_wait_for_checks_detects_merge_conflict(self, pr_processor, sample_pr):
        """Test that merge conflicts are detected early."""
        sample_pr.status = PRStatus.REBASING
        pr_processor.status_poller.check_pr_status.return_value = (
            True,
            False,
            "CONFLICTING",
        )

        result = pr_processor._wait_for_checks(sample_pr)

        assert result is False  # Continue to fix workflow
        assert sample_pr.status == PRStatus.CHECKS_FAILED
        pr_processor.status_poller.check_pr_status.assert_called_once_with(sample_pr)
        # Should not wait for checks if conflict detected
        pr_processor.status_poller.wait_for_checks_completion.assert_not_called()

    def test_wait_for_checks_completed(self, pr_processor, sample_pr):
        """Test waiting for checks that complete successfully."""
        sample_pr.status = PRStatus.REBASING
        pr_processor.status_poller.check_pr_status.return_value = (
            True,
            False,
            "MERGEABLE",
        )
        pr_processor.status_poller.wait_for_checks_completion.return_value = "COMPLETED"

        result = pr_processor._wait_for_checks(sample_pr)

        assert result is False  # Continue to merge step
        assert sample_pr.status == PRStatus.CHECKS_PASSED

    def test_wait_for_checks_failed(self, pr_processor, sample_pr):
        """Test waiting for checks that fail."""
        sample_pr.status = PRStatus.REBASING
        pr_processor.status_poller.check_pr_status.return_value = (
            False,
            True,
            "MERGEABLE",
        )
        pr_processor.status_poller.wait_for_checks_completion.return_value = "FAILED"

        result = pr_processor._wait_for_checks(sample_pr)

        assert result is False  # Continue to fix workflow
        assert sample_pr.status == PRStatus.CHECKS_FAILED

    def test_attempt_auto_merge_success(self, pr_processor, sample_pr):
        """Test successful auto-merge."""
        sample_pr.status = PRStatus.CHECKS_PASSED
        pr_processor.status_poller.check_pr_status.return_value = (
            True,
            False,
            "MERGEABLE",
        )
        pr_processor.workflow_client.auto_merge_pr.return_value = True

        result = pr_processor._attempt_auto_merge(sample_pr)

        assert result is True  # Done with this PR
        assert sample_pr.status == PRStatus.MERGED

    def test_attempt_auto_merge_with_conflict(self, pr_processor, sample_pr):
        """Test auto-merge with merge conflict."""
        sample_pr.status = PRStatus.CHECKS_PASSED
        pr_processor.status_poller.check_pr_status.return_value = (
            True,
            False,
            "CONFLICTING",
        )

        result = pr_processor._attempt_auto_merge(sample_pr)

        assert result is False  # Route to fix workflow
        assert sample_pr.status == PRStatus.CHECKS_FAILED
        # Should not attempt merge if conflict detected
        pr_processor.workflow_client.auto_merge_pr.assert_not_called()

    def test_attempt_auto_merge_with_check_failures(self, pr_processor, sample_pr):
        """Test auto-merge with check failures."""
        sample_pr.status = PRStatus.CHECKS_PASSED
        pr_processor.status_poller.check_pr_status.return_value = (
            False,
            True,
            "MERGEABLE",
        )

        result = pr_processor._attempt_auto_merge(sample_pr)

        assert result is False  # Route to fix workflow
        assert sample_pr.status == PRStatus.CHECKS_FAILED

    def test_trigger_fix_workflow_success(self, pr_processor, sample_pr):
        """Test successful fix workflow triggering."""
        sample_pr.status = PRStatus.CHECKS_FAILED
        pr_processor.workflow_client.trigger_fix_workflow.return_value = "789"

        result = pr_processor._trigger_fix_workflow(sample_pr)

        assert result is False  # Continue to wait for fix
        assert sample_pr.status == PRStatus.FIXING
        assert sample_pr.fix_workflow_run_id == "789"

    def test_trigger_fix_workflow_failure(self, pr_processor, sample_pr):
        """Test fix workflow triggering failure."""
        sample_pr.status = PRStatus.CHECKS_FAILED
        pr_processor.workflow_client.trigger_fix_workflow.return_value = None

        result = pr_processor._trigger_fix_workflow(sample_pr)

        assert result is True  # Give up on this PR
        assert sample_pr.status == PRStatus.FAILED
        assert sample_pr.error_message == "Failed to trigger fix workflow"

    @patch("time.sleep")
    def test_wait_for_fix_completion_success(self, mock_sleep, pr_processor, sample_pr):
        """Test waiting for fix workflow that succeeds."""
        sample_pr.status = PRStatus.FIXING
        sample_pr.fix_workflow_run_id = "789"
        pr_processor.workflow_client.poll_workflow_status.return_value = "SUCCESS"
        pr_processor.status_poller.wait_for_checks_completion.return_value = "COMPLETED"

        result = pr_processor._wait_for_fix_completion(sample_pr)

        assert result is False  # Continue to merge
        assert sample_pr.status == PRStatus.CHECKS_PASSED

    def test_wait_for_fix_completion_failure(self, pr_processor, sample_pr):
        """Test waiting for fix workflow that fails."""
        sample_pr.status = PRStatus.FIXING
        sample_pr.fix_workflow_run_id = "789"
        sample_pr.attempt_count = 0
        sample_pr.max_attempts = 3
        pr_processor.workflow_client.poll_workflow_status.return_value = "FAILURE"

        result = pr_processor._wait_for_fix_completion(sample_pr)

        assert result is False  # Retry
        assert sample_pr.status == PRStatus.CHECKS_FAILED
        assert sample_pr.attempt_count == 1

    def test_wait_for_fix_completion_max_attempts(self, pr_processor, sample_pr):
        """Test fix workflow failure after max attempts."""
        sample_pr.status = PRStatus.FIXING
        sample_pr.fix_workflow_run_id = "789"
        sample_pr.attempt_count = 2
        sample_pr.max_attempts = 3
        pr_processor.workflow_client.poll_workflow_status.return_value = "FAILURE"

        # This increments attempt_count from 2 to 3 (reaches max)
        result = pr_processor._wait_for_fix_completion(sample_pr)

        assert result is True  # Give up at max attempts
        assert sample_pr.attempt_count == 3
        assert sample_pr.status == PRStatus.FAILED

    @patch("time.sleep")
    def test_process_pr_full_flow_success(self, mock_sleep, pr_processor, sample_pr):
        """Test full PR processing flow from pending to merged."""
        initial_sha = "abc123def456abc123def456abc123def456abc1"
        new_sha = "def789ghi012def789ghi012def789ghi012def7"

        # Setup mocks for successful flow
        pr_processor.workflow_client.get_pr_head_sha.side_effect = [
            initial_sha,  # Before rebase
            new_sha,  # After rebase
        ]
        pr_processor.workflow_client.trigger_rebase.return_value = True
        pr_processor.workflow_client.check_latest_comment.return_value = ""
        pr_processor.status_poller.check_pr_status.return_value = (
            True,
            False,
            "MERGEABLE",
        )
        pr_processor.status_poller.wait_for_checks_completion.return_value = "COMPLETED"
        pr_processor.workflow_client.auto_merge_pr.return_value = True

        result = pr_processor.process_pr(sample_pr)

        assert result is True  # Successfully merged
        assert sample_pr.status == PRStatus.MERGED

    @patch("time.sleep")
    def test_process_pr_with_merge_conflict(self, mock_sleep, pr_processor, sample_pr):
        """Test PR processing when merge conflict is detected."""
        initial_sha = "abc123def456abc123def456abc123def456abc1"

        # Setup mocks for conflict flow
        pr_processor.workflow_client.get_pr_head_sha.return_value = initial_sha
        pr_processor.workflow_client.trigger_rebase.return_value = True
        pr_processor.workflow_client.check_latest_comment.return_value = ""
        # First call: conflict detected, second call: after fix it's mergeable
        pr_processor.status_poller.check_pr_status.side_effect = [
            (True, False, "CONFLICTING"),  # Initial check before rebase
            (True, False, "MERGEABLE"),  # After fix workflow completes
        ]
        pr_processor.workflow_client.trigger_fix_workflow.return_value = "789"
        pr_processor.workflow_client.poll_workflow_status.return_value = "SUCCESS"
        pr_processor.status_poller.wait_for_checks_completion.return_value = "COMPLETED"
        pr_processor.workflow_client.auto_merge_pr.return_value = True

        result = pr_processor.process_pr(sample_pr)

        assert result is True  # Successfully resolved and merged
        assert sample_pr.status == PRStatus.MERGED
        # Verify fix workflow was triggered
        pr_processor.workflow_client.trigger_fix_workflow.assert_called_once()

    def test_process_pr_terminal_states(self, pr_processor, sample_pr):
        """Test that terminal states immediately return."""
        for status in [PRStatus.MERGED, PRStatus.FAILED, PRStatus.SKIPPED]:
            sample_pr.status = status
            result = pr_processor.process_pr(sample_pr)
            assert result is True
