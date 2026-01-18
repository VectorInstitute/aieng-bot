"""Tests for the ActivityLogger class."""

import json
import subprocess
from unittest.mock import MagicMock, Mock, patch

import pytest

from aieng_bot.observability import ActivityLogger


@pytest.fixture
def activity_logger():
    """Create an ActivityLogger instance."""
    return ActivityLogger(
        bucket="test-bucket",
        log_path="data/test_activity_log.json",
    )


@pytest.fixture
def sample_activity_log():
    """Create a sample activity log structure."""
    return {
        "activities": [
            {
                "repo": "VectorInstitute/test-repo",
                "pr_number": 41,
                "pr_title": "Previous PR",
                "pr_author": "app/dependabot",
                "pr_url": "https://github.com/VectorInstitute/test-repo/pull/41",
                "timestamp": "2025-12-19T10:00:00Z",
                "workflow_run_id": "111111",
                "github_run_url": "https://github.com/.../actions/runs/111111",
                "status": "SUCCESS",
                "failure_type": "lint",
                "trace_path": "traces/2025/12/19/test-repo-pr-41.json",
                "fix_time_hours": 0.25,
            }
        ],
        "last_updated": "2025-12-19T10:00:00Z",
    }


class TestActivityLoggerInit:
    """Tests for ActivityLogger initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        logger = ActivityLogger()

        assert logger.bucket == "bot-dashboard-vectorinstitute"
        assert logger.log_path == "data/bot_activity_log.json"
        assert (
            logger.gcs_uri
            == "gs://bot-dashboard-vectorinstitute/data/bot_activity_log.json"
        )

    def test_init_with_custom_values(self):
        """Test initialization with custom bucket and log path."""
        logger = ActivityLogger(bucket="custom-bucket", log_path="custom/path.json")

        assert logger.bucket == "custom-bucket"
        assert logger.log_path == "custom/path.json"
        assert logger.gcs_uri == "gs://custom-bucket/custom/path.json"


class TestLoadActivityLog:
    """Tests for _load_activity_log method."""

    def test_load_existing_log(self, activity_logger, sample_activity_log):
        """Test loading an existing activity log."""
        mock_result = Mock()
        mock_result.stdout = json.dumps(sample_activity_log)

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = activity_logger._load_activity_log()

            # Verify gcloud command was called correctly
            mock_run.assert_called_once_with(
                ["gcloud", "storage", "cat", activity_logger.gcs_uri],
                capture_output=True,
                text=True,
                check=True,
            )

            # Verify returned data
            assert result == sample_activity_log
            assert len(result["activities"]) == 1
            assert result["last_updated"] == "2025-12-19T10:00:00Z"

    def test_load_nonexistent_log(self, activity_logger):
        """Test loading when log file doesn't exist."""
        with patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "gcloud"),
        ):
            result = activity_logger._load_activity_log()

            # Should return empty structure
            assert result == {"activities": [], "last_updated": None}

    def test_load_invalid_json(self, activity_logger):
        """Test loading when log contains invalid JSON."""
        mock_result = Mock()
        mock_result.stdout = "invalid json content"

        with patch("subprocess.run", return_value=mock_result):
            result = activity_logger._load_activity_log()

            # Should return empty structure
            assert result == {"activities": [], "last_updated": None}

    def test_load_empty_json(self, activity_logger):
        """Test loading when log is empty JSON object."""
        mock_result = Mock()
        mock_result.stdout = "{}"

        with patch("subprocess.run", return_value=mock_result):
            result = activity_logger._load_activity_log()

            # Should return the empty object
            assert result == {}


