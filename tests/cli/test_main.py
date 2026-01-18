"""Tests for CLI functionality."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from aieng_bot._cli.main import cli
from aieng_bot._cli.utils import get_version


def test_get_version_installed():
    """Test get_version returns version string when package is installed."""
    with patch("aieng_bot._cli.utils.version") as mock_version:
        mock_version.return_value = "1.2.3"
        result = get_version()
        assert result == "1.2.3"
        mock_version.assert_called_once_with("aieng-bot")


def test_get_version_not_installed():
    """Test get_version returns 'unknown' when package is not installed."""
    with patch("aieng_bot._cli.utils.version") as mock_version:
        from importlib.metadata import (  # noqa: PLC0415 - Import after mock setup
            PackageNotFoundError,
        )

        mock_version.side_effect = PackageNotFoundError()
        result = get_version()
        assert result == "unknown"


def test_cli_version_flag():
    """Test that --version flag outputs version and exits."""
    runner = CliRunner()

    with patch("aieng_bot._cli.main.get_version") as mock_get_version:
        mock_get_version.return_value = "1.2.3"
        result = runner.invoke(cli, ["--version"])

    # Should exit with code 0
    assert result.exit_code == 0
    assert "aieng-bot 1.2.3" in result.output


def test_cli_version_output_format():
    """Test that --version outputs in correct format."""
    import re  # noqa: PLC0415 - Import after test setup

    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])

    output = result.output
    assert "aieng-bot" in output
    # Check that output contains a version string (format: X.Y.Z or X.Y.Z.dev)
    assert re.search(r"\d+\.\d+\.\d+", output), "Output should contain a version number"


def test_version_with_development_install():
    """Test version handling for development (editable) installs."""
    with patch("aieng_bot._cli.utils.version") as mock_version:
        mock_version.return_value = "1.2.3.dev"
        result = get_version()
        assert result == "1.2.3.dev"


def test_version_function_exception_handling():
    """Test that get_version handles unexpected exceptions gracefully."""
    with patch("aieng_bot._cli.utils.version") as mock_version:
        # Only PackageNotFoundError should return "unknown"
        from importlib.metadata import (  # noqa: PLC0415 - Import after mock setup
            PackageNotFoundError,
        )

        mock_version.side_effect = PackageNotFoundError()
        result = get_version()
        assert result == "unknown"

        # Any other exception should propagate
        mock_version.side_effect = RuntimeError("Unexpected error")
        with pytest.raises(RuntimeError, match="Unexpected error"):
            get_version()


def test_cli_help_includes_version():
    """Test that --help output includes version option."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    output = result.output
    assert "--version" in output
    assert "Show version and exit" in output

    # Help should exit with code 0
    assert result.exit_code == 0


