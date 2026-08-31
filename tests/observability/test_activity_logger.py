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
        entries_prefix="data/test_activity_entries/",
    )


@pytest.fixture
def sample_activity():
    """Create a sample activity entry."""
    return {
        "repo": "VectorInstitute/test-repo",
        "pr_number": 41,
        "pr_title": "Previous PR",
        "pr_author": "app/dependabot",
        "pr_url": "https://github.com/VectorInstitute/test-repo/pull/41",
        "timestamp": "2025-12-19T10:00:00Z",
        "workflow_run_id": "111111",
        "github_run_url": "https://github.com/.../actions/runs/111111",
        "status": "SUCCESS",
        "failure_types": ["lint"],
        "failure_type": "lint",
        "cost_usd": 0.1,
        "fix_time_hours": 0.25,
    }


@pytest.fixture
def sample_activity_log(sample_activity):
    """Create a sample combined activity log structure."""
    return {
        "activities": [sample_activity],
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
        assert logger.entries_prefix == "data/activity_entries/"
        assert (
            logger.entries_gcs_prefix
            == "gs://bot-dashboard-vectorinstitute/data/activity_entries/"
        )

    def test_init_with_custom_values(self):
        """Test initialization with custom bucket and log path."""
        logger = ActivityLogger(
            bucket="custom-bucket",
            log_path="custom/path.json",
            entries_prefix="custom/entries/",
        )

        assert logger.bucket == "custom-bucket"
        assert logger.log_path == "custom/path.json"
        assert logger.gcs_uri == "gs://custom-bucket/custom/path.json"
        assert logger.entries_prefix == "custom/entries/"
        assert logger.entries_gcs_prefix == "gs://custom-bucket/custom/entries/"


class TestGcsReadJson:
    """Tests for _gcs_read_json method."""

    def test_read_existing_file(self, activity_logger, sample_activity_log):
        """Test reading an existing JSON file from GCS."""
        mock_result = Mock()
        mock_result.stdout = json.dumps(sample_activity_log)

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = activity_logger._gcs_read_json(activity_logger.gcs_uri)

            mock_run.assert_called_once_with(
                ["gcloud", "storage", "cat", activity_logger.gcs_uri],
                capture_output=True,
                text=True,
                check=True,
            )
            assert result == sample_activity_log

    def test_read_nonexistent_file(self, activity_logger):
        """Test reading a file that does not exist (404)."""
        error = subprocess.CalledProcessError(1, "gcloud")
        error.stderr = (
            "ERROR: No URLs matched: gs://test-bucket/data/test_activity_log.json"
        )
        error.stdout = ""
        with patch("subprocess.run", side_effect=error):
            result = activity_logger._gcs_read_json(activity_logger.gcs_uri)

            assert result == {"activities": [], "last_updated": None}

    def test_read_auth_failure_returns_none(self, activity_logger):
        """Test that auth/permission failures return None (not empty dict)."""
        error = subprocess.CalledProcessError(1, "gcloud")
        error.stderr = (
            "ERROR: (gcloud.storage.cat) User does not have storage.objects.get access"
        )
        error.stdout = ""
        with patch("subprocess.run", side_effect=error):
            result = activity_logger._gcs_read_json(activity_logger.gcs_uri)

            assert result is None

    def test_read_invalid_json_returns_none(self, activity_logger):
        """Test that corrupted JSON returns None."""
        mock_result = Mock()
        mock_result.stdout = "invalid json content"

        with patch("subprocess.run", return_value=mock_result):
            result = activity_logger._gcs_read_json(activity_logger.gcs_uri)

            assert result is None


class TestWriteEntrySidecar:
    """Tests for _write_entry_sidecar method."""

    def test_write_sidecar_success(self, activity_logger, sample_activity):
        """Test successfully writing an activity sidecar."""
        mock_file_path = "/tmp/test_12345.json"

        with (
            patch("tempfile.NamedTemporaryFile") as mock_tempfile,
            patch("subprocess.run") as mock_run,
            patch("os.unlink") as mock_unlink,
        ):
            mock_file = MagicMock()
            mock_file.name = mock_file_path
            mock_file.__enter__ = Mock(return_value=mock_file)
            mock_file.__exit__ = Mock(return_value=False)
            mock_tempfile.return_value = mock_file

            result = activity_logger._write_entry_sidecar(sample_activity, "111111")

            assert result is True
            expected_gcs_uri = f"{activity_logger.entries_gcs_prefix}111111.json"
            mock_run.assert_called_once_with(
                ["gcloud", "storage", "cp", mock_file_path, expected_gcs_uri],
                check=True,
                capture_output=True,
            )
            mock_unlink.assert_called_once_with(mock_file_path)

    def test_write_sidecar_uses_workflow_run_id_as_filename(
        self, activity_logger, sample_activity
    ):
        """Test that workflow_run_id is used as the sidecar filename."""
        with (
            patch("tempfile.NamedTemporaryFile") as mock_tempfile,
            patch("subprocess.run") as mock_run,
            patch("os.unlink"),
        ):
            mock_file = MagicMock()
            mock_file.name = "/tmp/x.json"
            mock_file.__enter__ = Mock(return_value=mock_file)
            mock_file.__exit__ = Mock(return_value=False)
            mock_tempfile.return_value = mock_file

            activity_logger._write_entry_sidecar(sample_activity, "99999")

            dst = mock_run.call_args[0][0][-1]
            assert dst == f"{activity_logger.entries_gcs_prefix}99999.json"

    def test_write_sidecar_upload_failure(self, activity_logger, sample_activity):
        """Test sidecar write failure on upload error."""
        with (
            patch("tempfile.NamedTemporaryFile") as mock_tempfile,
            patch(
                "subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "gcloud"),
            ),
            patch("os.unlink"),
        ):
            mock_file = MagicMock()
            mock_file.name = "/tmp/x.json"
            mock_file.__enter__ = Mock(return_value=mock_file)
            mock_file.__exit__ = Mock(return_value=False)
            mock_tempfile.return_value = mock_file

            result = activity_logger._write_entry_sidecar(sample_activity, "111111")

            assert result is False


class TestListEntrySidecars:
    """Tests for _list_entry_sidecars method."""

    def test_list_returns_json_uris(self, activity_logger):
        """Test listing sidecar files returns only .json URIs."""
        mock_result = Mock()
        mock_result.stdout = (
            "gs://test-bucket/data/test_activity_entries/111111.json\n"
            "gs://test-bucket/data/test_activity_entries/222222.json\n"
        )

        with patch("subprocess.run", return_value=mock_result):
            result = activity_logger._list_entry_sidecars()

            assert result == [
                "gs://test-bucket/data/test_activity_entries/111111.json",
                "gs://test-bucket/data/test_activity_entries/222222.json",
            ]

    def test_list_empty_on_error(self, activity_logger):
        """Test listing returns empty list on GCS error."""
        with patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "gcloud"),
        ):
            result = activity_logger._list_entry_sidecars()

            assert result == []


