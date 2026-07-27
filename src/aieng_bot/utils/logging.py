"""Logging utilities using Rich console."""

from rich.console import Console
from rich.markup import escape

# Global console instance - write to stderr to avoid interfering with stdout
console = Console(stderr=True)


def get_console() -> Console:
    """Get the global Rich console instance.

    Returns:
        Console instance for formatted output.

    """
    return console


def log_info(message: str) -> None:
    """Log an informational message.

    Args:
        message: Message to log. Treated as plain text, not Rich markup.

    """
    console.print(f"[blue]ℹ[/blue] {escape(message)}")


def log_success(message: str) -> None:
    """Log a success message.

    Args:
        message: Message to log. Treated as plain text, not Rich markup.

    """
    console.print(f"[green]✓[/green] {escape(message)}")


def log_warning(message: str) -> None:
    """Log a warning message.

    Args:
        message: Message to log. Treated as plain text, not Rich markup.

    """
    console.print(f"[yellow]⚠[/yellow] {escape(message)}", style="yellow")


def log_error(message: str) -> None:
    """Log an error message.

    Args:
        message: Message to log. Treated as plain text, not Rich markup.

    """
    console.print(f"[red]✗[/red] {escape(message)}", style="bold red")
