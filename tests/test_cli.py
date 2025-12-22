"""Tests for CLI functionality."""

import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from aieng_bot_maintain.cli import get_version


def test_get_version_installed():
    """Test get_version returns version string when package is installed."""
    with patch("aieng_bot_maintain._cli.utils.version") as mock_version:
        mock_version.return_value = "1.2.3"
        result = get_version()
        assert result == "1.2.3"
        mock_version.assert_called_once_with("aieng-bot-maintain")


def test_get_version_not_installed():
    """Test get_version returns 'unknown' when package is not installed."""
    with patch("aieng_bot_maintain._cli.utils.version") as mock_version:
        from importlib.metadata import PackageNotFoundError

        mock_version.side_effect = PackageNotFoundError()
        result = get_version()
        assert result == "unknown"


def test_cli_version_flag():
    """Test that --version flag outputs version and exits."""
    test_args = ["classify-pr-failure", "--version"]

    with (
        patch.object(sys, "argv", test_args),
        patch("aieng_bot_maintain.cli.get_version") as mock_get_version,
        pytest.raises(SystemExit) as exc_info,
    ):
        mock_get_version.return_value = "1.2.3"
        from aieng_bot_maintain.cli import classify_pr_failure_cli

        # Capture stdout
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            classify_pr_failure_cli()

    # Should exit with code 0
    assert exc_info.value.code == 0


def test_cli_version_output_format():
    """Test that --version outputs in correct format."""
    import re

    test_args = ["classify-pr-failure", "--version"]

    with (
        patch.object(sys, "argv", test_args),
    ):
        from aieng_bot_maintain.cli import classify_pr_failure_cli

        # Capture stdout
        captured_output = StringIO()
        try:
            with patch("sys.stdout", captured_output):
                classify_pr_failure_cli()
        except SystemExit:
            pass

        output = captured_output.getvalue()
        assert "classify-pr-failure" in output
        # Check that output contains a version string (format: X.Y.Z or X.Y.Z.dev)
        assert re.search(r"\d+\.\d+\.\d+", output), (
            "Output should contain a version number"
        )


def test_version_with_development_install():
    """Test version handling for development (editable) installs."""
    with patch("aieng_bot_maintain._cli.utils.version") as mock_version:
        mock_version.return_value = "1.2.3.dev"
        result = get_version()
        assert result == "1.2.3.dev"


def test_version_function_exception_handling():
    """Test that get_version handles unexpected exceptions gracefully."""
    with patch("aieng_bot_maintain._cli.utils.version") as mock_version:
        # Only PackageNotFoundError should return "unknown"
        from importlib.metadata import PackageNotFoundError

        mock_version.side_effect = PackageNotFoundError()
        result = get_version()
        assert result == "unknown"

        # Any other exception should propagate
        mock_version.side_effect = RuntimeError("Unexpected error")
        with pytest.raises(RuntimeError, match="Unexpected error"):
            get_version()


def test_cli_help_includes_version():
    """Test that --help output includes version option."""
    test_args = ["classify-pr-failure", "--help"]

    with (
        patch.object(sys, "argv", test_args),
        pytest.raises(SystemExit) as exc_info,
    ):
        from aieng_bot_maintain.cli import classify_pr_failure_cli

        # Capture stdout
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            classify_pr_failure_cli()

        output = captured_output.getvalue()
        assert "--version" in output
        assert "Show version number and exit" in output

    # Help should exit with code 0
    assert exc_info.value.code == 0


