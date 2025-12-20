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
    """Sample PR for testing."""
    return PRQueueItem(
        repo="VectorInstitute/test-repo",
        pr_number=123,
        pr_title="Bump dependency",
        pr_author="dependabot[bot]",
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
    def test_trigger_rebase_success(self, mock_sleep, pr_processor, sample_pr):
        """Test successful rebase triggering."""
        # Mock status check to show no conflicts
        pr_processor.status_poller.check_pr_status.return_value = (
            True,
            False,
            "MERGEABLE",
        )
        pr_processor.workflow_client.trigger_rebase.return_value = True

        result = pr_processor._trigger_rebase(sample_pr)

        assert result is False  # False means continue processing
        assert sample_pr.status == PRStatus.REBASING
        assert sample_pr.rebase_started_at is not None
        pr_processor.status_poller.check_pr_status.assert_called_once_with(sample_pr)
        pr_processor.workflow_client.trigger_rebase.assert_called_once_with(sample_pr)
        mock_sleep.assert_called_once_with(60)

    @patch("time.sleep")
    def test_trigger_rebase_failure(self, mock_sleep, pr_processor, sample_pr):
        """Test rebase triggering failure."""
        # Mock status check to show no conflicts
        pr_processor.status_poller.check_pr_status.return_value = (
            True,
            False,
            "MERGEABLE",
        )
        pr_processor.workflow_client.trigger_rebase.return_value = False

        result = pr_processor._trigger_rebase(sample_pr)

        assert result is True  # True means move to next PR
        assert sample_pr.status == PRStatus.FAILED
        assert sample_pr.error_message == "Failed to trigger rebase"

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
        # Setup mocks for successful flow
        pr_processor.workflow_client.trigger_rebase.return_value = True
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
        # Setup mocks for conflict flow
        pr_processor.workflow_client.trigger_rebase.return_value = True
        # First call: conflict detected, second call: after fix it's mergeable
        pr_processor.status_poller.check_pr_status.side_effect = [
            (True, False, "CONFLICTING"),  # Initial check after rebase
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
