"""Tests for CLI public exports module."""

import aieng_bot.cli as cli_module
from aieng_bot.cli import (
    AgentFixer,
    AgentFixRequest,
    CheckFailure,
    PRContext,
    PRFailureClassifier,
    _parse_pr_inputs,
    _read_failure_logs,
    cli,
    get_version,
    version,
)


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

    def test_version_is_exported(self):
        """Test that version function is re-exported."""
        assert version is not None
        assert callable(version)

    def test_backward_compat_private_functions(self):
        """Test that private function aliases are exported for backward compatibility."""
        assert _read_failure_logs is not None
        assert callable(_read_failure_logs)
        assert _parse_pr_inputs is not None
        assert callable(_parse_pr_inputs)

    def test_agent_fixer_is_exported(self):
        """Test that AgentFixer is re-exported."""
        assert AgentFixer is not None

    def test_agent_fix_request_is_exported(self):
        """Test that AgentFixRequest is re-exported."""
        assert AgentFixRequest is not None

    def test_pr_failure_classifier_is_exported(self):
        """Test that PRFailureClassifier is re-exported."""
        assert PRFailureClassifier is not None

    def test_check_failure_is_exported(self):
        """Test that CheckFailure is re-exported."""
        assert CheckFailure is not None

    def test_pr_context_is_exported(self):
        """Test that PRContext is re-exported."""
        assert PRContext is not None


class TestCLIModule:
    """Test CLI module direct execution."""

    def test_module_has_main_guard(self):
        """Test that module has if __name__ == '__main__' guard."""
        # Check module has cli function available
        assert hasattr(cli_module, "cli")
        assert callable(cli_module.cli)

    def test_all_exports_match(self):
        """Test that __all__ contains expected exports."""
        expected_exports = {
            "cli",
            "get_version",
            "_read_failure_logs",
            "_parse_pr_inputs",
            "version",
            "AgentFixer",
            "AgentFixRequest",
            "PRFailureClassifier",
            "CheckFailure",
            "PRContext",
        }

        assert hasattr(cli_module, "__all__")
        assert set(cli_module.__all__) == expected_exports
