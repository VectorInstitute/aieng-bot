"""Tests for check waiter module."""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from aieng_bot.check_waiter import CheckStatus, CheckWaiter


@pytest.fixture
def waiter():
    """Create a CheckWaiter instance for testing."""
    return CheckWaiter(
        repo="VectorInstitute/test-repo",
        pr_number=123,
        gh_token="test-token",
        max_wait_seconds=60,
        check_interval_seconds=10,
    )


class TestCheckStatus:
    """Test suite for CheckStatus enum."""

    def test_enum_values(self):
        """Test CheckStatus enum values."""
        assert CheckStatus.COMPLETED == "COMPLETED"
        assert CheckStatus.FAILED == "FAILED"
        assert CheckStatus.RUNNING == "RUNNING"
        assert CheckStatus.NO_CHECKS == "NO_CHECKS"
        assert CheckStatus.TIMEOUT == "TIMEOUT"


class TestCheckWaiter:
    """Test suite for CheckWaiter class."""

    def test_init(self):
        """Test CheckWaiter initialization."""
        waiter = CheckWaiter(
            repo="VectorInstitute/test-repo",
            pr_number=123,
            gh_token="test-token",
            max_wait_seconds=120,
            check_interval_seconds=30,
        )
        assert waiter.repo == "VectorInstitute/test-repo"
        assert waiter.pr_number == 123
        assert waiter.gh_token == "test-token"
        assert waiter.max_wait_seconds == 120
        assert waiter.check_interval_seconds == 30
        assert waiter.max_attempts == 4  # 120 / 30

    def test_init_defaults(self):
        """Test CheckWaiter initialization with defaults."""
        waiter = CheckWaiter(
            repo="VectorInstitute/test-repo",
            pr_number=123,
            gh_token="test-token",
        )
        assert waiter.max_wait_seconds == 900
        assert waiter.check_interval_seconds == 30
        assert waiter.max_attempts == 30  # 900 / 30

    def test_analyze_checks_no_checks(self, waiter):
        """Test analyzing checks when list is empty."""
        status = waiter._analyze_checks([])
        assert status == CheckStatus.NO_CHECKS

    def test_analyze_checks_all_null(self, waiter):
        """Test analyzing checks when all have null status and conclusion."""
        checks = [
            {"status": None, "conclusion": None},
            {"status": None, "conclusion": None},
        ]
        status = waiter._analyze_checks(checks)
        assert status == CheckStatus.NO_CHECKS

    def test_analyze_checks_stale_check_filtered(self, waiter):
        """Test that stale checks (status=null, conclusion=null) are filtered out."""
        checks = [
            {"status": "COMPLETED", "conclusion": "SUCCESS"},
            {"status": None, "conclusion": None},  # Stale check - should be filtered
        ]
        status = waiter._analyze_checks(checks)
        assert status == CheckStatus.COMPLETED

    def test_analyze_checks_running(self, waiter):
        """Test analyzing checks when some are running."""
        checks = [
            {"status": "COMPLETED", "conclusion": "SUCCESS"},
            {"status": "IN_PROGRESS", "conclusion": None},
        ]
        status = waiter._analyze_checks(checks)
        assert status == CheckStatus.RUNNING

    def test_analyze_checks_queued(self, waiter):
        """Test analyzing checks when some are queued."""
        checks = [
            {"status": "COMPLETED", "conclusion": "SUCCESS"},
            {"status": "QUEUED", "conclusion": None},
        ]
        status = waiter._analyze_checks(checks)
        assert status == CheckStatus.RUNNING

    def test_analyze_checks_pending(self, waiter):
        """Test analyzing checks when some are pending."""
        checks = [
            {"status": "COMPLETED", "conclusion": "SUCCESS"},
            {"status": "PENDING", "conclusion": None},
        ]
        status = waiter._analyze_checks(checks)
        assert status == CheckStatus.RUNNING

    def test_analyze_checks_failed(self, waiter):
        """Test analyzing checks when some have failed."""
        checks = [
            {"status": "COMPLETED", "conclusion": "SUCCESS"},
            {"status": "COMPLETED", "conclusion": "FAILURE"},
        ]
        status = waiter._analyze_checks(checks)
        assert status == CheckStatus.FAILED

    def test_analyze_checks_completed(self, waiter):
        """Test analyzing checks when all are completed successfully."""
        checks = [
            {"status": "COMPLETED", "conclusion": "SUCCESS"},
            {"status": "COMPLETED", "conclusion": "SUCCESS"},
        ]
        status = waiter._analyze_checks(checks)
        assert status == CheckStatus.COMPLETED

    def test_analyze_checks_mixed_stale_and_valid(self, waiter):
        """Test analyzing checks with mix of stale and valid checks."""
        checks = [
            {"status": None, "conclusion": None},  # Stale
            {"status": "COMPLETED", "conclusion": "SUCCESS"},  # Valid
            {"status": None, "conclusion": None},  # Stale
            {"status": "COMPLETED", "conclusion": "SUCCESS"},  # Valid
        ]
        status = waiter._analyze_checks(checks)
        assert status == CheckStatus.COMPLETED

    @patch("subprocess.run")
    def test_get_check_status_success(self, mock_run, waiter):
        """Test successful check status retrieval."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(
            {"statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}]}
        )
        mock_run.return_value = mock_result

        status = waiter.get_check_status()

        assert status == CheckStatus.COMPLETED
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_get_check_status_api_error(self, mock_run, waiter):
        """Test check status retrieval with API error."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "gh", stderr="API error"
        )

        with pytest.raises(RuntimeError, match="Failed to get check status"):
            waiter.get_check_status()

    @patch("subprocess.run")
    def test_get_check_status_json_error(self, mock_run, waiter):
        """Test check status retrieval with invalid JSON."""
        mock_result = MagicMock()
        mock_result.stdout = "invalid json"
        mock_run.return_value = mock_result

        with pytest.raises(RuntimeError, match="Failed to parse check status JSON"):
            waiter.get_check_status()

    @patch("subprocess.run")
    def test_get_check_status_no_rollup(self, mock_run, waiter):
        """Test check status when no rollup data."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"statusCheckRollup": None})
        mock_run.return_value = mock_result

        status = waiter.get_check_status()

        assert status == CheckStatus.NO_CHECKS

    @patch.object(CheckWaiter, "get_check_status")
    @patch("time.sleep")
    def test_wait_completed_immediately(self, mock_sleep, mock_get_status, waiter):
        """Test waiting when checks complete immediately."""
        mock_get_status.return_value = CheckStatus.COMPLETED

        result = waiter.wait()

        assert result.status == CheckStatus.COMPLETED
        assert result.attempts == 1
        assert result.elapsed_seconds > 0
        assert "successfully" in result.message
        mock_sleep.assert_not_called()

    @patch.object(CheckWaiter, "get_check_status")
    @patch("time.sleep")
    def test_wait_failed_immediately(self, mock_sleep, mock_get_status, waiter):
        """Test waiting when checks fail immediately."""
        mock_get_status.return_value = CheckStatus.FAILED

        result = waiter.wait()

        assert result.status == CheckStatus.FAILED
        assert result.attempts == 1
        assert result.elapsed_seconds > 0
        assert "failed" in result.message
        mock_sleep.assert_not_called()

    @patch.object(CheckWaiter, "get_check_status")
    @patch("time.sleep")
    def test_wait_running_then_completed(self, mock_sleep, mock_get_status, waiter):
        """Test waiting when checks are running then complete."""
        mock_get_status.side_effect = [
            CheckStatus.RUNNING,
            CheckStatus.RUNNING,
            CheckStatus.COMPLETED,
        ]

        result = waiter.wait()

        assert result.status == CheckStatus.COMPLETED
        assert result.attempts == 3
        assert result.elapsed_seconds > 0
        assert "successfully" in result.message
        assert mock_sleep.call_count == 2  # Sleeps between attempts

    @patch.object(CheckWaiter, "get_check_status")
    @patch("time.sleep")
    def test_wait_timeout(self, mock_sleep, mock_get_status, waiter):
        """Test waiting when timeout is reached."""
        mock_get_status.return_value = CheckStatus.RUNNING

        result = waiter.wait()

        assert result.status == CheckStatus.TIMEOUT
        assert result.attempts == 6  # 60 / 10
        assert result.elapsed_seconds > 0
        assert "timeout" in result.message

    @patch.object(CheckWaiter, "get_check_status")
    @patch("time.sleep")
    def test_wait_no_checks_early(self, mock_sleep, mock_get_status, waiter):
        """Test waiting when no checks found after early attempts."""
        # NO_CHECKS for first 2 attempts is OK, but after 5 attempts it fails
        mock_get_status.return_value = CheckStatus.NO_CHECKS

        result = waiter.wait()

        assert result.status == CheckStatus.NO_CHECKS
        assert result.attempts == 6  # Gives up after attempt 5
        assert result.elapsed_seconds > 0
        assert "No checks found" in result.message

    @patch.object(CheckWaiter, "get_check_status")
    @patch("time.sleep")
    def test_wait_no_checks_then_running(self, mock_sleep, mock_get_status, waiter):
        """Test waiting when no checks initially, then checks start."""
        mock_get_status.side_effect = [
            CheckStatus.NO_CHECKS,
            CheckStatus.NO_CHECKS,
            CheckStatus.RUNNING,
            CheckStatus.COMPLETED,
        ]

        result = waiter.wait()

        assert result.status == CheckStatus.COMPLETED
        assert result.attempts == 4
        assert result.elapsed_seconds > 0
        assert "successfully" in result.message

    @patch.object(CheckWaiter, "get_check_status")
    @patch("time.sleep")
    def test_wait_handles_exceptions(self, mock_sleep, mock_get_status, waiter, capsys):
        """Test waiting handles exceptions and continues."""
        mock_get_status.side_effect = [
            RuntimeError("API error"),
            CheckStatus.COMPLETED,
        ]

        result = waiter.wait()

        # Should continue after error and eventually succeed
        assert result.status == CheckStatus.COMPLETED
        captured = capsys.readouterr()
        assert "Warning: API error" in captured.out

    @patch.object(CheckWaiter, "get_check_status")
    @patch("time.sleep")
    def test_wait_correct_intervals(self, mock_sleep, mock_get_status, waiter):
        """Test that wait sleeps the correct intervals."""
        mock_get_status.side_effect = [
            CheckStatus.RUNNING,
            CheckStatus.RUNNING,
            CheckStatus.COMPLETED,
        ]

        waiter.wait()

        # Should sleep check_interval_seconds between attempts
        assert mock_sleep.call_count == 2
        for call in mock_sleep.call_args_list:
            assert call[0][0] == 10  # waiter.check_interval_seconds
