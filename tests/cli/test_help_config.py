"""Tests for CLI help configuration module."""

import os
from unittest.mock import patch

from click.testing import CliRunner

from aieng_bot._cli.help_config import (
    VECTOR_BLUE,
    VECTOR_MAGENTA,
    VECTOR_ORANGE,
    VECTOR_TEAL,
    format_examples_panel,
)
from aieng_bot._cli.main import cli


class TestVectorColors:
    """Test suite for Vector Institute color constants."""

    def test_vector_magenta_is_hex(self):
        """Test that Vector magenta is a valid hex color."""
        assert VECTOR_MAGENTA.startswith("#")
        assert len(VECTOR_MAGENTA) == 7
        assert VECTOR_MAGENTA == "#EB088A"

    def test_vector_blue_is_hex(self):
        """Test that Vector blue is a valid hex color."""
        assert VECTOR_BLUE.startswith("#")
        assert len(VECTOR_BLUE) == 7
        assert VECTOR_BLUE == "#0066CC"

    def test_vector_teal_is_hex(self):
        """Test that Vector teal is a valid hex color."""
        assert VECTOR_TEAL.startswith("#")
        assert len(VECTOR_TEAL) == 7
        assert VECTOR_TEAL == "#00A0B0"

    def test_vector_orange_is_hex(self):
        """Test that Vector orange is a valid hex color."""
        assert VECTOR_ORANGE.startswith("#")
        assert len(VECTOR_ORANGE) == 7
        assert VECTOR_ORANGE == "#FF6B35"

    def test_all_colors_are_unique(self):
        """Test that all color constants are unique."""
        colors = [VECTOR_MAGENTA, VECTOR_BLUE, VECTOR_TEAL, VECTOR_ORANGE]
        assert len(colors) == len(set(colors))


class TestFormatExamplesPanel:
    """Test suite for format_examples_panel function."""

    def test_format_single_example(self):
        """Test formatting a single example."""
        examples = [("Classify a PR", "aieng-bot classify --repo owner/repo --pr 1")]
        result = format_examples_panel(examples)

        assert "Classify a PR" in result
        assert "aieng-bot classify --repo owner/repo --pr 1" in result
        assert "[dim]" in result
        assert "[bold cyan]" in result

    def test_format_multiple_examples(self):
        """Test formatting multiple examples."""
        examples = [
            ("Basic usage", "aieng-bot fix --repo owner/repo --pr 1"),
            ("With logging", "aieng-bot fix --repo owner/repo --pr 1 --log"),
        ]
        result = format_examples_panel(examples)

        assert "Basic usage" in result
        assert "With logging" in result
        assert "aieng-bot fix" in result
        assert "--log" in result

    def test_format_empty_examples(self):
        """Test formatting empty examples list."""
        result = format_examples_panel([])
        assert result == ""

    def test_format_examples_has_dollar_sign(self):
        """Test that examples have $ prefix for commands."""
        examples = [("Test", "echo hello")]
        result = format_examples_panel(examples)
        assert "$ echo hello" in result

    def test_format_examples_strips_trailing_whitespace(self):
        """Test that trailing whitespace is stripped."""
        examples = [("Test", "command")]
        result = format_examples_panel(examples)
        assert not result.endswith("\n")


class TestRichClickHelp:
    """Test suite for rich-click help output."""

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    def test_main_help_shows_commands(self):
        """Test that main help shows available commands."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "classify" in result.output
        assert "fix" in result.output

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    def test_main_help_shows_options(self):
        """Test that main help shows global options."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "--version" in result.output
        assert "--no-banner" in result.output

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    def test_classify_help_shows_options(self):
        """Test that classify help shows all options."""
        runner = CliRunner()
        result = runner.invoke(cli, ["classify", "--help"])

        assert result.exit_code == 0
        assert "--repo" in result.output
        assert "--pr" in result.output
        assert "--json" in result.output
        assert "--output" in result.output
        assert "--github-token" in result.output
        assert "--anthropic-api-key" in result.output

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    def test_classify_help_shows_description(self):
        """Test that classify help shows command description."""
        runner = CliRunner()
        result = runner.invoke(cli, ["classify", "--help"])

        assert result.exit_code == 0
        assert "Classify PR failure type" in result.output

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    def test_fix_help_shows_options(self):
        """Test that fix help shows all options."""
        runner = CliRunner()
        result = runner.invoke(cli, ["fix", "--help"])

        assert result.exit_code == 0
        assert "--repo" in result.output
        assert "--pr" in result.output
        assert "--max-retries" in result.output
        assert "--timeout-minutes" in result.output
        assert "--cwd" in result.output
        assert "--log" in result.output

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    def test_fix_help_shows_description(self):
        """Test that fix help shows command description."""
        runner = CliRunner()
        result = runner.invoke(cli, ["fix", "--help"])

        assert result.exit_code == 0
        assert "Fix and merge a PR" in result.output

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    def test_help_shows_examples(self):
        """Test that help output shows examples."""
        runner = CliRunner()
        result = runner.invoke(cli, ["fix", "--help"])

        assert result.exit_code == 0
        # Check for example-related content
        assert "aieng-bot fix" in result.output

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    def test_help_shows_env_vars(self):
        """Test that help output mentions environment variables."""
        runner = CliRunner()
        result = runner.invoke(cli, ["classify", "--help"])

        assert result.exit_code == 0
        assert "ANTHROPIC_API_KEY" in result.output
        assert "GITHUB_TOKEN" in result.output

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    def test_no_banner_flag_accepted(self):
        """Test that --no-banner flag is accepted."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--no-banner", "--help"])

        assert result.exit_code == 0

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    def test_main_help_mentions_vector_institute(self):
        """Test that help mentions Vector Institute."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "Vector Institute" in result.output

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    def test_classify_help_mentions_failure_types(self):
        """Test that classify help mentions failure types."""
        runner = CliRunner()
        result = runner.invoke(cli, ["classify", "--help"])

        assert result.exit_code == 0
        # Check that at least some failure types are mentioned
        output_lower = result.output.lower()
        assert "test" in output_lower or "lint" in output_lower

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "GITHUB_TOKEN": "gh-token"},
        clear=True,
    )
    def test_fix_help_mentions_workflow(self):
        """Test that fix help mentions the workflow steps."""
        runner = CliRunner()
        result = runner.invoke(cli, ["fix", "--help"])

        assert result.exit_code == 0
        output_lower = result.output.lower()
        # Check for workflow-related terms
        assert "analyze" in output_lower or "fix" in output_lower
