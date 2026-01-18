"""Tests for fix CLI command helper functions."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aieng_bot._cli.commands.fix import (
    _check_environment_variables,
    _check_pr_status,
    _classify_failure,
    _cleanup_temporary_files,
    _fetch_initial_failure_logs,
    _fetch_pr_details,
    _handle_result,
    _log_activity_to_gcs,
    _prepare_agent_environment,
)
from aieng_bot.agent_fixer import AgentFixResult
from aieng_bot.classifier.models import FailureType


class TestCheckEnvironmentVariables:
    """Tests for _check_environment_variables function."""

    def test_all_vars_set(self):
        """Test when all required environment variables are set."""
        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "test-token"},
        ):
            ok, missing = _check_environment_variables()
            assert ok is True
            assert missing == []

    def test_gh_token_alternative(self):
        """Test that GH_TOKEN is accepted as alternative to GITHUB_TOKEN."""
        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "test-key", "GH_TOKEN": "test-token"},
            clear=True,
        ):
            ok, missing = _check_environment_variables()
            assert ok is True
            assert missing == []

    def test_missing_anthropic_key(self):
        """Test when ANTHROPIC_API_KEY is missing."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}, clear=True):
            ok, missing = _check_environment_variables()
            assert ok is False
            assert any("ANTHROPIC_API_KEY" in m for m in missing)

    def test_missing_github_token(self):
        """Test when both GITHUB_TOKEN and GH_TOKEN are missing."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True):
            ok, missing = _check_environment_variables()
            assert ok is False
            assert any("GITHUB_TOKEN" in m or "GH_TOKEN" in m for m in missing)

    def test_all_vars_missing(self):
        """Test when all environment variables are missing."""
        with patch.dict(os.environ, {}, clear=True):
            ok, missing = _check_environment_variables()
            assert ok is False
            assert len(missing) == 2


class TestCheckPRStatus:
    """Tests for _check_pr_status function."""

    def test_open_pr_with_failing_checks(self):
        """Test open PR with failing checks."""
        with patch("subprocess.run") as mock_run:
            # First call: get state (OPEN)
            state_response = MagicMock()
            state_response.returncode = 0
            state_response.stdout = '{"state": "OPEN"}'

            # Second call: check status (failing)
            check_response = MagicMock()
            check_response.returncode = 1  # Exit code 1 means check failed
            check_response.stdout = "some check\tfail\t..."

            mock_run.side_effect = [state_response, check_response]

            state, has_failures = _check_pr_status("owner/repo", 123, "token")

            assert state == "OPEN"
            assert has_failures is True

    def test_merged_pr(self):
        """Test already merged PR."""
        with patch("subprocess.run") as mock_run:
            state_response = MagicMock()
            state_response.returncode = 0
            state_response.stdout = '{"state": "MERGED"}'

            check_response = MagicMock()
            check_response.returncode = 0
            check_response.stdout = ""

            mock_run.side_effect = [state_response, check_response]

            state, has_failures = _check_pr_status("owner/repo", 123, "token")

            assert state == "MERGED"
            assert has_failures is False

    def test_closed_pr(self):
        """Test closed (not merged) PR."""
        with patch("subprocess.run") as mock_run:
            state_response = MagicMock()
            state_response.returncode = 0
            state_response.stdout = '{"state": "CLOSED"}'

            check_response = MagicMock()
            check_response.returncode = 0
            check_response.stdout = ""

            mock_run.side_effect = [state_response, check_response]

            state, has_failures = _check_pr_status("owner/repo", 123, "token")

            assert state == "CLOSED"
            assert has_failures is False

    def test_open_pr_with_passing_checks(self):
        """Test open PR with all checks passing."""
        with patch("subprocess.run") as mock_run:
            state_response = MagicMock()
            state_response.returncode = 0
            state_response.stdout = '{"state": "OPEN"}'

            check_response = MagicMock()
            check_response.returncode = 0
            check_response.stdout = "some check\tpass\t..."

            mock_run.side_effect = [state_response, check_response]

            state, has_failures = _check_pr_status("owner/repo", 123, "token")

            assert state == "OPEN"
            assert has_failures is False

    def test_check_with_fail_in_output(self):
        """Test that 'fail' in output text triggers has_failing_checks."""
        with patch("subprocess.run") as mock_run:
            state_response = MagicMock()
            state_response.returncode = 0
            state_response.stdout = '{"state": "OPEN"}'

            check_response = MagicMock()
            check_response.returncode = 0  # Exit code 0
            check_response.stdout = "CI\tfailure\tdetails"  # But 'fail' in output

            mock_run.side_effect = [state_response, check_response]

            state, has_failures = _check_pr_status("owner/repo", 123, "token")

            assert state == "OPEN"
            assert has_failures is True

    def test_state_command_failure(self):
        """Test when gh pr view command fails."""
        with patch("subprocess.run") as mock_run:
            state_response = MagicMock()
            state_response.returncode = 1  # Command failed
            state_response.stdout = ""

            check_response = MagicMock()
            check_response.returncode = 0
            check_response.stdout = ""

            mock_run.side_effect = [state_response, check_response]

            state, has_failures = _check_pr_status("owner/repo", 123, "token")

            assert state == "UNKNOWN"
            assert has_failures is False

    def test_without_github_token(self):
        """Test calling without github token."""
        with patch("subprocess.run") as mock_run:
            state_response = MagicMock()
            state_response.returncode = 0
            state_response.stdout = '{"state": "OPEN"}'

            check_response = MagicMock()
            check_response.returncode = 0
            check_response.stdout = ""

            mock_run.side_effect = [state_response, check_response]

            state, has_failures = _check_pr_status("owner/repo", 123, None)

            assert state == "OPEN"
            assert has_failures is False


class TestFetchPRDetails:
    """Tests for _fetch_pr_details function."""

    def test_fetch_pr_details_success(self):
        """Test successful PR details fetch."""
        mock_pr_context = MagicMock()
        mock_pr_context.pr_title = "Bump pytest"
        mock_pr_context.pr_author = "dependabot[bot]"
        mock_pr_context.head_ref = "dependabot/pip/pytest-8.0.0"
        mock_pr_context.base_ref = "main"

        with patch(
            "aieng_bot._cli.commands.fix.GitHubClient"
        ) as mock_github_client_class:
            mock_client = MagicMock()
            mock_client.get_pr_details.return_value = mock_pr_context
            mock_github_client_class.return_value = mock_client

            title, author, head, base = _fetch_pr_details("owner/repo", 123, "token")

            assert title == "Bump pytest"
            assert author == "dependabot[bot]"
            assert head == "dependabot/pip/pytest-8.0.0"
            assert base == "main"


class TestFetchInitialFailureLogs:
    """Tests for _fetch_initial_failure_logs function."""

    def test_fetch_logs_with_failed_checks(self):
        """Test fetching logs when there are failed checks."""
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch(
                "aieng_bot._cli.commands.fix.GitHubClient"
            ) as mock_github_client_class,
        ):
            mock_client = MagicMock()
            mock_client.get_failed_checks.return_value = [
                MagicMock(name="CI", conclusion="FAILURE")
            ]

            # Create a temp file that get_failure_logs returns
            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".txt"
            ) as temp_logs:
                temp_logs.write("Error: test failed")
                temp_logs_name = temp_logs.name

            mock_client.get_failure_logs.return_value = temp_logs_name
            mock_github_client_class.return_value = mock_client

            result = _fetch_initial_failure_logs("owner/repo", 123, tmp_dir, "token")

            assert result == str(Path(tmp_dir) / ".failure-logs.txt")
            assert Path(result).exists()

            # Cleanup
            Path(temp_logs_name).unlink(missing_ok=True)

    def test_fetch_logs_no_failed_checks(self):
        """Test fetching logs when there are no failed checks."""
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch(
                "aieng_bot._cli.commands.fix.GitHubClient"
            ) as mock_github_client_class,
        ):
            mock_client = MagicMock()
            mock_client.get_failed_checks.return_value = []
            mock_github_client_class.return_value = mock_client

            result = _fetch_initial_failure_logs("owner/repo", 123, tmp_dir, "token")

            assert result == str(Path(tmp_dir) / ".failure-logs.txt")
            assert Path(result).exists()

            # Should contain message about no logs
            with open(result) as f:
                content = f.read()
                assert "No failure logs" in content


class TestPrepareAgentEnvironment:
    """Tests for _prepare_agent_environment function."""

    def test_same_source_and_dest_returns_false(self):
        """Test when running from bot repo (source == dest)."""
        # When running from the bot repo itself, the function should return False
        # because source and destination .claude directories are the same

        # Get the actual bot repo path (where tests are running from)
        bot_repo_path = Path(__file__).parent.parent.parent.parent
        claude_dir = bot_repo_path / ".claude"

        if claude_dir.exists():
            # Running from bot repo - test that same path returns False
            result = _prepare_agent_environment(str(bot_repo_path))
            assert result is False  # Should not copy to self

    def test_skills_copied_to_different_directory(self):
        """Test that skills are copied when cwd is different from bot repo."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create .git/info directory for exclude file
            git_info_dir = Path(tmp_dir) / ".git" / "info"
            git_info_dir.mkdir(parents=True)

            # Run the actual function - it will copy .claude from bot repo
            result = _prepare_agent_environment(tmp_dir)

            # Should return True (skills were copied)
            assert result is True

            # Verify .claude directory was created
            assert (Path(tmp_dir) / ".claude").exists()

            # Verify git exclude was updated
            exclude_file = git_info_dir / "exclude"
            assert exclude_file.exists()
            content = exclude_file.read_text()
            assert ".claude/" in content
            assert ".pr-context.json" in content


