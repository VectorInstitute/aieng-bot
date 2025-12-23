"""Tests for GitHub API client."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aieng_bot.classifier.models import CheckFailure, PRContext
from aieng_bot.utils.github_client import GitHubClient


class TestGitHubClientInit:
    """Test suite for GitHubClient initialization."""

    def test_init_with_explicit_token(self):
        """Test initialization with explicit token."""
        client = GitHubClient(github_token="test-token-123")
        assert client.github_token == "test-token-123"

    @patch.dict(os.environ, {"GITHUB_TOKEN": "env-token-456"}, clear=True)
    def test_init_with_github_token_env(self):
        """Test initialization with GITHUB_TOKEN from environment."""
        client = GitHubClient()
        assert client.github_token == "env-token-456"

    @patch.dict(os.environ, {"GH_TOKEN": "gh-token-789"}, clear=True)
    def test_init_with_gh_token_env(self):
        """Test initialization with GH_TOKEN from environment."""
        client = GitHubClient()
        assert client.github_token == "gh-token-789"

    @patch.dict(
        os.environ, {"GITHUB_TOKEN": "github-token", "GH_TOKEN": "gh-token"}, clear=True
    )
    def test_init_prefers_github_token_env(self):
        """Test that GITHUB_TOKEN is preferred over GH_TOKEN."""
        client = GitHubClient()
        assert client.github_token == "github-token"

    @patch.dict(os.environ, {}, clear=True)
    def test_init_without_token_raises_error(self):
        """Test that initialization fails without token."""
        with pytest.raises(
            ValueError,
            match="GitHub token not found. Please set GITHUB_TOKEN or GH_TOKEN",
        ):
            GitHubClient()

    def test_explicit_token_overrides_env(self):
        """Test that explicit token overrides environment variables."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "env-token"}, clear=True):
            client = GitHubClient(github_token="explicit-token")
            assert client.github_token == "explicit-token"


class TestGitHubClientRunGhCommand:
    """Test suite for _run_gh_command method."""

    @patch("subprocess.run")
    def test_run_gh_command_success(self, mock_run):
        """Test successful gh command execution."""
        mock_result = MagicMock()
        mock_result.stdout = "success output"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        result = client._run_gh_command(["api", "repos/VectorInstitute/test"])

        assert result.stdout == "success output"
        assert result.returncode == 0
        mock_run.assert_called_once()

        # Verify gh CLI is called with correct arguments
        call_args = mock_run.call_args
        assert call_args[0][0] == ["gh", "api", "repos/VectorInstitute/test"]

        # Verify environment contains token
        assert call_args[1]["env"]["GH_TOKEN"] == "test-token"

    @patch("subprocess.run")
    def test_run_gh_command_with_check_false(self, mock_run):
        """Test gh command execution with check=False."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "error"
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        result = client._run_gh_command(["api", "test"], check=False)

        # Should not raise even with non-zero exit code
        assert result.returncode == 1
        assert result.stderr == "error"

    @patch("subprocess.run")
    def test_run_gh_command_timeout(self, mock_run):
        """Test gh command timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="gh api test", timeout=120)

        client = GitHubClient(github_token="test-token")
        with pytest.raises(subprocess.TimeoutExpired):
            client._run_gh_command(["api", "test"])

    @patch("subprocess.run")
    def test_run_gh_command_not_found(self, mock_run):
        """Test gh CLI not installed."""
        mock_run.side_effect = FileNotFoundError("gh: command not found")

        client = GitHubClient(github_token="test-token")
        with pytest.raises(FileNotFoundError):
            client._run_gh_command(["api", "test"])

    @patch("subprocess.run")
    def test_run_gh_command_timeout_value(self, mock_run):
        """Test that timeout is set to 120 seconds."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        client._run_gh_command(["api", "test"])

        # Verify timeout is set
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 120

    @patch("subprocess.run")
    def test_run_gh_command_preserves_environment(self, mock_run):
        """Test that existing environment variables are preserved."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        with patch.dict(os.environ, {"PATH": "/usr/bin", "HOME": "/home/user"}):
            client = GitHubClient(github_token="test-token")
            client._run_gh_command(["api", "test"])

            call_kwargs = mock_run.call_args[1]
            assert "PATH" in call_kwargs["env"]
            assert "HOME" in call_kwargs["env"]
            assert call_kwargs["env"]["GH_TOKEN"] == "test-token"


