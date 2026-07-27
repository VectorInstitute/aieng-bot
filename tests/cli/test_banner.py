"""Tests for CLI banner and group behavior."""

import os
from unittest.mock import patch

from click.testing import CliRunner
from rich.console import Console

from aieng_bot._cli.main import cli, print_banner


class TestPrintBanner:
    """Tests for print_banner."""

    def test_banner_prints_version_and_model(self):
        """Banner output includes name, version, and model."""
        console = Console(record=True, force_terminal=False)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AIENG_BOT_NO_BANNER", None)
            print_banner(console)
        output = console.export_text()
        assert "aieng-bot" in output
        assert "Vector Institute AI Engineering" in output

    def test_banner_suppressed_by_env_var(self):
        """AIENG_BOT_NO_BANNER suppresses all banner output."""
        console = Console(record=True, force_terminal=False)
        with patch.dict(os.environ, {"AIENG_BOT_NO_BANNER": "1"}):
            print_banner(console)
        assert console.export_text() == ""


class TestCliGroup:
    """Tests for the top-level CLI group."""

    def test_no_subcommand_shows_help(self):
        """Invoking without a subcommand prints help."""
        runner = CliRunner()
        result = runner.invoke(cli, [], env={"AIENG_BOT_NO_BANNER": "1"})
        assert result.exit_code == 0
        assert "fix" in result.output

    def test_no_banner_flag(self):
        """--no-banner suppresses the banner but still shows help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--no-banner"])
        assert result.exit_code == 0
        assert "fix" in result.output

    def test_version_flag(self):
        """--version prints the version and exits."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "aieng-bot" in result.output