class TestCleanupTemporaryFiles:
    """Tests for _cleanup_temporary_files function."""

    def test_cleanup_all_files(self):
        """Test cleanup of all temporary files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create files to clean up
            failure_logs = Path(tmp_dir) / ".failure-logs.txt"
            failure_logs.write_text("logs")

            skills_dir = Path(tmp_dir) / ".claude"
            skills_dir.mkdir()
            (skills_dir / "test.txt").write_text("test")

            pr_context = Path(tmp_dir) / ".pr-context.json"
            pr_context.write_text("{}")

            _cleanup_temporary_files(tmp_dir, str(failure_logs), skills_copied=True)

            assert not failure_logs.exists()
            assert not skills_dir.exists()
            assert not pr_context.exists()

    def test_cleanup_no_failure_logs(self):
        """Test cleanup when failure_logs_file is None."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / ".claude"
            skills_dir.mkdir()

            _cleanup_temporary_files(tmp_dir, None, skills_copied=True)

            assert not skills_dir.exists()

    def test_cleanup_skills_not_copied(self):
        """Test cleanup when skills were not copied."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            failure_logs = Path(tmp_dir) / ".failure-logs.txt"
            failure_logs.write_text("logs")

            # Skills dir exists but shouldn't be deleted
            skills_dir = Path(tmp_dir) / ".claude"
            skills_dir.mkdir()

            _cleanup_temporary_files(tmp_dir, str(failure_logs), skills_copied=False)

            assert not failure_logs.exists()
            assert skills_dir.exists()  # Should NOT be deleted

    def test_cleanup_handles_errors(self):
        """Test that cleanup handles errors gracefully."""
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch("os.unlink", side_effect=OSError("permission denied")),
        ):
            # Should not raise, just log warning
            _cleanup_temporary_files(tmp_dir, "/nonexistent/file.txt", False)


class TestClassifyFailure:
    """Tests for _classify_failure function."""

    def test_classify_merge_conflict(self):
        """Test classification when PR has merge conflicts."""
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch(
                "aieng_bot._cli.commands.fix.GitHubClient"
            ) as mock_github_client_class,
        ):
            mock_client = MagicMock()
            mock_client.check_merge_conflicts.return_value = True
            mock_github_client_class.return_value = mock_client

            failure_logs_file = Path(tmp_dir) / ".failure-logs.txt"
            failure_logs_file.write_text("some logs")

            result = _classify_failure(
                repo="owner/repo",
                pr_number=123,
                pr_title="Test PR",
                pr_author="testuser",
                head_ref="feature-branch",
                base_ref="main",
                failure_logs_file=str(failure_logs_file),
                github_token="token",
            )

            assert result.failure_type == FailureType.MERGE_CONFLICT
            assert result.confidence == 1.0

    def test_classify_merge_only_no_failed_checks(self):
        """Test classification when there are no failed checks."""
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch(
                "aieng_bot._cli.commands.fix.GitHubClient"
            ) as mock_github_client_class,
        ):
            mock_client = MagicMock()
            mock_client.check_merge_conflicts.return_value = False
            mock_client.get_failed_checks.return_value = []
            mock_github_client_class.return_value = mock_client

            failure_logs_file = Path(tmp_dir) / ".failure-logs.txt"
            failure_logs_file.write_text("No failure logs")

            result = _classify_failure(
                repo="owner/repo",
                pr_number=123,
                pr_title="Test PR",
                pr_author="testuser",
                head_ref="feature-branch",
                base_ref="main",
                failure_logs_file=str(failure_logs_file),
                github_token="token",
            )

            assert result.failure_type == FailureType.MERGE_ONLY
            assert result.confidence == 1.0

    def test_classify_calls_classifier_with_failed_checks(self):
        """Test that classifier is called when there are failed checks."""
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch(
                "aieng_bot._cli.commands.fix.GitHubClient"
            ) as mock_github_client_class,
            patch(
                "aieng_bot._cli.commands.fix.PRFailureClassifier"
            ) as mock_classifier_class,
        ):
            mock_client = MagicMock()
            mock_client.check_merge_conflicts.return_value = False
            mock_client.get_failed_checks.return_value = [
                MagicMock(name="lint-check", conclusion="FAILURE")
            ]
            mock_github_client_class.return_value = mock_client

            mock_result = MagicMock()
            mock_result.failure_type = FailureType.LINT
            mock_result.confidence = 0.95

            mock_classifier = MagicMock()
            mock_classifier.classify.return_value = mock_result
            mock_classifier_class.return_value = mock_classifier

            failure_logs_file = Path(tmp_dir) / ".failure-logs.txt"
            failure_logs_file.write_text("lint error logs")

            result = _classify_failure(
                repo="owner/repo",
                pr_number=123,
                pr_title="Test PR",
                pr_author="testuser",
                head_ref="feature-branch",
                base_ref="main",
                failure_logs_file=str(failure_logs_file),
                github_token="token",
            )

            assert result.failure_type == FailureType.LINT
            mock_classifier.classify.assert_called_once()


class TestHandleResult:
    """Tests for _handle_result function."""

    def test_handle_success_result(self):
        """Test handling successful result."""
        result = AgentFixResult(
            status="SUCCESS",
            trace_file="/tmp/trace.json",
            summary_file="/tmp/summary.txt",
        )

        with pytest.raises(SystemExit) as exc_info:
            _handle_result(
                result=result,
                repo="owner/repo",
                pr_number=123,
                pr_title="Test PR",
                pr_author="testuser",
                workflow_run_id="run123",
                github_run_url="https://github.com/...",
                elapsed_hours=0.5,
                failure_type="lint",
                log_to_gcs=False,
            )

        assert exc_info.value.code == 0

    def test_handle_failed_result(self):
        """Test handling failed result."""
        result = AgentFixResult(
            status="FAILED",
            trace_file="",
            summary_file="",
            error_message="Agent failed",
        )

        with pytest.raises(SystemExit) as exc_info:
            _handle_result(
                result=result,
                repo="owner/repo",
                pr_number=123,
                pr_title="Test PR",
                pr_author="testuser",
                workflow_run_id="run123",
                github_run_url="https://github.com/...",
                elapsed_hours=0.5,
                failure_type="unknown",
                log_to_gcs=False,
            )

        assert exc_info.value.code == 1

    def test_handle_result_with_gcs_logging(self):
        """Test that GCS logging is called when enabled."""
        result = AgentFixResult(
            status="SUCCESS",
            trace_file="/tmp/trace.json",
            summary_file="/tmp/summary.txt",
        )

        with (
            patch("aieng_bot._cli.commands.fix._log_activity_to_gcs") as mock_log_gcs,
            pytest.raises(SystemExit),
        ):
            _handle_result(
                result=result,
                repo="owner/repo",
                pr_number=123,
                pr_title="Test PR",
                pr_author="testuser",
                workflow_run_id="run123",
                github_run_url="https://github.com/...",
                elapsed_hours=0.5,
                failure_type="lint",
                log_to_gcs=True,
            )

            mock_log_gcs.assert_called_once()


class TestLogActivityToGCS:
    """Tests for _log_activity_to_gcs function."""

    def test_log_activity_success(self):
        """Test successful activity logging."""
        with patch("aieng_bot._cli.commands.fix.ActivityLogger") as mock_logger_class:
            mock_logger = MagicMock()
            mock_logger_class.return_value = mock_logger

            _log_activity_to_gcs(
                repo="owner/repo",
                pr_number=123,
                pr_title="Test PR",
                pr_author="testuser",
                workflow_run_id="run123",
                github_run_url="https://github.com/...",
                status="SUCCESS",
                trace_path="/tmp/trace.json",
                fix_time_hours=0.5,
                failure_type="lint",
            )

            mock_logger.log_fix.assert_called_once()
            call_kwargs = mock_logger.log_fix.call_args[1]
            assert call_kwargs["repo"] == "owner/repo"
            assert call_kwargs["pr_number"] == 123
            assert call_kwargs["status"] == "SUCCESS"
            assert call_kwargs["failure_type"] == "lint"

    def test_log_activity_handles_exception(self):
        """Test that logging errors are handled gracefully."""
        with patch("aieng_bot._cli.commands.fix.ActivityLogger") as mock_logger_class:
            mock_logger_class.side_effect = RuntimeError("GCS connection failed")

            # Should not raise
            _log_activity_to_gcs(
                repo="owner/repo",
                pr_number=123,
                pr_title="Test PR",
                pr_author="testuser",
                workflow_run_id="run123",
                github_run_url="https://github.com/...",
                status="SUCCESS",
                trace_path="/tmp/trace.json",
                fix_time_hours=0.5,
                failure_type="lint",
            )

    def test_log_activity_constructs_pr_url(self):
        """Test that PR URL is correctly constructed."""
        with patch("aieng_bot._cli.commands.fix.ActivityLogger") as mock_logger_class:
            mock_logger = MagicMock()
            mock_logger_class.return_value = mock_logger

            _log_activity_to_gcs(
                repo="VectorInstitute/test-repo",
                pr_number=456,
                pr_title="Test",
                pr_author="user",
                workflow_run_id="run",
                github_run_url="url",
                status="SUCCESS",
                trace_path="",
                fix_time_hours=0.1,
                failure_type="test",
            )

            call_kwargs = mock_logger.log_fix.call_args[1]
            assert (
                call_kwargs["pr_url"]
                == "https://github.com/VectorInstitute/test-repo/pull/456"
            )