class TestSaveActivityLog:
    """Tests for _save_activity_log method."""

    def test_save_success(self, activity_logger, sample_activity_log):
        """Test successfully saving activity log."""
        mock_file_path = "/tmp/test_12345.json"

        with (
            patch("tempfile.NamedTemporaryFile") as mock_tempfile,
            patch("subprocess.run") as mock_run,
            patch("os.unlink") as mock_unlink,
        ):
            # Mock temporary file
            mock_file = MagicMock()
            mock_file.name = mock_file_path
            mock_file.__enter__ = Mock(return_value=mock_file)
            mock_file.__exit__ = Mock(return_value=False)
            mock_tempfile.return_value = mock_file

            # Test save
            result = activity_logger._save_activity_log(sample_activity_log)

            # Verify success
            assert result is True

            # Verify tempfile was created
            mock_tempfile.assert_called_once_with(
                mode="w", delete=False, suffix=".json"
            )

            # Verify gcloud upload was called
            mock_run.assert_called_once_with(
                ["gcloud", "storage", "cp", mock_file_path, activity_logger.gcs_uri],
                check=True,
                capture_output=True,
            )

            # Verify temp file was cleaned up
            mock_unlink.assert_called_once_with(mock_file_path)

    def test_save_subprocess_error(self, activity_logger, sample_activity_log):
        """Test save failure due to subprocess error."""
        mock_file_path = "/tmp/test_12345.json"

        with (
            patch("tempfile.NamedTemporaryFile") as mock_tempfile,
            patch(
                "subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "gcloud"),
            ),
        ):
            # Mock temporary file
            mock_file = MagicMock()
            mock_file.name = mock_file_path
            mock_file.__enter__ = Mock(return_value=mock_file)
            mock_file.__exit__ = Mock(return_value=False)
            mock_tempfile.return_value = mock_file

            # Test save
            result = activity_logger._save_activity_log(sample_activity_log)

            # Verify failure
            assert result is False

    def test_save_general_exception(self, activity_logger, sample_activity_log):
        """Test save failure due to general exception."""
        with patch(
            "tempfile.NamedTemporaryFile",
            side_effect=Exception("File system error"),
        ):
            # Test save
            result = activity_logger._save_activity_log(sample_activity_log)

            # Verify failure
            assert result is False


