"""Tests for CLI utility functions."""

import argparse
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from aieng_bot._cli.utils import get_version, parse_pr_inputs, read_failure_logs
from aieng_bot.classifier.models import CheckFailure, PRContext


class TestGetVersion:
    """Test suite for get_version function."""

    def test_get_version_installed(self):
        """Test get_version returns version string when package is installed."""
        with patch("aieng_bot._cli.utils.version") as mock_version:
            mock_version.return_value = "1.2.3"
            result = get_version()
            assert result == "1.2.3"
            mock_version.assert_called_once_with("aieng-bot")

    def test_get_version_not_installed(self):
        """Test get_version returns 'unknown' when package is not installed."""
        from importlib.metadata import (  # noqa: PLC0415
            PackageNotFoundError,
        )

        with patch("aieng_bot._cli.utils.version") as mock_version:
            mock_version.side_effect = PackageNotFoundError()
            result = get_version()
            assert result == "unknown"

    def test_get_version_with_dev_version(self):
        """Test get_version with development version."""
        with patch("aieng_bot._cli.utils.version") as mock_version:
            mock_version.return_value = "0.4.0.dev0+g1234567"
            result = get_version()
            assert result == "0.4.0.dev0+g1234567"

    def test_get_version_with_rc_version(self):
        """Test get_version with release candidate version."""
        with patch("aieng_bot._cli.utils.version") as mock_version:
            mock_version.return_value = "2.0.0rc1"
            result = get_version()
            assert result == "2.0.0rc1"

    def test_get_version_calls_correct_package(self):
        """Test that get_version queries the correct package name."""
        with patch("aieng_bot._cli.utils.version") as mock_version:
            mock_version.return_value = "1.0.0"
            get_version()
            # Verify it queries "aieng-bot" not "aieng_bot"
            mock_version.assert_called_with("aieng-bot")


class TestReadFailureLogs:
    """Test suite for read_failure_logs function."""

    def test_read_failure_logs_from_file(self):
        """Test reading failure logs from file."""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".txt"
        ) as temp_file:
            temp_file.write("Error: Test failed\nStack trace here")
            temp_file_path = temp_file.name

        try:
            args = argparse.Namespace(
                failure_logs_file=temp_file_path, failure_logs=None
            )
            result = read_failure_logs(args)

            assert result == "Error: Test failed\nStack trace here"
        finally:
            Path(temp_file_path).unlink(missing_ok=True)

    def test_read_failure_logs_from_argument(self):
        """Test reading failure logs from command-line argument."""
        args = argparse.Namespace(
            failure_logs_file=None, failure_logs="Error from argument"
        )
        result = read_failure_logs(args)

        assert result == "Error from argument"

    def test_read_failure_logs_prefers_file_over_argument(self):
        """Test that file is preferred when both file and argument are provided."""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".txt"
        ) as temp_file:
            temp_file.write("Error from file")
            temp_file_path = temp_file.name

        try:
            args = argparse.Namespace(
                failure_logs_file=temp_file_path, failure_logs="Error from argument"
            )
            result = read_failure_logs(args)

            # Should prefer file over argument
            assert result == "Error from file"
        finally:
            Path(temp_file_path).unlink(missing_ok=True)

    def test_read_failure_logs_file_not_found(self):
        """Test reading failure logs when file doesn't exist."""
        args = argparse.Namespace(
            failure_logs_file="/nonexistent/file.txt", failure_logs=None
        )
        result = read_failure_logs(args)

        assert result == ""

    def test_read_failure_logs_neither_provided(self):
        """Test reading failure logs when neither file nor argument is provided."""
        args = argparse.Namespace(failure_logs_file=None, failure_logs=None)
        result = read_failure_logs(args)

        assert result == ""

    def test_read_failure_logs_empty_file(self):
        """Test reading failure logs from empty file."""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".txt"
        ) as temp_file:
            temp_file_path = temp_file.name
            # Write nothing - file is empty

        try:
            args = argparse.Namespace(
                failure_logs_file=temp_file_path, failure_logs=None
            )
            result = read_failure_logs(args)

            assert result == ""
        finally:
            Path(temp_file_path).unlink(missing_ok=True)

    def test_read_failure_logs_large_file(self):
        """Test reading failure logs from large file."""
        large_content = "Error line\n" * 10000
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".txt"
        ) as temp_file:
            temp_file.write(large_content)
            temp_file_path = temp_file.name

        try:
            args = argparse.Namespace(
                failure_logs_file=temp_file_path, failure_logs=None
            )
            result = read_failure_logs(args)

            assert result == large_content
            assert len(result) == len(large_content)
        finally:
            Path(temp_file_path).unlink(missing_ok=True)

    def test_read_failure_logs_with_special_characters(self):
        """Test reading failure logs with special characters and unicode."""
        special_content = (
            "Error: Test failed 💥\n"
            "Stack trace: \n"
            "  at función() línea 42\n"
            "  Encoding test: 中文 日本語 한국어"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".txt", encoding="utf-8"
        ) as temp_file:
            temp_file.write(special_content)
            temp_file_path = temp_file.name

        try:
            args = argparse.Namespace(
                failure_logs_file=temp_file_path, failure_logs=None
            )
            result = read_failure_logs(args)

            assert result == special_content
        finally:
            Path(temp_file_path).unlink(missing_ok=True)

    def test_read_failure_logs_empty_argument(self):
        """Test reading failure logs from empty string argument."""
        args = argparse.Namespace(failure_logs_file=None, failure_logs="")
        result = read_failure_logs(args)

        assert result == ""

    def test_read_failure_logs_whitespace_argument(self):
        """Test reading failure logs from whitespace-only argument."""
        args = argparse.Namespace(failure_logs_file=None, failure_logs="   \n\t  ")
        result = read_failure_logs(args)

        assert result == "   \n\t  "