class TestApplyAgentFixCLI:
    """Test apply-agent-fix CLI command."""

    @pytest.fixture
    def mock_env(self):
        """Set up environment variables for tests."""
        return {"ANTHROPIC_API_KEY": "test-api-key"}

    @pytest.fixture
    def cli_args(self, tmp_path):
        """Create valid CLI arguments for testing (skills-based)."""
        logs_file = tmp_path / ".failure-logs.txt"
        logs_file.write_text("Test logs")

        # Create skills directory for agent to use
        skills_dir = tmp_path / ".claude" / "skills" / "fix-test-failures"
        skills_dir.mkdir(parents=True, exist_ok=True)
        (skills_dir / "SKILL.md").write_text("Test skill")

        return [
            "apply-agent-fix",
            "--repo",
            "VectorInstitute/test-repo",
            "--pr-number",
            "123",
            "--pr-title",
            "Bump pytest",
            "--pr-author",
            "app/dependabot",
            "--pr-url",
            "https://github.com/VectorInstitute/test-repo/pull/123",
            "--head-ref",
            "dependabot/pytest-8.0.0",
            "--base-ref",
            "main",
            "--failure-type",
            "test",
            "--failed-check-names",
            "Run Tests",
            "--failure-logs-file",
            str(logs_file),
            "--workflow-run-id",
            "1234567890",
            "--github-run-url",
            "https://github.com/runs/123",
            "--cwd",
            str(tmp_path),
        ]

    def test_cli_version_flag(self, mock_env):
        """Test --version flag for apply-agent-fix command."""
        test_args = ["apply-agent-fix", "--version"]

        with (
            patch.dict("os.environ", mock_env),
            patch.object(sys, "argv", test_args),
            patch("aieng_bot_maintain.cli.get_version") as mock_get_version,
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_get_version.return_value = "1.2.3"
            from aieng_bot_maintain.cli import apply_agent_fix_cli

            captured_output = StringIO()
            with patch("sys.stdout", captured_output):
                apply_agent_fix_cli()

        assert exc_info.value.code == 0

    def test_cli_help_flag(self, mock_env):
        """Test --help flag for apply-agent-fix command."""
        test_args = ["apply-agent-fix", "--help"]

        with (
            patch.dict("os.environ", mock_env),
            patch.object(sys, "argv", test_args),
            pytest.raises(SystemExit) as exc_info,
        ):
            from aieng_bot_maintain.cli import apply_agent_fix_cli

            captured_output = StringIO()
            with patch("sys.stdout", captured_output):
                apply_agent_fix_cli()

            output = captured_output.getvalue()
            assert "Apply automated fixes" in output
            assert "--repo" in output
            assert "--failure-type" in output

        assert exc_info.value.code == 0

    def test_cli_success(self, cli_args, mock_env):
        """Test successful execution of apply-agent-fix CLI."""
        from aieng_bot_maintain.agent_fixer import AgentFixResult

        mock_result = AgentFixResult(
            status="SUCCESS",
            trace_file="/tmp/trace.json",
            summary_file="/tmp/summary.txt",
        )

        with (
            patch.dict("os.environ", mock_env),
            patch.object(sys, "argv", cli_args),
            patch(
                "aieng_bot_maintain._cli.commands.apply_fix.AgentFixer"
            ) as mock_fixer_class,
            patch(
                "aieng_bot_maintain._cli.commands.apply_fix.asyncio.run"
            ) as mock_asyncio_run,
        ):
            mock_fixer = MagicMock()
            mock_fixer_class.return_value = mock_fixer
            mock_asyncio_run.return_value = mock_result

            from aieng_bot_maintain.cli import apply_agent_fix_cli

            with pytest.raises(SystemExit) as exc_info:
                apply_agent_fix_cli()

            assert exc_info.value.code == 0
            mock_fixer_class.assert_called_once()
            mock_asyncio_run.assert_called_once()

    def test_cli_failure(self, cli_args, mock_env):
        """Test failed execution of apply-agent-fix CLI."""
        from aieng_bot_maintain.agent_fixer import AgentFixResult

        mock_result = AgentFixResult(
            status="FAILED",
            trace_file="",
            summary_file="",
            error_message="Agent execution failed",
        )

        with (
            patch.dict("os.environ", mock_env),
            patch.object(sys, "argv", cli_args),
            patch(
                "aieng_bot_maintain._cli.commands.apply_fix.AgentFixer"
            ) as mock_fixer_class,
            patch(
                "aieng_bot_maintain._cli.commands.apply_fix.asyncio.run"
            ) as mock_asyncio_run,
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_fixer = MagicMock()
            mock_fixer_class.return_value = mock_fixer
            mock_asyncio_run.return_value = mock_result

            from aieng_bot_maintain.cli import apply_agent_fix_cli

            apply_agent_fix_cli()

        assert exc_info.value.code == 1

    def test_cli_missing_required_args(self, mock_env):
        """Test CLI with missing required arguments."""
        test_args = [
            "apply-agent-fix",
            "--repo",
            "VectorInstitute/test-repo",
            # Missing other required args
        ]

        with (
            patch.dict("os.environ", mock_env),
            patch.object(sys, "argv", test_args),
            pytest.raises(SystemExit) as exc_info,
        ):
            from aieng_bot_maintain.cli import apply_agent_fix_cli

            apply_agent_fix_cli()

        # Should exit with error code
        assert exc_info.value.code != 0

    def test_cli_invalid_failure_type(self, cli_args, mock_env):
        """Test CLI with invalid failure type."""
        # Modify args to have invalid failure type
        failure_type_idx = cli_args.index("--failure-type")
        cli_args[failure_type_idx + 1] = "invalid_type"

        with (
            patch.dict("os.environ", mock_env),
            patch.object(sys, "argv", cli_args),
            pytest.raises(SystemExit) as exc_info,
        ):
            from aieng_bot_maintain.cli import apply_agent_fix_cli

            apply_agent_fix_cli()

        # Should exit with error code due to invalid choice
        assert exc_info.value.code != 0

    def test_cli_no_api_key(self, cli_args):
        """Test CLI without ANTHROPIC_API_KEY set."""
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(sys, "argv", cli_args),
            pytest.raises(SystemExit) as exc_info,
        ):
            from aieng_bot_maintain.cli import apply_agent_fix_cli

            apply_agent_fix_cli()

        # Should exit with error code
        assert exc_info.value.code == 1

    def test_cli_exception_handling(self, cli_args, mock_env):
        """Test CLI handles unexpected exceptions gracefully."""
        with (
            patch.dict("os.environ", mock_env),
            patch.object(sys, "argv", cli_args),
            patch(
                "aieng_bot_maintain.cli.AgentFixer",
                side_effect=RuntimeError("Unexpected error"),
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            from aieng_bot_maintain.cli import apply_agent_fix_cli

            apply_agent_fix_cli()

        assert exc_info.value.code == 1
