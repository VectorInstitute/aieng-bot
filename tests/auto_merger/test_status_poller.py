"""Tests for status poller."""

from unittest.mock import patch

import pytest

from aieng_bot.auto_merger.models import PRQueueItem, PRStatus
from aieng_bot.auto_merger.status_poller import StatusPoller

# Patch time.sleep at module level for all tests
pytestmark = pytest.mark.usefixtures("mock_sleep")


@pytest.fixture(autouse=True)
def mock_sleep():
    """Auto-mock time.sleep for all tests."""
    with patch("aieng_bot.auto_merger.status_poller.time.sleep"):
        yield


@pytest.fixture
def status_poller():
    """Create a StatusPoller instance."""
    return StatusPoller(gh_token="test_token")


@pytest.fixture
def sample_pr():
    """Sample PR for testing."""
    return PRQueueItem(
        repo="VectorInstitute/test-repo",
        pr_number=123,
        pr_title="Test PR",
        pr_author="dependabot[bot]",
        pr_url="https://github.com/VectorInstitute/test-repo/pull/123",
        status=PRStatus.WAITING_CHECKS,
        queued_at="2025-01-15T10:00:00Z",
        last_updated="2025-01-15T10:00:00Z",
    )


class TestStatusPoller:
    """Test suite for StatusPoller."""

    def test_init(self):
        """Test StatusPoller initialization."""
        poller = StatusPoller(gh_token="test_token")
        assert poller.gh_token == "test_token"

    def test_check_pr_status_with_checkrun_success(self, status_poller, sample_pr):
        """Test check_pr_status with CheckRun type checks that pass."""
        with patch.object(
            status_poller,
            "_run_gh_command",
            return_value='{"statusCheckRollup": [{"__typename": "CheckRun", "name": "CI", "conclusion": "SUCCESS", "status": "COMPLETED"}], "mergeable": "MERGEABLE"}',
        ):
            all_passed, has_failures, mergeable = status_poller.check_pr_status(
                sample_pr
            )

        assert all_passed is True
        assert has_failures is False
        assert mergeable == "MERGEABLE"

    def test_check_pr_status_with_statuscontext_success(self, status_poller, sample_pr):
        """Test check_pr_status with StatusContext type checks that pass."""
        with patch.object(
            status_poller,
            "_run_gh_command",
            return_value='{"statusCheckRollup": [{"__typename": "StatusContext", "context": "pre-commit.ci", "state": "SUCCESS"}], "mergeable": "MERGEABLE"}',
        ):
            all_passed, has_failures, mergeable = status_poller.check_pr_status(
                sample_pr
            )

        assert all_passed is True
        assert has_failures is False
        assert mergeable == "MERGEABLE"

    def test_check_pr_status_with_mixed_checks_success(self, status_poller, sample_pr):
        """Test check_pr_status with both CheckRun and StatusContext that pass."""
        with patch.object(
            status_poller,
            "_run_gh_command",
            return_value='{"statusCheckRollup": [{"__typename": "CheckRun", "name": "CI", "conclusion": "SUCCESS"}, {"__typename": "StatusContext", "context": "pre-commit.ci", "state": "SUCCESS"}], "mergeable": "MERGEABLE"}',
        ):
            all_passed, has_failures, mergeable = status_poller.check_pr_status(
                sample_pr
            )

        assert all_passed is True
        assert has_failures is False
        assert mergeable == "MERGEABLE"

    def test_check_pr_status_with_checkrun_failure(self, status_poller, sample_pr):
        """Test check_pr_status with CheckRun that fails."""
        with patch.object(
            status_poller,
            "_run_gh_command",
            return_value='{"statusCheckRollup": [{"__typename": "CheckRun", "name": "CI", "conclusion": "FAILURE", "status": "COMPLETED"}], "mergeable": "MERGEABLE"}',
        ):
            all_passed, has_failures, mergeable = status_poller.check_pr_status(
                sample_pr
            )

        assert all_passed is False
        assert has_failures is True
        assert mergeable == "MERGEABLE"

    def test_check_pr_status_with_statuscontext_failure(self, status_poller, sample_pr):
        """Test check_pr_status with StatusContext that fails."""
        with patch.object(
            status_poller,
            "_run_gh_command",
            return_value='{"statusCheckRollup": [{"__typename": "StatusContext", "context": "pre-commit.ci", "state": "FAILURE"}], "mergeable": "MERGEABLE"}',
        ):
            all_passed, has_failures, mergeable = status_poller.check_pr_status(
                sample_pr
            )

        assert all_passed is False
        assert has_failures is True
        assert mergeable == "MERGEABLE"

    def test_check_pr_status_with_statuscontext_error(self, status_poller, sample_pr):
        """Test check_pr_status with StatusContext in ERROR state."""
        with patch.object(
            status_poller,
            "_run_gh_command",
            return_value='{"statusCheckRollup": [{"__typename": "StatusContext", "context": "pre-commit.ci", "state": "ERROR"}], "mergeable": "MERGEABLE"}',
        ):
            all_passed, has_failures, mergeable = status_poller.check_pr_status(
                sample_pr
            )

        assert all_passed is False
        assert has_failures is True
        assert mergeable == "MERGEABLE"

    def test_check_pr_status_with_neutral_checkrun(self, status_poller, sample_pr):
        """Test check_pr_status with NEUTRAL CheckRun (like CodeQL)."""
        with patch.object(
            status_poller,
            "_run_gh_command",
            return_value='{"statusCheckRollup": [{"__typename": "CheckRun", "name": "CodeQL", "conclusion": "NEUTRAL", "status": "COMPLETED"}], "mergeable": "MERGEABLE"}',
        ):
            all_passed, has_failures, mergeable = status_poller.check_pr_status(
                sample_pr
            )

        assert all_passed is True
        assert has_failures is False
        assert mergeable == "MERGEABLE"

    def test_check_pr_status_with_conflicting(self, status_poller, sample_pr):
        """Test check_pr_status with merge conflict."""
        with patch.object(
            status_poller,
            "_run_gh_command",
            return_value='{"statusCheckRollup": [{"__typename": "CheckRun", "name": "CI", "conclusion": "SUCCESS"}], "mergeable": "CONFLICTING"}',
        ):
            all_passed, has_failures, mergeable = status_poller.check_pr_status(
                sample_pr
            )

        assert all_passed is True
        assert has_failures is False
        assert mergeable == "CONFLICTING"

    def test_wait_for_checks_completion_with_statuscontext_completed(
        self, status_poller, sample_pr
    ):
        """Test wait_for_checks_completion with StatusContext that completes."""
        with patch.object(
            status_poller,
            "_run_gh_command",
            return_value='{"statusCheckRollup": [{"__typename": "StatusContext", "context": "pre-commit.ci", "state": "SUCCESS"}]}',
        ):
            result = status_poller.wait_for_checks_completion(
                sample_pr, timeout_minutes=1
            )

        assert result == "COMPLETED"

    def test_wait_for_checks_completion_with_statuscontext_failed(
        self, status_poller, sample_pr
    ):
        """Test wait_for_checks_completion with StatusContext that fails.

        Returns same failed check repeatedly to demonstrate stability,
        then returns FAILED after 60s stability threshold.
        """
        with patch.object(
            status_poller,
            "_run_gh_command",
            return_value='{"statusCheckRollup": [{"__typename": "StatusContext", "context": "pre-commit.ci", "state": "FAILURE"}]}',
        ):
            result = status_poller.wait_for_checks_completion(
                sample_pr,
                timeout_minutes=2,  # Need at least 2 minutes to reach 60s stability
            )

        assert result == "FAILED"

    def test_wait_for_checks_completion_with_statuscontext_pending(
        self, status_poller, sample_pr
    ):
        """Test wait_for_checks_completion with StatusContext in PENDING state."""
        call_count = 0

        def mock_command(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: pending
                return '{"statusCheckRollup": [{"__typename": "StatusContext", "context": "pre-commit.ci", "state": "PENDING"}]}'
            # Second call: success
            return '{"statusCheckRollup": [{"__typename": "StatusContext", "context": "pre-commit.ci", "state": "SUCCESS"}]}'

        with patch.object(status_poller, "_run_gh_command", side_effect=mock_command):
            result = status_poller.wait_for_checks_completion(
                sample_pr, timeout_minutes=1
            )

        assert result == "COMPLETED"
        assert call_count == 2

    def test_wait_for_checks_completion_with_mixed_checks(
        self, status_poller, sample_pr
    ):
        """Test wait_for_checks_completion with both CheckRun and StatusContext."""
        with patch.object(
            status_poller,
            "_run_gh_command",
            return_value='{"statusCheckRollup": [{"__typename": "CheckRun", "name": "CI", "conclusion": "SUCCESS", "status": "COMPLETED"}, {"__typename": "StatusContext", "context": "pre-commit.ci", "state": "SUCCESS"}]}',
        ):
            result = status_poller.wait_for_checks_completion(
                sample_pr, timeout_minutes=1
            )

        assert result == "COMPLETED"

    def test_wait_for_checks_completion_with_checkrun_in_progress(
        self, status_poller, sample_pr
    ):
        """Test wait_for_checks_completion with CheckRun in progress."""
        call_count = 0

        def mock_command(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: in progress
                return '{"statusCheckRollup": [{"__typename": "CheckRun", "name": "CI", "conclusion": null, "status": "IN_PROGRESS"}]}'
            # Second call: completed
            return '{"statusCheckRollup": [{"__typename": "CheckRun", "name": "CI", "conclusion": "SUCCESS", "status": "COMPLETED"}]}'

        with patch.object(status_poller, "_run_gh_command", side_effect=mock_command):
            result = status_poller.wait_for_checks_completion(
                sample_pr, timeout_minutes=1
            )

        assert result == "COMPLETED"
        assert call_count == 2

    def test_wait_for_checks_completion_no_checks(self, status_poller, sample_pr):
        """Test wait_for_checks_completion when no checks are found."""
        with patch.object(
            status_poller, "_run_gh_command", return_value='{"statusCheckRollup": []}'
        ):
            # Use 2 minutes to get at least 3 attempts (requires attempt > 2 to return NO_CHECKS)
            result = status_poller.wait_for_checks_completion(
                sample_pr, timeout_minutes=2
            )

        assert result == "NO_CHECKS"

    def test_wait_for_checks_completion_timeout(self, status_poller, sample_pr):
        """Test wait_for_checks_completion times out for running checks."""
        with patch.object(
            status_poller,
            "_run_gh_command",
            return_value='{"statusCheckRollup": [{"__typename": "StatusContext", "context": "pre-commit.ci", "state": "PENDING"}]}',
        ):
            result = status_poller.wait_for_checks_completion(
                sample_pr, timeout_minutes=1
            )

        assert result == "RUNNING"

    def test_wait_for_checks_completion_real_world_scenario(
        self, status_poller, sample_pr
    ):
        """Test with real-world check data from adrenaline PR #51."""
        # This is the actual check structure from the PR
        with patch.object(
            status_poller,
            "_run_gh_command",
            return_value='{"statusCheckRollup": [{"__typename": "CheckRun", "completedAt": "2025-12-20T19:21:45Z", "conclusion": "NEUTRAL", "detailsUrl": "https://github.com/VectorInstitute/adrenaline/runs/58618489930", "name": "CodeQL", "startedAt": "2025-12-20T19:21:44Z", "status": "COMPLETED", "workflowName": ""}, {"__typename": "StatusContext", "context": "pre-commit.ci - pr", "startedAt": "2025-12-20T19:22:58Z", "state": "SUCCESS", "targetUrl": "https://results.pre-commit.ci/run/github/846117045/1766258505.oSb695JuRzK_Fwpv9vSFTA"}]}',
        ):
            result = status_poller.wait_for_checks_completion(
                sample_pr, timeout_minutes=1
            )

        assert result == "COMPLETED"

    def test_wait_for_checks_completion_with_phantom_status_context(
        self, status_poller, sample_pr
    ):
        """Test that phantom StatusContext entries with null values are ignored.

        GitHub sometimes returns StatusContext objects with all null values
        (no name, no state, no conclusion). These should be skipped to avoid
        waiting indefinitely for them to finalize.
        """
        with patch.object(
            status_poller,
            "_run_gh_command",
            return_value='{"statusCheckRollup": [{"__typename": "CheckRun", "name": "run-code-check", "conclusion": "FAILURE", "status": "COMPLETED"}, {"__typename": "CheckRun", "name": "unit-tests", "conclusion": "SUCCESS", "status": "COMPLETED"}, {"__typename": "StatusContext", "name": null, "state": null, "conclusion": null, "status": null}]}',
        ):
            result = status_poller.wait_for_checks_completion(
                sample_pr,
                timeout_minutes=2,  # Need at least 2 minutes to reach 60s stability
            )

        # Should detect failure after stability threshold without waiting for phantom StatusContext
        assert result == "FAILED"