class TestGitHubClientGetPRDetails:
    """Test suite for get_pr_details method."""

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_pr_details_success(self, mock_run):
        """Test successful PR details retrieval."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(
            {
                "title": "Update dependencies",
                "author": {"login": "app/dependabot"},
                "headRefName": "dependabot/npm/package-1.0.0",
                "baseRefName": "main",
                "mergeable": "MERGEABLE",
            }
        )
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        pr_context = client.get_pr_details("VectorInstitute/test-repo", 123)

        assert isinstance(pr_context, PRContext)
        assert pr_context.repo == "VectorInstitute/test-repo"
        assert pr_context.pr_number == 123
        assert pr_context.pr_title == "Update dependencies"
        assert pr_context.pr_author == "app/dependabot"
        assert pr_context.head_ref == "dependabot/npm/package-1.0.0"
        assert pr_context.base_ref == "main"

        # Verify gh CLI was called with correct arguments
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "pr" in call_args
        assert "view" in call_args
        assert "123" in call_args
        assert "--repo" in call_args
        assert "VectorInstitute/test-repo" in call_args

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_pr_details_invalid_json(self, mock_run):
        """Test PR details with invalid JSON response."""
        mock_result = MagicMock()
        mock_result.stdout = "not valid json"
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        with pytest.raises(json.JSONDecodeError):
            client.get_pr_details("VectorInstitute/test-repo", 123)

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_pr_details_missing_fields(self, mock_run):
        """Test PR details with missing required fields."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(
            {
                "title": "Update dependencies",
                # Missing author, headRefName, etc.
            }
        )
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        with pytest.raises(KeyError):
            client.get_pr_details("VectorInstitute/test-repo", 123)

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_pr_details_api_error(self, mock_run):
        """Test PR details with API error."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "gh", stderr="API rate limit exceeded"
        )

        client = GitHubClient(github_token="test-token")
        with pytest.raises(subprocess.CalledProcessError):
            client.get_pr_details("VectorInstitute/test-repo", 123)

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_pr_details_with_pre_commit_ci_bot(self, mock_run):
        """Test PR details with pre-commit-ci bot author."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(
            {
                "title": "[pre-commit.ci] auto fixes",
                "author": {"login": "app/pre-commit-ci"},
                "headRefName": "pre-commit-ci-update",
                "baseRefName": "main",
                "mergeable": "MERGEABLE",
            }
        )
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        pr_context = client.get_pr_details("VectorInstitute/test-repo", 456)

        assert pr_context.pr_author == "app/pre-commit-ci"
        assert pr_context.pr_title == "[pre-commit.ci] auto fixes"