class TestLogFix:
    """Tests for log_fix method."""

    def test_log_fix_success(self, activity_logger):
        """Test logging fix activity successfully."""
        with (
            patch.object(
                activity_logger,
                "_load_activity_log",
                return_value={"activities": [], "last_updated": None},
            ) as mock_load,
            patch.object(
                activity_logger, "_save_activity_log", return_value=True
            ) as mock_save,
        ):
            result = activity_logger.log_fix(
                repo="VectorInstitute/test-repo",
                pr_number=42,
                pr_title="Bump dependency",
                pr_author="app/dependabot",
                pr_url="https://github.com/VectorInstitute/test-repo/pull/42",
                workflow_run_id="123456789",
                github_run_url="https://github.com/.../actions/runs/123456789",
                status="SUCCESS",
                failure_types=["test"],
                trace_path="traces/2025/12/19/test-repo-pr-42.json",
                fix_time_hours=0.5,
            )

            # Verify success
            assert result is True

            # Verify load was called
            mock_load.assert_called_once()

            # Verify save was called with correct data
            mock_save.assert_called_once()
            saved_data = mock_save.call_args[0][0]
            assert len(saved_data["activities"]) == 1
            activity = saved_data["activities"][0]

            assert activity["repo"] == "VectorInstitute/test-repo"
            assert activity["pr_number"] == 42
            assert activity["pr_title"] == "Bump dependency"
            assert activity["pr_author"] == "app/dependabot"
            assert activity["workflow_run_id"] == "123456789"
            assert activity["status"] == "SUCCESS"
            assert (
                activity["failure_type"] == "test"
            )  # Primary type for backward compat
            assert activity["failure_types"] == ["test"]  # Array of types
            assert activity["trace_path"] == "traces/2025/12/19/test-repo-pr-42.json"
            assert activity["fix_time_hours"] == 0.5

    def test_log_fix_all_status_types(self, activity_logger):
        """Test logging fix with different status types."""
        for status in ["SUCCESS", "FAILED"]:
            with (
                patch.object(
                    activity_logger,
                    "_load_activity_log",
                    return_value={"activities": [], "last_updated": None},
                ),
                patch.object(
                    activity_logger, "_save_activity_log", return_value=True
                ) as mock_save,
            ):
                result = activity_logger.log_fix(
                    repo="VectorInstitute/test-repo",
                    pr_number=42,
                    pr_title="Bump dependency",
                    pr_author="app/dependabot",
                    pr_url="https://github.com/VectorInstitute/test-repo/pull/42",
                    workflow_run_id="123456789",
                    github_run_url="https://github.com/.../actions/runs/123456789",
                    status=status,
                    failure_types=["lint"],
                    trace_path="traces/2025/12/19/test-repo-pr-42.json",
                    fix_time_hours=0.25,
                )

                assert result is True
                saved_data = mock_save.call_args[0][0]
                assert saved_data["activities"][0]["status"] == status

    def test_log_fix_all_failure_types(self, activity_logger):
        """Test logging fix with different failure types."""
        failure_type_list = [
            "test",
            "lint",
            "security",
            "build",
            "merge_conflict",
            "merge_only",
            "unknown",
        ]

        for ft in failure_type_list:
            with (
                patch.object(
                    activity_logger,
                    "_load_activity_log",
                    return_value={"activities": [], "last_updated": None},
                ),
                patch.object(
                    activity_logger, "_save_activity_log", return_value=True
                ) as mock_save,
            ):
                result = activity_logger.log_fix(
                    repo="VectorInstitute/test-repo",
                    pr_number=42,
                    pr_title="Bump dependency",
                    pr_author="app/dependabot",
                    pr_url="https://github.com/VectorInstitute/test-repo/pull/42",
                    workflow_run_id="123456789",
                    github_run_url="https://github.com/.../actions/runs/123456789",
                    status="SUCCESS",
                    failure_types=[ft],
                    trace_path="traces/2025/12/19/test-repo-pr-42.json",
                    fix_time_hours=0.25,
                )

                assert result is True
                saved_data = mock_save.call_args[0][0]
                assert saved_data["activities"][0]["failure_type"] == ft
                assert saved_data["activities"][0]["failure_types"] == [ft]

    def test_log_fix_appends_to_existing_log(self, activity_logger):
        """Test that fix activities are appended to existing log."""
        existing_log = {
            "activities": [
                {
                    "repo": "VectorInstitute/other-repo",
                    "pr_number": 1,
                    "pr_title": "Old PR",
                    "pr_author": "app/dependabot",
                    "pr_url": "https://github.com/VectorInstitute/other-repo/pull/1",
                    "timestamp": "2025-12-18T10:00:00Z",
                    "workflow_run_id": "111111",
                    "github_run_url": "https://github.com/.../actions/runs/111111",
                    "status": "SUCCESS",
                    "failure_type": "lint",
                    "trace_path": "traces/2025/12/18/other-repo-pr-1.json",
                    "fix_time_hours": 0.25,
                }
            ],
            "last_updated": "2025-12-18T10:00:00Z",
        }

        with (
            patch.object(
                activity_logger, "_load_activity_log", return_value=existing_log
            ),
            patch.object(
                activity_logger, "_save_activity_log", return_value=True
            ) as mock_save,
        ):
            activity_logger.log_fix(
                repo="VectorInstitute/test-repo",
                pr_number=42,
                pr_title="New PR",
                pr_author="app/dependabot",
                pr_url="https://github.com/VectorInstitute/test-repo/pull/42",
                workflow_run_id="123456789",
                github_run_url="https://github.com/.../actions/runs/123456789",
                status="SUCCESS",
                failure_types=["test"],
                trace_path="traces/2025/12/19/test-repo-pr-42.json",
                fix_time_hours=0.5,
            )

            # Verify both activities are in the log
            saved_data = mock_save.call_args[0][0]
            assert len(saved_data["activities"]) == 2
            assert saved_data["activities"][0]["pr_number"] == 1
            assert saved_data["activities"][1]["pr_number"] == 42

    def test_log_fix_save_failure(self, activity_logger):
        """Test logging when save fails."""
        with (
            patch.object(
                activity_logger,
                "_load_activity_log",
                return_value={"activities": [], "last_updated": None},
            ),
            patch.object(activity_logger, "_save_activity_log", return_value=False),
        ):
            result = activity_logger.log_fix(
                repo="VectorInstitute/test-repo",
                pr_number=42,
                pr_title="Bump dependency",
                pr_author="app/dependabot",
                pr_url="https://github.com/VectorInstitute/test-repo/pull/42",
                workflow_run_id="123456789",
                github_run_url="https://github.com/.../actions/runs/123456789",
                status="SUCCESS",
                failure_types=["test"],
                trace_path="traces/2025/12/19/test-repo-pr-42.json",
                fix_time_hours=0.5,
            )

            # Verify failure
            assert result is False
