"""Tests for CLI functionality."""

import sys
from io import StringIO
from unittest.mock import patch

import pytest

from aieng_bot_maintain.cli import get_version


def test_get_version_installed():
    """Test get_version returns version string when package is installed."""
    with patch("aieng_bot_maintain.cli.version") as mock_version:
        mock_version.return_value = "0.1.0"
        result = get_version()
        assert result == "0.1.0"
        mock_version.assert_called_once_with("aieng-bot-maintain")


def test_get_version_not_installed():
    """Test get_version returns 'unknown' when package is not installed."""
    with patch("aieng_bot_maintain.cli.version") as mock_version:
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
        mock_get_version.return_value = "0.1.0"
        from aieng_bot_maintain.cli import classify_pr_failure_cli

        # Capture stdout
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            classify_pr_failure_cli()

    # Should exit with code 0
    assert exc_info.value.code == 0


def test_cli_version_output_format():
    """Test that --version outputs in correct format."""
    test_args = ["classify-pr-failure", "--version"]

    with (
        patch.object(sys, "argv", test_args),
        patch("aieng_bot_maintain.cli.get_version") as mock_get_version,
    ):
        mock_get_version.return_value = "0.1.0"

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
        assert "0.1.0" in output


def test_version_with_development_install():
    """Test version handling for development (editable) installs."""
    with patch("aieng_bot_maintain.cli.version") as mock_version:
        mock_version.return_value = "0.1.0.dev"
        result = get_version()
        assert result == "0.1.0.dev"


def test_version_function_exception_handling():
    """Test that get_version handles unexpected exceptions gracefully."""
    with patch("aieng_bot_maintain.cli.version") as mock_version:
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