class TestRebuildCombinedLog:
    """Tests for _rebuild_combined_log method."""

    def test_rebuild_merges_sidecars_and_existing(
        self, activity_logger, sample_activity
    ):
        """Test that rebuild merges sidecars with existing log entries."""
        new_activity = {**sample_activity, "pr_number": 42, "workflow_run_id": "222222"}
        existing_log = {
            "activities": [sample_activity],
            "last_updated": "2025-12-19T10:00:00Z",
        }

        with (
            patch.object(
                activity_logger,
                "_list_entry_sidecars",
                return_value=[
                    "gs://test-bucket/data/test_activity_entries/222222.json"
                ],
            ),
            patch.object(
                activity_logger,
                "_gcs_read_json",
                side_effect=[new_activity, existing_log],
            ),
            patch.object(activity_logger, "_gcs_upload", return_value=True),
            patch("tempfile.NamedTemporaryFile") as mock_tempfile,
            patch("os.unlink"),
        ):
            mock_file = MagicMock()
            mock_file.name = "/tmp/x.json"
            mock_file.__enter__ = Mock(return_value=mock_file)
            mock_file.__exit__ = Mock(return_value=False)
            mock_tempfile.return_value = mock_file

            result = activity_logger._rebuild_combined_log()

            assert result is True

    def test_rebuild_deduplicates_by_run_id(self, activity_logger, sample_activity):
        """Test that rebuild deduplicates entries with the same workflow_run_id."""
        existing_log = {
            "activities": [sample_activity],
            "last_updated": "2025-12-19T10:00:00Z",
        }

        with (
            patch.object(
                activity_logger,
                "_list_entry_sidecars",
                return_value=[
                    "gs://test-bucket/data/test_activity_entries/111111.json"
                ],
            ),
            patch.object(
                activity_logger,
                "_gcs_read_json",
                # sidecar has same workflow_run_id as existing entry
                side_effect=[sample_activity, existing_log],
            ),
            patch.object(activity_logger, "_gcs_upload", return_value=True),
            patch("tempfile.NamedTemporaryFile") as mock_tempfile,
            patch("os.unlink"),
        ):
            mock_file = MagicMock()
            mock_file.name = "/tmp/x.json"
            mock_file.__enter__ = Mock(return_value=mock_file)
            mock_file.__exit__ = Mock(return_value=False)
            mock_tempfile.return_value = mock_file

            result = activity_logger._rebuild_combined_log()
            assert result is True

    def test_rebuild_upload_failure(self, activity_logger):
        """Test rebuild returns False when upload fails."""
        with (
            patch.object(activity_logger, "_list_entry_sidecars", return_value=[]),
            patch.object(
                activity_logger,
                "_gcs_read_json",
                return_value={"activities": [], "last_updated": None},
            ),
            patch.object(activity_logger, "_gcs_upload", return_value=False),
            patch("tempfile.NamedTemporaryFile") as mock_tempfile,
            patch("os.unlink"),
        ):
            mock_file = MagicMock()
            mock_file.name = "/tmp/x.json"
            mock_file.__enter__ = Mock(return_value=mock_file)
            mock_file.__exit__ = Mock(return_value=False)
            mock_tempfile.return_value = mock_file

            result = activity_logger._rebuild_combined_log()

            assert result is False