class TestParsePrInputs:
    """Test suite for parse_pr_inputs function."""

    def test_parse_pr_inputs_success(self):
        """Test successful parsing of PR inputs."""
        pr_info = json.dumps(
            {
                "repo": "VectorInstitute/test-repo",
                "pr_number": 123,
                "pr_title": "Update dependencies",
                "pr_author": "app/dependabot",
                "base_ref": "main",
                "head_ref": "dependabot/npm/package-1.0.0",
            }
        )

        failed_checks = json.dumps(
            [
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
                    "conclusion": "FAILURE",
                    "workflowName": "Linting",
                    "detailsUrl": "https://github.com/.../runs/124/job/457",
                    "startedAt": "2025-01-01T00:00:00Z",
                    "completedAt": "2025-01-01T00:03:00Z",
                },
            ]
        )

        args = argparse.Namespace(pr_info=pr_info, failed_checks=failed_checks)
        pr_context, checks = parse_pr_inputs(args)

        # Verify PR context
        assert isinstance(pr_context, PRContext)
        assert pr_context.repo == "VectorInstitute/test-repo"
        assert pr_context.pr_number == 123
        assert pr_context.pr_title == "Update dependencies"
        assert pr_context.pr_author == "app/dependabot"
        assert pr_context.base_ref == "main"
        assert pr_context.head_ref == "dependabot/npm/package-1.0.0"

        # Verify failed checks
        assert len(checks) == 2
        assert all(isinstance(check, CheckFailure) for check in checks)

        assert checks[0].name == "test-check"
        assert checks[0].conclusion == "FAILURE"
        assert checks[0].workflow_name == "CI Tests"
        assert "runs/123" in checks[0].details_url

        assert checks[1].name == "lint-check"
        assert checks[1].conclusion == "FAILURE"

    def test_parse_pr_inputs_minimal_checks(self):
        """Test parsing PR inputs with minimal check information."""
        pr_info = json.dumps(
            {
                "repo": "VectorInstitute/test-repo",
                "pr_number": 123,
                "pr_title": "Test PR",
                "pr_author": "app/dependabot",
                "base_ref": "main",
                "head_ref": "test-branch",
            }
        )

        # Checks with only required fields
        failed_checks = json.dumps(
            [
                {
                    "name": "test-check",
                    "conclusion": "FAILURE",
                    # Missing optional fields
                }
            ]
        )

        args = argparse.Namespace(pr_info=pr_info, failed_checks=failed_checks)
        pr_context, checks = parse_pr_inputs(args)

        assert len(checks) == 1
        assert checks[0].name == "test-check"
        assert checks[0].conclusion == "FAILURE"
        assert checks[0].workflow_name == ""
        assert checks[0].details_url == ""
        assert checks[0].started_at == ""
        assert checks[0].completed_at == ""

    def test_parse_pr_inputs_empty_checks_list(self):
        """Test parsing PR inputs with empty checks list."""
        pr_info = json.dumps(
            {
                "repo": "VectorInstitute/test-repo",
                "pr_number": 123,
                "pr_title": "Test PR",
                "pr_author": "app/dependabot",
                "base_ref": "main",
                "head_ref": "test-branch",
            }
        )

        failed_checks = json.dumps([])

        args = argparse.Namespace(pr_info=pr_info, failed_checks=failed_checks)
        pr_context, checks = parse_pr_inputs(args)

        assert isinstance(pr_context, PRContext)
        assert len(checks) == 0

    def test_parse_pr_inputs_invalid_json_pr_info(self):
        """Test parsing PR inputs with invalid JSON in pr_info."""
        args = argparse.Namespace(
            pr_info="not valid json", failed_checks=json.dumps([])
        )

        with pytest.raises(json.JSONDecodeError):
            parse_pr_inputs(args)

    def test_parse_pr_inputs_invalid_json_failed_checks(self):
        """Test parsing PR inputs with invalid JSON in failed_checks."""
        pr_info = json.dumps(
            {
                "repo": "VectorInstitute/test-repo",
                "pr_number": 123,
                "pr_title": "Test PR",
                "pr_author": "app/dependabot",
                "base_ref": "main",
                "head_ref": "test-branch",
            }
        )

        args = argparse.Namespace(pr_info=pr_info, failed_checks="not valid json")

        with pytest.raises(json.JSONDecodeError):
            parse_pr_inputs(args)

    def test_parse_pr_inputs_missing_pr_fields(self):
        """Test parsing PR inputs with missing required PR fields."""
        pr_info = json.dumps(
            {
                "repo": "VectorInstitute/test-repo",
                "pr_number": 123,
                # Missing required fields
            }
        )

        failed_checks = json.dumps([])

        args = argparse.Namespace(pr_info=pr_info, failed_checks=failed_checks)

        with pytest.raises(KeyError):
            parse_pr_inputs(args)

    def test_parse_pr_inputs_pr_number_as_string(self):
        """Test parsing PR inputs when pr_number is a string."""
        pr_info = json.dumps(
            {
                "repo": "VectorInstitute/test-repo",
                "pr_number": "456",  # String instead of int
                "pr_title": "Test PR",
                "pr_author": "app/dependabot",
                "base_ref": "main",
                "head_ref": "test-branch",
            }
        )

        failed_checks = json.dumps([])

        args = argparse.Namespace(pr_info=pr_info, failed_checks=failed_checks)
        pr_context, checks = parse_pr_inputs(args)

        # Should convert string to int
        assert pr_context.pr_number == 456
        assert isinstance(pr_context.pr_number, int)

    def test_parse_pr_inputs_multiple_checks_same_run(self):
        """Test parsing multiple checks from the same workflow run."""
        pr_info = json.dumps(
            {
                "repo": "VectorInstitute/test-repo",
                "pr_number": 123,
                "pr_title": "Test PR",
                "pr_author": "app/dependabot",
                "base_ref": "main",
                "head_ref": "test-branch",
            }
        )

        failed_checks = json.dumps(
            [
                {
                    "name": "test-job-1",
                    "conclusion": "FAILURE",
                    "workflowName": "CI Tests",
                    "detailsUrl": "https://github.com/.../runs/123/job/456",
                    "startedAt": "2025-01-01T00:00:00Z",
                    "completedAt": "2025-01-01T00:05:00Z",
                },
                {
                    "name": "test-job-2",
                    "conclusion": "FAILURE",
                    "workflowName": "CI Tests",
                    "detailsUrl": "https://github.com/.../runs/123/job/457",
                    "startedAt": "2025-01-01T00:00:00Z",
                    "completedAt": "2025-01-01T00:05:00Z",
                },
            ]
        )

        args = argparse.Namespace(pr_info=pr_info, failed_checks=failed_checks)
        pr_context, checks = parse_pr_inputs(args)

        assert len(checks) == 2
        assert checks[0].name == "test-job-1"
        assert checks[1].name == "test-job-2"
        # Both from same run
        assert "runs/123" in checks[0].details_url
        assert "runs/123" in checks[1].details_url

    def test_parse_pr_inputs_with_special_characters(self):
        """Test parsing PR inputs with special characters in strings."""
        pr_info = json.dumps(
            {
                "repo": "VectorInstitute/test-repo",
                "pr_number": 123,
                "pr_title": "Fix bug in función() with emoji 🐛",
                "pr_author": "app/dependabot",
                "base_ref": "main",
                "head_ref": "fix/bug-with-特殊字符",
            }
        )

        failed_checks = json.dumps([])

        args = argparse.Namespace(pr_info=pr_info, failed_checks=failed_checks)
        pr_context, checks = parse_pr_inputs(args)

        assert "emoji 🐛" in pr_context.pr_title
        assert "特殊字符" in pr_context.head_ref

    def test_parse_pr_inputs_pre_commit_ci_author(self):
        """Test parsing PR inputs with pre-commit-ci bot author."""
        pr_info = json.dumps(
            {
                "repo": "VectorInstitute/test-repo",
                "pr_number": 789,
                "pr_title": "[pre-commit.ci] auto fixes",
                "pr_author": "app/pre-commit-ci",
                "base_ref": "main",
                "head_ref": "pre-commit-ci-update",
            }
        )

        failed_checks = json.dumps([])

        args = argparse.Namespace(pr_info=pr_info, failed_checks=failed_checks)
        pr_context, checks = parse_pr_inputs(args)

        assert pr_context.pr_author == "app/pre-commit-ci"
        assert "[pre-commit.ci]" in pr_context.pr_title

    def test_parse_pr_inputs_check_with_null_fields(self):
        """Test parsing checks with null values in optional fields."""
        pr_info = json.dumps(
            {
                "repo": "VectorInstitute/test-repo",
                "pr_number": 123,
                "pr_title": "Test PR",
                "pr_author": "app/dependabot",
                "base_ref": "main",
                "head_ref": "test-branch",
            }
        )

        failed_checks = json.dumps(
            [
                {
                    "name": "test-check",
                    "conclusion": "FAILURE",
                    "workflowName": None,
                    "detailsUrl": None,
                    "startedAt": None,
                    "completedAt": None,
                }
            ]
        )

        args = argparse.Namespace(pr_info=pr_info, failed_checks=failed_checks)
        pr_context, checks = parse_pr_inputs(args)

        # Should use get() with default empty strings for null values
        assert len(checks) == 1
        # None values should be converted to empty strings
        assert checks[0].workflow_name in (None, "")
        assert checks[0].details_url in (None, "")

    def test_parse_pr_inputs_preserves_check_order(self):
        """Test that parse_pr_inputs preserves the order of checks."""
        pr_info = json.dumps(
            {
                "repo": "VectorInstitute/test-repo",
                "pr_number": 123,
                "pr_title": "Test PR",
                "pr_author": "app/dependabot",
                "base_ref": "main",
                "head_ref": "test-branch",
            }
        )

        failed_checks = json.dumps(
            [
                {"name": "check-3", "conclusion": "FAILURE"},
                {"name": "check-1", "conclusion": "FAILURE"},
                {"name": "check-2", "conclusion": "FAILURE"},
            ]
        )

        args = argparse.Namespace(pr_info=pr_info, failed_checks=failed_checks)
        pr_context, checks = parse_pr_inputs(args)

        # Order should be preserved
        assert checks[0].name == "check-3"
        assert checks[1].name == "check-1"
        assert checks[2].name == "check-2"