class TestFixCLI:
    """Test fix CLI command."""

    @pytest.fixture
    def mock_env(self):
        """Set up environment variables for tests."""
        return {
            "ANTHROPIC_API_KEY": "test-api-key",
            "GITHUB_TOKEN": "test-github-token",
        }

    @pytest.fixture
    def cli_args(self, tmp_path):
        """Create valid CLI arguments for testing."""
        return [
            "fix",
            "--repo",
            "VectorInstitute/test-repo",
            "--pr",
            "123",
            "--cwd",
            str(tmp_path),
        ]

    def test_cli_version_flag(self, mock_env):
        """Test --version flag for fix command."""
        runner = CliRunner()

        with (
            patch.dict("os.environ", mock_env),
            patch("aieng_bot._cli.main.get_version") as mock_get_version,
        ):
            mock_get_version.return_value = "1.2.3"
            result = runner.invoke(cli, ["--version"])

        assert result.exit_code == 0
        assert "aieng-bot 1.2.3" in result.output

    def test_cli_help_flag(self, mock_env):
        """Test --help flag for fix command."""
        runner = CliRunner()

        with patch.dict("os.environ", mock_env):
            result = runner.invoke(cli, ["fix", "--help"])

        output = result.output
        assert "Fix and merge a PR" in output
        assert "--repo" in output
        assert "--pr" in output
        assert "--max-retries" in output
        assert result.exit_code == 0

    def test_cli_success(self, cli_args, mock_env):
        """Test successful execution of fix CLI."""
        from aieng_bot.agent_fixer import (  # noqa: PLC0415 - Import after fixtures
            AgentFixResult,
        )
        from aieng_bot.classifier.models import (  # noqa: PLC0415 - Import after fixtures
            ClassificationResult,
            FailureType,
        )

        mock_result = AgentFixResult(
            status="SUCCESS",
            trace_file="/tmp/trace.json",
            summary_file="/tmp/summary.txt",
        )

        mock_classification = ClassificationResult(
            failure_types=[FailureType.LINT],
            confidence=0.95,
            reasoning="Lint failure detected",
            failed_check_names=["lint-check"],
            recommended_action="Run linter",
        )

        runner = CliRunner()

        with (
            patch.dict("os.environ", mock_env),
            patch("aieng_bot._cli.commands.fix._fetch_pr_details") as mock_fetch,
            patch(
                "aieng_bot._cli.commands.fix._fetch_initial_failure_logs"
            ) as mock_fetch_logs,
            patch("aieng_bot._cli.commands.fix._classify_failure") as mock_classify,
            patch(
                "aieng_bot._cli.commands.fix._prepare_agent_environment"
            ) as mock_prepare,
            patch(
                "aieng_bot._cli.commands.fix._cleanup_temporary_files"
            ) as mock_cleanup,
            patch("aieng_bot._cli.commands.fix.AgentFixer") as mock_fixer_class,
            patch("aieng_bot._cli.commands.fix.asyncio.run") as mock_asyncio_run,
        ):
            # Mock helper function returns
            mock_fetch.return_value = (
                "Bump pytest",
                "app/dependabot",
                "dependabot/pytest-8.0.0",
                "main",
            )
            mock_fetch_logs.return_value = ".failure-logs.txt"
            mock_classify.return_value = mock_classification
            mock_prepare.return_value = True

            mock_fixer = MagicMock()
            mock_fixer_class.return_value = mock_fixer
            mock_asyncio_run.return_value = mock_result

            result = runner.invoke(cli, cli_args)

            assert result.exit_code == 0
            mock_fixer_class.assert_called_once()
            mock_asyncio_run.assert_called_once()
            mock_cleanup.assert_called_once()

    def test_cli_failure(self, cli_args, mock_env):
        """Test failed execution of fix CLI."""
        from aieng_bot.agent_fixer import (  # noqa: PLC0415 - Import after fixtures
            AgentFixResult,
        )
        from aieng_bot.classifier.models import (  # noqa: PLC0415 - Import after fixtures
            ClassificationResult,
            FailureType,
        )

        mock_result = AgentFixResult(
            status="FAILED",
            trace_file="",
            summary_file="",
            error_message="Agent execution failed",
        )

        mock_classification = ClassificationResult(
            failure_types=[FailureType.LINT],
            confidence=0.95,
            reasoning="Lint failure detected",
            failed_check_names=["lint-check"],
            recommended_action="Run linter",
        )

        runner = CliRunner()

        with (
            patch.dict("os.environ", mock_env),
            patch("aieng_bot._cli.commands.fix._fetch_pr_details") as mock_fetch,
            patch(
                "aieng_bot._cli.commands.fix._fetch_initial_failure_logs"
            ) as mock_fetch_logs,
            patch("aieng_bot._cli.commands.fix._classify_failure") as mock_classify,
            patch(
                "aieng_bot._cli.commands.fix._prepare_agent_environment"
            ) as mock_prepare,
            patch(
                "aieng_bot._cli.commands.fix._cleanup_temporary_files"
            ) as mock_cleanup,
            patch("aieng_bot._cli.commands.fix.AgentFixer") as mock_fixer_class,
            patch("aieng_bot._cli.commands.fix.asyncio.run") as mock_asyncio_run,
        ):
            # Mock helper function returns
            mock_fetch.return_value = (
                "Bump pytest",
                "app/dependabot",
                "dependabot/pytest-8.0.0",
                "main",
            )
            mock_fetch_logs.return_value = ".failure-logs.txt"
            mock_classify.return_value = mock_classification
            mock_prepare.return_value = True

            mock_fixer = MagicMock()
            mock_fixer_class.return_value = mock_fixer
            mock_asyncio_run.return_value = mock_result

            result = runner.invoke(cli, cli_args)

            assert result.exit_code == 1
            mock_cleanup.assert_called_once()

    def test_cli_missing_required_args(self, mock_env):
        """Test CLI with missing required arguments."""
        runner = CliRunner()
        test_args = [
            "fix",
            "--repo",
            "VectorInstitute/test-repo",
            # Missing --pr
        ]

        with patch.dict("os.environ", mock_env):
            result = runner.invoke(cli, test_args)

        # Should exit with error code
        assert result.exit_code != 0

    def test_cli_no_api_key(self, cli_args):
        """Test CLI without ANTHROPIC_API_KEY set."""
        runner = CliRunner()

        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(cli, cli_args)

        # Should exit with error code (missing required args or env vars)
        assert result.exit_code != 0

    def test_cli_exception_handling(self, cli_args, mock_env):
        """Test CLI handles unexpected exceptions gracefully."""
        runner = CliRunner()

        with (
            patch.dict("os.environ", mock_env),
            patch(
                "aieng_bot._cli.commands.fix._fetch_pr_details",
                side_effect=RuntimeError("Unexpected error"),
            ),
            patch(
                "aieng_bot._cli.commands.fix._cleanup_temporary_files"
            ) as mock_cleanup,
        ):
            result = runner.invoke(cli, cli_args)

            assert result.exit_code == 1
            mock_cleanup.assert_called_once()
