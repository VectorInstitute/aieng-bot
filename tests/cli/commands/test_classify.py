"""Tests for classify CLI command."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from rich.console import Console

from aieng_bot._cli.commands.classify import (
    _check_environment_variables,
    _get_json_output,
    _handle_merge_conflict,
    _handle_no_failed_checks,
    _output_json_format,
    _output_result,
    _output_rich_format,
)
from aieng_bot._cli.main import cli
from aieng_bot.classifier.models import (
    CheckFailure,
    ClassificationResult,
    FailureType,
    PRContext,
)


class TestCheckEnvironmentVariables:
    """Test suite for _check_environment_variables function."""

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    def test_all_variables_set(self):
        """Test when all required variables are set."""
        ok, missing = _check_environment_variables()
        assert ok is True
        assert len(missing) == 0

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GH_TOKEN": "gh-token"},
        clear=True,
    )
    def test_gh_token_alternative(self):
        """Test with GH_TOKEN instead of GITHUB_TOKEN."""
        ok, missing = _check_environment_variables()
        assert ok is True
        assert len(missing) == 0

    @patch.dict(os.environ, {}, clear=True)
    def test_no_variables_set(self):
        """Test when no variables are set."""
        ok, missing = _check_environment_variables()
        assert ok is False
        assert len(missing) == 2
        assert any("ANTHROPIC_API_KEY" in m for m in missing)
        assert any("GITHUB_TOKEN" in m for m in missing)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True)
    def test_missing_github_token(self):
        """Test when only GitHub token is missing."""
        ok, missing = _check_environment_variables()
        assert ok is False
        assert len(missing) == 1
        assert "GITHUB_TOKEN" in missing[0]

    @patch.dict(os.environ, {"GITHUB_TOKEN": "gh-token"}, clear=True)
    def test_missing_anthropic_key(self):
        """Test when only Anthropic key is missing."""
        ok, missing = _check_environment_variables()
        assert ok is False
        assert len(missing) == 1
        assert "ANTHROPIC_API_KEY" in missing[0]

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "GITHUB_TOKEN": ""}, clear=True)
    def test_empty_variables(self):
        """Test with empty string values."""
        ok, missing = _check_environment_variables()
        assert ok is False
        assert len(missing) == 2


class TestGetJsonOutput:
    """Test suite for _get_json_output function."""

    def test_get_json_output_complete(self):
        """Test JSON output with complete result."""
        result = ClassificationResult(
            failure_type=FailureType.TEST,
            confidence=0.95,
            reasoning="Tests failed due to API changes",
            failed_check_names=["unit-tests", "integration-tests"],
            recommended_action="Update test assertions",
        )

        output = _get_json_output(result)

        assert output["failure_type"] == "test"
        assert output["confidence"] == 0.95
        assert output["reasoning"] == "Tests failed due to API changes"
        assert output["failed_check_names"] == ["unit-tests", "integration-tests"]
        assert output["recommended_action"] == "Update test assertions"

    def test_get_json_output_unknown(self):
        """Test JSON output with unknown failure type."""
        result = ClassificationResult(
            failure_type=FailureType.UNKNOWN,
            confidence=0.0,
            reasoning="Cannot determine failure type",
            failed_check_names=[],
            recommended_action="Manual investigation required",
        )

        output = _get_json_output(result)

        assert output["failure_type"] == "unknown"
        assert output["confidence"] == 0.0
        assert output["failed_check_names"] == []

    def test_get_json_output_all_failure_types(self):
        """Test JSON output for all failure types."""
        failure_types = [
            FailureType.TEST,
            FailureType.LINT,
            FailureType.SECURITY,
            FailureType.BUILD,
            FailureType.MERGE_CONFLICT,
            FailureType.UNKNOWN,
        ]

        for failure_type in failure_types:
            result = ClassificationResult(
                failure_type=failure_type,
                confidence=0.9,
                reasoning="Test reasoning",
                failed_check_names=["check-1"],
                recommended_action="Test action",
            )
            output = _get_json_output(result)
            assert output["failure_type"] == failure_type.value


class TestOutputJsonFormat:
    """Test suite for _output_json_format function."""

    def test_output_json_to_stdout(self):
        """Test JSON output to stdout."""
        result = ClassificationResult(
            failure_type=FailureType.LINT,
            confidence=0.85,
            reasoning="Linting errors",
            failed_check_names=["eslint"],
            recommended_action="Run linter",
        )

        console = Console()
        with patch.object(console, "print_json") as mock_print:
            _output_json_format(result, console, output_file=None)
            mock_print.assert_called_once()
            # Verify the data structure
            call_data = mock_print.call_args[1]["data"]
            assert call_data["failure_type"] == "lint"
            assert call_data["confidence"] == 0.85

    def test_output_json_to_file(self):
        """Test JSON output to file."""
        result = ClassificationResult(
            failure_type=FailureType.SECURITY,
            confidence=0.92,
            reasoning="Security vulnerability",
            failed_check_names=["security-scan"],
            recommended_action="Update dependencies",
        )

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            output_file = f.name

        try:
            console = Console()
            _output_json_format(result, console, output_file=output_file)

            # Verify file was created and contains correct data
            assert Path(output_file).exists()
            with open(output_file, "r") as f:
                data = json.load(f)

            assert data["failure_type"] == "security"
            assert data["confidence"] == 0.92
            assert data["reasoning"] == "Security vulnerability"
        finally:
            Path(output_file).unlink(missing_ok=True)

    def test_output_json_file_formatting(self):
        """Test that JSON file is properly formatted with indent."""
        result = ClassificationResult(
            failure_type=FailureType.BUILD,
            confidence=0.88,
            reasoning="Build failed",
            failed_check_names=["build"],
            recommended_action="Fix build errors",
        )

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            output_file = f.name

        try:
            console = Console()
            _output_json_format(result, console, output_file=output_file)

            # Read raw content to verify formatting
            with open(output_file, "r") as f:
                content = f.read()

            # Should have indentation and newlines (pretty-printed)
            assert "\n" in content
            assert "  " in content  # 2-space indent
        finally:
            Path(output_file).unlink(missing_ok=True)


class TestOutputRichFormat:
    """Test suite for _output_rich_format function."""

    def test_output_rich_format_successful(self):
        """Test Rich format output for successful classification."""
        result = ClassificationResult(
            failure_type=FailureType.TEST,
            confidence=0.95,
            reasoning="Unit tests failed",
            failed_check_names=["pytest"],
            recommended_action="Fix test assertions",
        )

        console = Console()
        with patch.object(console, "print") as mock_print:
            _output_rich_format(result, console)
            # Should print multiple times (empty line, panel, empty line)
            assert mock_print.call_count >= 3

    def test_output_rich_format_unknown(self):
        """Test Rich format output for unknown classification."""
        result = ClassificationResult(
            failure_type=FailureType.UNKNOWN,
            confidence=0.3,
            reasoning="Cannot classify",
            failed_check_names=[],
            recommended_action="Manual review",
        )

        console = Console()
        with patch.object(console, "print") as mock_print:
            _output_rich_format(result, console)
            assert mock_print.call_count >= 3

    def test_output_rich_format_low_confidence(self):
        """Test Rich format output for low confidence result."""
        result = ClassificationResult(
            failure_type=FailureType.LINT,
            confidence=0.6,  # Below 0.7 threshold
            reasoning="Might be linting",
            failed_check_names=["check"],
            recommended_action="Verify",
        )

        console = Console()
        with patch.object(console, "print") as mock_print:
            _output_rich_format(result, console)
            assert mock_print.call_count >= 3


class TestOutputResult:
    """Test suite for _output_result function."""

    def test_output_result_rich_format(self):
        """Test routing to Rich format."""
        result = ClassificationResult(
            failure_type=FailureType.TEST,
            confidence=0.9,
            reasoning="Test",
            failed_check_names=[],
            recommended_action="Fix",
        )

        console = Console()
        with (
            patch("aieng_bot._cli.commands.classify._output_rich_format") as mock_rich,
            patch("aieng_bot._cli.commands.classify._output_json_format") as mock_json,
        ):
            _output_result(result, console, json_output=False, output_file=None)
            mock_rich.assert_called_once()
            mock_json.assert_not_called()

    def test_output_result_json_format(self):
        """Test routing to JSON format with --json flag."""
        result = ClassificationResult(
            failure_type=FailureType.LINT,
            confidence=0.85,
            reasoning="Lint",
            failed_check_names=[],
            recommended_action="Fix",
        )

        console = Console()
        with (
            patch("aieng_bot._cli.commands.classify._output_rich_format") as mock_rich,
            patch("aieng_bot._cli.commands.classify._output_json_format") as mock_json,
        ):
            _output_result(result, console, json_output=True, output_file=None)
            mock_json.assert_called_once()
            mock_rich.assert_not_called()

    def test_output_result_json_file(self):
        """Test routing to JSON format with output file."""
        result = ClassificationResult(
            failure_type=FailureType.SECURITY,
            confidence=0.95,
            reasoning="Security",
            failed_check_names=[],
            recommended_action="Update",
        )

        console = Console()
        with (
            patch("aieng_bot._cli.commands.classify._output_rich_format") as mock_rich,
            patch("aieng_bot._cli.commands.classify._output_json_format") as mock_json,
        ):
            _output_result(result, console, json_output=False, output_file="out.json")
            mock_json.assert_called_once_with(result, console, "out.json")
            mock_rich.assert_not_called()


class TestHandleMergeConflict:
    """Test suite for _handle_merge_conflict function."""

    def test_handle_merge_conflict_rich_output(self):
        """Test merge conflict handler with Rich output."""
        console = Console()
        with (
            patch("aieng_bot._cli.commands.classify._output_result") as mock_output,
            pytest.raises(SystemExit) as exc_info,
        ):
            _handle_merge_conflict(console, json_output=False, output_file=None)

        assert exc_info.value.code == 0
        mock_output.assert_called_once()

        # Verify the result passed to output
        call_args = mock_output.call_args
        result = call_args[0][0]
        assert result.failure_type == FailureType.MERGE_CONFLICT
        assert result.confidence == 1.0
        assert "merge conflicts" in result.reasoning.lower()

    def test_handle_merge_conflict_json_output(self):
        """Test merge conflict handler with JSON output."""
        console = Console()
        with (
            patch("aieng_bot._cli.commands.classify._output_result") as mock_output,
            pytest.raises(SystemExit) as exc_info,
        ):
            _handle_merge_conflict(console, json_output=True, output_file=None)

        assert exc_info.value.code == 0
        call_args = mock_output.call_args
        assert call_args[0][2] is True  # json_output=True


class TestHandleNoFailedChecks:
    """Test suite for _handle_no_failed_checks function."""

    def test_handle_no_failed_checks_rich_output(self):
        """Test no failed checks handler with Rich output."""
        console = Console()
        with (
            patch("aieng_bot._cli.commands.classify._output_result") as mock_output,
            pytest.raises(SystemExit) as exc_info,
        ):
            _handle_no_failed_checks(console, json_output=False, output_file=None)

        assert exc_info.value.code == 0
        mock_output.assert_called_once()

        # Verify the result
        result = mock_output.call_args[0][0]
        assert result.failure_type == FailureType.UNKNOWN
        assert result.confidence == 0.0
        assert len(result.failed_check_names) == 0

    def test_handle_no_failed_checks_json_output(self):
        """Test no failed checks handler with JSON output."""
        console = Console()
        with (
            patch("aieng_bot._cli.commands.classify._output_result") as mock_output,
            pytest.raises(SystemExit) as exc_info,
        ):
            _handle_no_failed_checks(console, json_output=True, output_file="out.json")

        assert exc_info.value.code == 0
        call_args = mock_output.call_args
        assert call_args[0][2] is True  # json_output=True
        assert call_args[0][3] == "out.json"  # output_file


class TestClassifyCommand:
    """Test suite for classify CLI command."""

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    @patch("aieng_bot._cli.commands.classify.PRFailureClassifier")
    @patch("aieng_bot._cli.commands.classify.GitHubClient")
    def test_classify_successful(self, mock_github_client_class, mock_classifier_class):
        """Test successful classification."""
        # Setup mocks
        mock_github = MagicMock()
        mock_github.check_merge_conflicts.return_value = False
        mock_github.get_pr_details.return_value = PRContext(
            repo="VectorInstitute/test-repo",
            pr_number=123,
            pr_title="Update deps",
            pr_author="app/dependabot",
            base_ref="main",
            head_ref="update-branch",
        )
        mock_github.get_failed_checks.return_value = [
            CheckFailure(
                name="test-check",
                conclusion="FAILURE",
                workflow_name="CI",
                details_url="https://github.com/.../runs/123",
                started_at="2025-01-01T00:00:00Z",
                completed_at="2025-01-01T00:05:00Z",
            )
        ]
        mock_github.get_failure_logs.return_value = "/tmp/logs.txt"
        mock_github_client_class.return_value = mock_github

        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = ClassificationResult(
            failure_type=FailureType.TEST,
            confidence=0.95,
            reasoning="Tests failed",
            failed_check_names=["test-check"],
            recommended_action="Fix tests",
        )
        mock_classifier_class.return_value = mock_classifier

        runner = CliRunner()
        result = runner.invoke(
            cli, ["classify", "--repo", "VectorInstitute/test-repo", "--pr", "123"]
        )

        assert result.exit_code == 0
        mock_github.check_merge_conflicts.assert_called_once_with(
            "VectorInstitute/test-repo", 123
        )
        mock_github.get_pr_details.assert_called_once()
        mock_github.get_failed_checks.assert_called_once()
        mock_classifier.classify.assert_called_once()

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    @patch("aieng_bot._cli.commands.classify.GitHubClient")
    def test_classify_with_merge_conflicts(self, mock_github_client_class):
        """Test classification with merge conflicts."""
        mock_github = MagicMock()
        mock_github.check_merge_conflicts.return_value = True
        mock_github_client_class.return_value = mock_github

        runner = CliRunner()
        result = runner.invoke(
            cli, ["classify", "--repo", "VectorInstitute/test-repo", "--pr", "123"]
        )

        assert result.exit_code == 0
        mock_github.check_merge_conflicts.assert_called_once()
        # Should not fetch PR details or run classification
        mock_github.get_pr_details.assert_not_called()

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    @patch("aieng_bot._cli.commands.classify.GitHubClient")
    def test_classify_with_no_failed_checks(self, mock_github_client_class):
        """Test classification with no failed checks."""
        mock_github = MagicMock()
        mock_github.check_merge_conflicts.return_value = False
        mock_github.get_pr_details.return_value = PRContext(
            repo="VectorInstitute/test-repo",
            pr_number=123,
            pr_title="Update deps",
            pr_author="app/dependabot",
            base_ref="main",
            head_ref="update-branch",
        )
        mock_github.get_failed_checks.return_value = []
        mock_github_client_class.return_value = mock_github

        runner = CliRunner()
        result = runner.invoke(
            cli, ["classify", "--repo", "VectorInstitute/test-repo", "--pr", "123"]
        )

        assert result.exit_code == 0
        mock_github.get_failed_checks.assert_called_once()

    @patch.dict(os.environ, {}, clear=True)
    def test_classify_missing_env_vars(self):
        """Test classification with missing environment variables."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["classify", "--repo", "VectorInstitute/test-repo", "--pr", "123"]
        )

        assert result.exit_code == 1
        assert "Missing required environment variables" in result.output

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    @patch("aieng_bot._cli.commands.classify.PRFailureClassifier")
    @patch("aieng_bot._cli.commands.classify.GitHubClient")
    def test_classify_json_output(
        self, mock_github_client_class, mock_classifier_class
    ):
        """Test classification with JSON output."""
        # Setup mocks
        mock_github = MagicMock()
        mock_github.check_merge_conflicts.return_value = False
        mock_github.get_pr_details.return_value = PRContext(
            repo="VectorInstitute/test-repo",
            pr_number=123,
            pr_title="Test PR",
            pr_author="app/dependabot",
            base_ref="main",
            head_ref="test",
        )
        mock_github.get_failed_checks.return_value = [
            CheckFailure(
                name="check",
                conclusion="FAILURE",
                workflow_name="CI",
                details_url="url",
                started_at="time",
                completed_at="time",
            )
        ]
        mock_github.get_failure_logs.return_value = "/tmp/logs.txt"
        mock_github_client_class.return_value = mock_github

        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = ClassificationResult(
            failure_type=FailureType.LINT,
            confidence=0.85,
            reasoning="Lint errors",
            failed_check_names=["check"],
            recommended_action="Fix",
        )
        mock_classifier_class.return_value = mock_classifier

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "classify",
                "--repo",
                "VectorInstitute/test-repo",
                "--pr",
                "123",
                "--json",
            ],
        )

        assert result.exit_code == 0
        # Output should be JSON
        assert "lint" in result.output.lower()

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    @patch("aieng_bot._cli.commands.classify.PRFailureClassifier")
    @patch("aieng_bot._cli.commands.classify.GitHubClient")
    def test_classify_output_to_file(
        self, mock_github_client_class, mock_classifier_class
    ):
        """Test classification with output to file."""
        # Setup mocks
        mock_github = MagicMock()
        mock_github.check_merge_conflicts.return_value = False
        mock_github.get_pr_details.return_value = PRContext(
            repo="VectorInstitute/test-repo",
            pr_number=123,
            pr_title="Test PR",
            pr_author="app/dependabot",
            base_ref="main",
            head_ref="test",
        )
        mock_github.get_failed_checks.return_value = [
            CheckFailure(
                name="check",
                conclusion="FAILURE",
                workflow_name="CI",
                details_url="url",
                started_at="time",
                completed_at="time",
            )
        ]
        mock_github.get_failure_logs.return_value = "/tmp/logs.txt"
        mock_github_client_class.return_value = mock_github

        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = ClassificationResult(
            failure_type=FailureType.BUILD,
            confidence=0.9,
            reasoning="Build failed",
            failed_check_names=["check"],
            recommended_action="Fix build",
        )
        mock_classifier_class.return_value = mock_classifier

        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".json"
        ) as temp_file:
            output_file = temp_file.name

        try:
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "classify",
                    "--repo",
                    "VectorInstitute/test-repo",
                    "--pr",
                    "123",
                    "--output",
                    output_file,
                ],
            )

            assert result.exit_code == 0
            assert Path(output_file).exists()

            # Verify file contents
            with open(output_file, "r") as f:
                data = json.load(f)
            assert data["failure_type"] == "build"
            assert data["confidence"] == 0.9
        finally:
            Path(output_file).unlink(missing_ok=True)

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    @patch("aieng_bot._cli.commands.classify.PRFailureClassifier")
    @patch("aieng_bot._cli.commands.classify.GitHubClient")
    def test_classify_unknown_exits_with_error(
        self, mock_github_client_class, mock_classifier_class
    ):
        """Test that unknown classification exits with error code."""
        # Setup mocks
        mock_github = MagicMock()
        mock_github.check_merge_conflicts.return_value = False
        mock_github.get_pr_details.return_value = PRContext(
            repo="VectorInstitute/test-repo",
            pr_number=123,
            pr_title="Test PR",
            pr_author="app/dependabot",
            base_ref="main",
            head_ref="test",
        )
        mock_github.get_failed_checks.return_value = [
            CheckFailure(
                name="check",
                conclusion="FAILURE",
                workflow_name="CI",
                details_url="url",
                started_at="time",
                completed_at="time",
            )
        ]
        mock_github.get_failure_logs.return_value = "/tmp/logs.txt"
        mock_github_client_class.return_value = mock_github

        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = ClassificationResult(
            failure_type=FailureType.UNKNOWN,
            confidence=0.3,
            reasoning="Cannot classify",
            failed_check_names=["check"],
            recommended_action="Manual review",
        )
        mock_classifier_class.return_value = mock_classifier

        runner = CliRunner()
        result = runner.invoke(
            cli, ["classify", "--repo", "VectorInstitute/test-repo", "--pr", "123"]
        )

        # Should exit with error code for unknown
        assert result.exit_code == 1

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    @patch("aieng_bot._cli.commands.classify.GitHubClient")
    def test_classify_github_api_error(self, mock_github_client_class):
        """Test classification with GitHub API error."""
        mock_github_client_class.side_effect = ValueError("GitHub API error")

        runner = CliRunner()
        result = runner.invoke(
            cli, ["classify", "--repo", "VectorInstitute/test-repo", "--pr", "123"]
        )

        assert result.exit_code == 1
        assert "GitHub API error" in result.output

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    @patch("aieng_bot._cli.commands.classify.PRFailureClassifier")
    @patch("aieng_bot._cli.commands.classify.GitHubClient")
    def test_classify_unexpected_error(
        self, mock_github_client_class, mock_classifier_class
    ):
        """Test classification with unexpected error."""
        mock_github = MagicMock()
        mock_github.check_merge_conflicts.side_effect = Exception("Unexpected error")
        mock_github_client_class.return_value = mock_github

        runner = CliRunner()
        result = runner.invoke(
            cli, ["classify", "--repo", "VectorInstitute/test-repo", "--pr", "123"]
        )

        assert result.exit_code == 1
        assert "Unexpected error" in result.output

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    @patch("aieng_bot._cli.commands.classify.PRFailureClassifier")
    @patch("aieng_bot._cli.commands.classify.GitHubClient")
    @patch("os.unlink")
    def test_classify_cleans_up_temp_file(
        self, mock_unlink, mock_github_client_class, mock_classifier_class
    ):
        """Test that temporary log file is cleaned up."""
        # Setup mocks
        mock_github = MagicMock()
        mock_github.check_merge_conflicts.return_value = False
        mock_github.get_pr_details.return_value = PRContext(
            repo="VectorInstitute/test-repo",
            pr_number=123,
            pr_title="Test",
            pr_author="app/dependabot",
            base_ref="main",
            head_ref="test",
        )
        mock_github.get_failed_checks.return_value = [
            CheckFailure(
                name="check",
                conclusion="FAILURE",
                workflow_name="CI",
                details_url="url",
                started_at="time",
                completed_at="time",
            )
        ]
        mock_github.get_failure_logs.return_value = "/tmp/test-logs.txt"
        mock_github_client_class.return_value = mock_github

        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = ClassificationResult(
            failure_type=FailureType.TEST,
            confidence=0.9,
            reasoning="Test",
            failed_check_names=["check"],
            recommended_action="Fix",
        )
        mock_classifier_class.return_value = mock_classifier

        runner = CliRunner()
        result = runner.invoke(
            cli, ["classify", "--repo", "VectorInstitute/test-repo", "--pr", "123"]
        )

        assert result.exit_code == 0
        # Verify temp file cleanup was attempted
        mock_unlink.assert_called_with("/tmp/test-logs.txt")

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    def test_classify_with_explicit_tokens(self):
        """Test classification with explicitly provided tokens."""
        with patch("aieng_bot._cli.commands.classify.GitHubClient") as mock_gh:
            mock_github = MagicMock()
            mock_github.check_merge_conflicts.return_value = True
            mock_gh.return_value = mock_github

            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "classify",
                    "--repo",
                    "VectorInstitute/test-repo",
                    "--pr",
                    "123",
                    "--github-token",
                    "explicit-gh-token",
                    "--anthropic-api-key",
                    "explicit-api-key",
                ],
            )

            # Should exit successfully with merge conflict detected
            assert result.exit_code == 0
            # Should use explicit tokens
            mock_gh.assert_called_once_with(github_token="explicit-gh-token")
