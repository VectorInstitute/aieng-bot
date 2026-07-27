"""Tests for CLI public exports module."""

import aieng_bot.cli as cli_module
from aieng_bot.cli import cli, get_version


class TestCLIExports:
    """Test suite for CLI module exports."""

    def test_cli_is_exported(self):
        """Test that cli entry point is exported."""
        assert cli is not None
        assert callable(cli)

    def test_get_version_is_exported(self):
        """Test that get_version function is exported."""
        assert get_version is not None
        assert callable(get_version)

    def test_all_exports_match(self):
        """Test that __all__ contains expected exports."""
        assert set(cli_module.__all__) == {"cli", "get_version"}
