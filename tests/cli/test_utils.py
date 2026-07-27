"""Tests for CLI utility functions."""

from unittest.mock import patch

from aieng_bot._cli.utils import get_version


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