class TestLogFix:
    """Tests for log_fix method."""

    def test_log_fix_success(self, activity_logger):
        """Test logging fix activity successfully."""
        with (
            patch.object(
                activity_logger, "_write_entry_sidecar", return_value=True
            ) as mock_sidecar,
            patch.object(
                activity_logger, "_rebuild_combined_log", return_value=True
            ) as mock_rebuild,
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
                cost_usd=0.42,
                fix_time_hours=0.5,
            )

            assert result is True

            # Sidecar is written with correct data
            mock_sidecar.assert_called_once()
            activity, run_id = mock_sidecar.call_args[0]
            assert run_id == "123456789"
            assert activity["repo"] == "VectorInstitute/test-repo"
            assert activity["pr_number"] == 42
            assert activity["status"] == "SUCCESS"
            assert activity["failure_type"] == "test"
            assert activity["failure_types"] == ["test"]
            assert activity["fix_time_hours"] == 0.5

            # Combined log is rebuilt
            mock_rebuild.assert_called_once()

    def test_log_fix_sidecar_failure_returns_false(self, activity_logger):
        """Test that sidecar write failure causes log_fix to return False."""
        with (
            patch.object(activity_logger, "_write_entry_sidecar", return_value=False),
            patch.object(
                activity_logger, "_rebuild_combined_log", return_value=True
            ) as mock_rebuild,
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
                cost_usd=0.42,
                fix_time_hours=0.5,
            )

            assert result is False
            # Rebuild should not be attempted if sidecar failed
            mock_rebuild.assert_not_called()

    def test_log_fix_rebuild_failure_still_returns_true(self, activity_logger):
        """Test that rebuild failure returns True (activity safe in sidecar)."""
        with (
            patch.object(activity_logger, "_write_entry_sidecar", return_value=True),
            patch.object(activity_logger, "_rebuild_combined_log", return_value=False),
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
                failure_types=["lint"],
                cost_usd=0.42,
                fix_time_hours=0.25,
            )

            # Sidecar is safe — still a success from caller's perspective
            assert result is True

    def test_log_fix_all_status_types(self, activity_logger):
        """Test logging fix with different status types."""
        for status in ["SUCCESS", "FAILED"]:
            with (
                patch.object(
                    activity_logger, "_write_entry_sidecar", return_value=True
                ) as mock_sidecar,
                patch.object(
                    activity_logger, "_rebuild_combined_log", return_value=True
                ),
            ):
                activity_logger.log_fix(
                    repo="VectorInstitute/test-repo",
                    pr_number=42,
                    pr_title="Bump dependency",
                    pr_author="app/dependabot",
                    pr_url="https://github.com/VectorInstitute/test-repo/pull/42",
                    workflow_run_id="123456789",
                    github_run_url="https://github.com/.../actions/runs/123456789",
                    status=status,
                    failure_types=["lint"],
                    cost_usd=0.42,
                    fix_time_hours=0.25,
                )

                activity, _ = mock_sidecar.call_args[0]
                assert activity["status"] == status

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
                    activity_logger, "_write_entry_sidecar", return_value=True
                ) as mock_sidecar,
                patch.object(
                    activity_logger, "_rebuild_combined_log", return_value=True
                ),
            ):
                activity_logger.log_fix(
                    repo="VectorInstitute/test-repo",
                    pr_number=42,
                    pr_title="Bump dependency",
                    pr_author="app/dependabot",
                    pr_url="https://github.com/VectorInstitute/test-repo/pull/42",
                    workflow_run_id="123456789",
                    github_run_url="https://github.com/.../actions/runs/123456789",
                    status="SUCCESS",
                    failure_types=[ft],
                    cost_usd=0.42,
                    fix_time_hours=0.25,
                )

                activity, _ = mock_sidecar.call_args[0]
                assert activity["failure_type"] == ft
                assert activity["failure_types"] == [ft]
