"""Logging utilities using Rich console."""

from rich.console import Console

# Global console instance
console = Console()


def get_console() -> Console:
    """Get the global Rich console instance.

    Returns:
        Console instance for formatted output.

    """
    return console


def log_info(message: str) -> None:
    """Log an informational message.

    Args:
        message: Message to log.

    """
    console.print(f"[blue]ℹ[/blue] {message}")


def log_success(message: str) -> None:
    """Log a success message.

    Args:
        message: Message to log.

    """
    console.print(f"[green]✓[/green] {message}")


def log_warning(message: str) -> None:
    """Log a warning message.

    Args:
        message: Message to log.

    """
    console.print(f"[yellow]⚠[/yellow] {message}", style="yellow")


def log_error(message: str) -> None:
    """Log an error message.

    Args:
        message: Message to log.

    """
    console.print(f"[red]✗[/red] {message}", style="bold red")
