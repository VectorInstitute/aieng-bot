"""Tests for Rich logging helpers."""

from unittest.mock import patch

from rich.console import Console

from aieng_bot.utils.logging import (
    get_console,
    log_error,
    log_info,
    log_success,
    log_warning,
)


def _capture(func, message: str) -> str:
    """Run a log helper against a recording console and return its output."""
    console = Console(record=True, force_terminal=False, width=200)
    with patch("aieng_bot.utils.logging.console", console):
        func(message)
    return console.export_text()


class TestLoggingHelpers:
    """Tests for log_* helpers."""

    def test_get_console_returns_stderr_console(self):
        """The global console writes to stderr."""
        assert get_console().stderr is True

    def test_log_info_plain_message(self):
        """Plain messages are printed verbatim."""
        assert "hello world" in _capture(log_info, "hello world")

    def test_untrusted_markup_does_not_raise(self):
        """Messages containing Rich markup must not raise MarkupError."""
        hostile = 'preview: {"a": [1, 2]} [/bold] [/b]'
        for func in (log_info, log_success, log_warning, log_error):
            output = _capture(func, hostile)
            assert "[/bold]" in output

    def test_square_brackets_preserved(self):
        """Bracketed text (e.g. shell globs) is not swallowed as markup."""
        output = _capture(log_info, 'grep -r "x" [a-z].py')
        assert "[a-z].py" in output