class TestGitHubClientGetFailedChecks:
    """Test suite for get_failed_checks method."""

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_failed_checks_success(self, mock_run):
        """Test successful failed checks retrieval."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(
            {
                "statusCheckRollup": [
                    {
                        "name": "test-check",
                        "conclusion": "FAILURE",
                        "workflowName": "CI Tests",
                        "detailsUrl": "https://github.com/.../runs/123/job/456",
                        "startedAt": "2025-01-01T00:00:00Z",
                        "completedAt": "2025-01-01T00:05:00Z",
                    },
                    {
                        "name": "lint-check",
                        "conclusion": "SUCCESS",
                        "workflowName": "Linting",
                        "detailsUrl": "https://github.com/.../runs/124/job/457",
                        "startedAt": "2025-01-01T00:00:00Z",
                        "completedAt": "2025-01-01T00:03:00Z",
                    },
                    {
                        "name": "security-check",
                        "conclusion": "FAILURE",
                        "workflowName": "Security Audit",
                        "detailsUrl": "https://github.com/.../runs/125/job/458",
                        "startedAt": "2025-01-01T00:00:00Z",
                        "completedAt": "2025-01-01T00:10:00Z",
                    },
                ]
            }
        )
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        failed_checks = client.get_failed_checks("VectorInstitute/test-repo", 123)

        assert len(failed_checks) == 2
        assert all(isinstance(check, CheckFailure) for check in failed_checks)

        # Check first failure
        assert failed_checks[0].name == "test-check"
        assert failed_checks[0].conclusion == "FAILURE"
        assert failed_checks[0].workflow_name == "CI Tests"
        assert "runs/123" in failed_checks[0].details_url

        # Check second failure
        assert failed_checks[1].name == "security-check"
        assert failed_checks[1].conclusion == "FAILURE"

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_failed_checks_no_failures(self, mock_run):
        """Test get_failed_checks when all checks pass."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(
            {
                "statusCheckRollup": [
                    {
                        "name": "test-check",
                        "conclusion": "SUCCESS",
                        "workflowName": "CI Tests",
                        "detailsUrl": "https://github.com/.../runs/123/job/456",
                        "startedAt": "2025-01-01T00:00:00Z",
                        "completedAt": "2025-01-01T00:05:00Z",
                    }
                ]
            }
        )
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        failed_checks = client.get_failed_checks("VectorInstitute/test-repo", 123)

        assert len(failed_checks) == 0

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_failed_checks_empty_rollup(self, mock_run):
        """Test get_failed_checks with empty status check rollup."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"statusCheckRollup": []})
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        failed_checks = client.get_failed_checks("VectorInstitute/test-repo", 123)

        assert len(failed_checks) == 0

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_failed_checks_no_rollup(self, mock_run):
        """Test get_failed_checks when statusCheckRollup is missing."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({})
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        failed_checks = client.get_failed_checks("VectorInstitute/test-repo", 123)

        assert len(failed_checks) == 0

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_failed_checks_missing_optional_fields(self, mock_run):
        """Test get_failed_checks with missing optional fields."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(
            {
                "statusCheckRollup": [
                    {
                        "conclusion": "FAILURE",
                        # Missing name, workflowName, detailsUrl, etc.
                    }
                ]
            }
        )
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        failed_checks = client.get_failed_checks("VectorInstitute/test-repo", 123)

        assert len(failed_checks) == 1
        assert failed_checks[0].name == ""
        assert failed_checks[0].workflow_name == ""
        assert failed_checks[0].details_url == ""


class TestGitHubClientGetFailureLogs:
    """Test suite for get_failure_logs method."""

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_failure_logs_success(self, mock_run):
        """Test successful failure logs extraction."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Error: Test failed\nAssertion error at line 42"
        mock_run.return_value = mock_result

        failed_checks = [
            CheckFailure(
                name="test-check",
                conclusion="FAILURE",
                workflow_name="CI Tests",
                details_url="https://github.com/VectorInstitute/test-repo/actions/runs/123/job/456",
                started_at="2025-01-01T00:00:00Z",
                completed_at="2025-01-01T00:05:00Z",
            )
        ]

        client = GitHubClient(github_token="test-token")
        logs_file = client.get_failure_logs("VectorInstitute/test-repo", failed_checks)

        try:
            assert Path(logs_file).exists()
            logs_content = Path(logs_file).read_text()
            assert "test-check" in logs_content
            assert "Error: Test failed" in logs_content
            assert "run 123" in logs_content
        finally:
            Path(logs_file).unlink(missing_ok=True)

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_failure_logs_multiple_checks(self, mock_run):
        """Test failure logs extraction from multiple checks."""
        mock_result1 = MagicMock()
        mock_result1.returncode = 0
        mock_result1.stdout = "Error: Test failed"

        mock_result2 = MagicMock()
        mock_result2.returncode = 0
        mock_result2.stdout = "Error: Lint failed"

        mock_run.side_effect = [mock_result1, mock_result2]

        failed_checks = [
            CheckFailure(
                name="test-check",
                conclusion="FAILURE",
                workflow_name="CI Tests",
                details_url="https://github.com/VectorInstitute/test-repo/actions/runs/123/job/456",
                started_at="2025-01-01T00:00:00Z",
                completed_at="2025-01-01T00:05:00Z",
            ),
            CheckFailure(
                name="lint-check",
                conclusion="FAILURE",
                workflow_name="Linting",
                details_url="https://github.com/VectorInstitute/test-repo/actions/runs/124/job/457",
                started_at="2025-01-01T00:00:00Z",
                completed_at="2025-01-01T00:03:00Z",
            ),
        ]

        client = GitHubClient(github_token="test-token")
        logs_file = client.get_failure_logs("VectorInstitute/test-repo", failed_checks)

        try:
            logs_content = Path(logs_file).read_text()
            assert "test-check" in logs_content
            assert "lint-check" in logs_content
            assert "Error: Test failed" in logs_content
            assert "Error: Lint failed" in logs_content
        finally:
            Path(logs_file).unlink(missing_ok=True)

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_failure_logs_deduplicates_runs(self, mock_run):
        """Test that same run ID is only fetched once."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Error: Multiple jobs failed"
        mock_run.return_value = mock_result

        # Multiple checks from the same run (different jobs)
        failed_checks = [
            CheckFailure(
                name="test-job-1",
                conclusion="FAILURE",
                workflow_name="CI Tests",
                details_url="https://github.com/VectorInstitute/test-repo/actions/runs/123/job/456",
                started_at="2025-01-01T00:00:00Z",
                completed_at="2025-01-01T00:05:00Z",
            ),
            CheckFailure(
                name="test-job-2",
                conclusion="FAILURE",
                workflow_name="CI Tests",
                details_url="https://github.com/VectorInstitute/test-repo/actions/runs/123/job/457",
                started_at="2025-01-01T00:00:00Z",
                completed_at="2025-01-01T00:05:00Z",
            ),
        ]

        client = GitHubClient(github_token="test-token")
        logs_file = client.get_failure_logs("VectorInstitute/test-repo", failed_checks)

        try:
            # Should only call gh once (deduplication)
            assert mock_run.call_count == 1
            logs_content = Path(logs_file).read_text()
            # Only one set of logs should be written
            assert logs_content.count("Error: Multiple jobs failed") == 1
        finally:
            Path(logs_file).unlink(missing_ok=True)

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_failure_logs_no_details_url(self, mock_run):
        """Test failure logs when check has no details URL."""
        failed_checks = [
            CheckFailure(
                name="test-check",
                conclusion="FAILURE",
                workflow_name="CI Tests",
                details_url="",  # Empty URL
                started_at="2025-01-01T00:00:00Z",
                completed_at="2025-01-01T00:05:00Z",
            )
        ]

        client = GitHubClient(github_token="test-token")
        logs_file = client.get_failure_logs("VectorInstitute/test-repo", failed_checks)

        try:
            logs_content = Path(logs_file).read_text()
            assert "No failure logs could be extracted" in logs_content
            # Should not call gh CLI
            mock_run.assert_not_called()
        finally:
            Path(logs_file).unlink(missing_ok=True)

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_failure_logs_invalid_url_format(self, mock_run):
        """Test failure logs with invalid URL format."""
        failed_checks = [
            CheckFailure(
                name="test-check",
                conclusion="FAILURE",
                workflow_name="CI Tests",
                details_url="https://github.com/invalid/url",  # No run ID
                started_at="2025-01-01T00:00:00Z",
                completed_at="2025-01-01T00:05:00Z",
            )
        ]

        client = GitHubClient(github_token="test-token")
        logs_file = client.get_failure_logs("VectorInstitute/test-repo", failed_checks)

        try:
            logs_content = Path(logs_file).read_text()
            assert "No failure logs could be extracted" in logs_content
            mock_run.assert_not_called()
        finally:
            Path(logs_file).unlink(missing_ok=True)

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_failure_logs_api_error(self, mock_run):
        """Test failure logs when API call fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "API rate limit exceeded"
        mock_run.return_value = mock_result

        failed_checks = [
            CheckFailure(
                name="test-check",
                conclusion="FAILURE",
                workflow_name="CI Tests",
                details_url="https://github.com/VectorInstitute/test-repo/actions/runs/123/job/456",
                started_at="2025-01-01T00:00:00Z",
                completed_at="2025-01-01T00:05:00Z",
            )
        ]

        client = GitHubClient(github_token="test-token")
        logs_file = client.get_failure_logs("VectorInstitute/test-repo", failed_checks)

        try:
            logs_content = Path(logs_file).read_text()
            assert "No failure logs could be extracted" in logs_content
        finally:
            Path(logs_file).unlink(missing_ok=True)

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_failure_logs_handles_exceptions(self, mock_run):
        """Test failure logs handles unexpected exceptions."""
        mock_run.side_effect = Exception("Unexpected error")

        failed_checks = [
            CheckFailure(
                name="test-check",
                conclusion="FAILURE",
                workflow_name="CI Tests",
                details_url="https://github.com/VectorInstitute/test-repo/actions/runs/123/job/456",
                started_at="2025-01-01T00:00:00Z",
                completed_at="2025-01-01T00:05:00Z",
            )
        ]

        client = GitHubClient(github_token="test-token")
        logs_file = client.get_failure_logs("VectorInstitute/test-repo", failed_checks)

        try:
            logs_content = Path(logs_file).read_text()
            assert "No failure logs could be extracted" in logs_content
        finally:
            Path(logs_file).unlink(missing_ok=True)

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_failure_logs_empty_checks_list(self, mock_run):
        """Test failure logs with empty checks list."""
        client = GitHubClient(github_token="test-token")
        logs_file = client.get_failure_logs("VectorInstitute/test-repo", [])

        try:
            logs_content = Path(logs_file).read_text()
            assert "No failure logs could be extracted" in logs_content
            mock_run.assert_not_called()
        finally:
            Path(logs_file).unlink(missing_ok=True)

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_failure_logs_creates_temp_file(self, mock_run):
        """Test that failure logs creates a temporary file."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Error logs"
        mock_run.return_value = mock_result

        failed_checks = [
            CheckFailure(
                name="test-check",
                conclusion="FAILURE",
                workflow_name="CI Tests",
                details_url="https://github.com/VectorInstitute/test-repo/actions/runs/123/job/456",
                started_at="2025-01-01T00:00:00Z",
                completed_at="2025-01-01T00:05:00Z",
            )
        ]

        client = GitHubClient(github_token="test-token")
        logs_file = client.get_failure_logs("VectorInstitute/test-repo", failed_checks)

        try:
            assert logs_file.startswith(tempfile.gettempdir())
            assert "failure-logs-" in logs_file
            assert logs_file.endswith(".txt")
        finally:
            Path(logs_file).unlink(missing_ok=True)

    @patch.object(GitHubClient, "_run_gh_command")
    def test_get_failure_logs_large_output(self, mock_run):
        """Test failure logs with large output."""
        # Generate large log output (5MB)
        large_logs = "Error line\n" * 100000
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = large_logs
        mock_run.return_value = mock_result

        failed_checks = [
            CheckFailure(
                name="test-check",
                conclusion="FAILURE",
                workflow_name="CI Tests",
                details_url="https://github.com/VectorInstitute/test-repo/actions/runs/123/job/456",
                started_at="2025-01-01T00:00:00Z",
                completed_at="2025-01-01T00:05:00Z",
            )
        ]

        client = GitHubClient(github_token="test-token")
        logs_file = client.get_failure_logs("VectorInstitute/test-repo", failed_checks)

        try:
            logs_content = Path(logs_file).read_text()
            # Verify all logs are written (no truncation)
            assert large_logs in logs_content
            assert len(logs_content) > len(large_logs)  # Includes headers
        finally:
            Path(logs_file).unlink(missing_ok=True)


class TestGitHubClientCheckMergeConflicts:
    """Test suite for check_merge_conflicts method."""

    @patch.object(GitHubClient, "_run_gh_command")
    def test_check_merge_conflicts_has_conflicts(self, mock_run):
        """Test checking merge conflicts when PR has conflicts."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"mergeable": "CONFLICTING"})
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        has_conflicts = client.check_merge_conflicts("VectorInstitute/test-repo", 123)

        assert has_conflicts is True

    @patch.object(GitHubClient, "_run_gh_command")
    def test_check_merge_conflicts_no_conflicts(self, mock_run):
        """Test checking merge conflicts when PR is mergeable."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"mergeable": "MERGEABLE"})
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        has_conflicts = client.check_merge_conflicts("VectorInstitute/test-repo", 123)

        assert has_conflicts is False

    @patch.object(GitHubClient, "_run_gh_command")
    def test_check_merge_conflicts_unknown_status(self, mock_run):
        """Test checking merge conflicts with unknown mergeable status."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"mergeable": "UNKNOWN"})
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        has_conflicts = client.check_merge_conflicts("VectorInstitute/test-repo", 123)

        assert has_conflicts is False

    @patch.object(GitHubClient, "_run_gh_command")
    def test_check_merge_conflicts_empty_status(self, mock_run):
        """Test checking merge conflicts with empty mergeable status."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"mergeable": ""})
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        has_conflicts = client.check_merge_conflicts("VectorInstitute/test-repo", 123)

        assert has_conflicts is False

    @patch.object(GitHubClient, "_run_gh_command")
    def test_check_merge_conflicts_missing_field(self, mock_run):
        """Test checking merge conflicts when mergeable field is missing."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({})
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        has_conflicts = client.check_merge_conflicts("VectorInstitute/test-repo", 123)

        assert has_conflicts is False

    @patch.object(GitHubClient, "_run_gh_command")
    def test_check_merge_conflicts_api_error(self, mock_run):
        """Test checking merge conflicts with API error."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "gh", stderr="API error"
        )

        client = GitHubClient(github_token="test-token")
        with pytest.raises(subprocess.CalledProcessError):
            client.check_merge_conflicts("VectorInstitute/test-repo", 123)

    @patch.object(GitHubClient, "_run_gh_command")
    def test_check_merge_conflicts_verifies_call_args(self, mock_run):
        """Test that check_merge_conflicts calls gh with correct arguments."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"mergeable": "MERGEABLE"})
        mock_run.return_value = mock_result

        client = GitHubClient(github_token="test-token")
        client.check_merge_conflicts("VectorInstitute/test-repo", 123)

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "pr" in call_args
        assert "view" in call_args
        assert "123" in call_args
        assert "--repo" in call_args
        assert "VectorInstitute/test-repo" in call_args
        assert "--json" in call_args
        assert "mergeable" in call_args
