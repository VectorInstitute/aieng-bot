"""Main CLI entry point for aieng-bot."""

import os

from rich.console import Console
from rich.text import Text

from ..config import get_model_name
from ..utils.logging import get_console
from .commands.fix import fix
from .help_config import VECTOR_MAGENTA, click
from .utils import get_version


def print_banner(console: Console) -> None:
    """Print ASCII art banner using Rich.

    Parameters
    ----------
    console : Console
        Rich console instance for output.

    """
    if os.environ.get("AIENG_BOT_NO_BANNER"):
        return

    version_str = get_version()
    model_name = get_model_name()

    # Sleek robot ASCII art with antennae
    line0 = Text()
    line0.append("  ◦   ◦  ", style="#EB088A bold")
    line0.append("   aieng-bot ", style="white bold")
    line0.append(f"v{version_str}", style="bright_black")

    line1 = Text()
    line1.append(" ┌─────┐ ", style="#EB088A bold")

    line2 = Text()
    line2.append(" │ ◉ ◉ │ ", style="#EB088A bold")
    line2.append("   ", style="")
    line2.append(model_name, style="cyan")

    line3 = Text()
    line3.append(" └──‿──┘ ", style="#EB088A bold")
    line3.append("   Vector Institute AI Engineering", style="bright_black")

    console.print()
    console.print(line0)
    console.print(line1)
    console.print(line2)
    console.print(line3)
    console.print()


def version_callback(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    """Show version and exit.

    Parameters
    ----------
    ctx : click.Context
        Click context.
    _param : click.Parameter
        Click parameter (unused).
    value : bool
        Whether --version flag was provided.

    """
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"aieng-bot {get_version()}")
    ctx.exit()


@click.group(
    invoke_without_command=True,
)
@click.rich_config(
    help_config=click.RichHelpConfiguration(
        width=100,
        show_arguments=True,
        show_metavars_column=True,
        append_metavars_help=True,
        style_option=f"bold {VECTOR_MAGENTA}",
        style_command="bold cyan",
        style_usage_command=f"bold {VECTOR_MAGENTA}",
    )
)
@click.option(
    "--version",
    is_flag=True,
    callback=version_callback,
    expose_value=False,
    is_eager=True,
    help="Show version and exit.",
)
@click.option(
    "--no-banner",
    is_flag=True,
    help="Disable ASCII art banner.",
)
@click.pass_context
def cli(ctx: click.Context, no_banner: bool) -> None:
    """AI Engineering Bot.

    Autonomously fixes CI failures, resolves merge conflicts, and merges GitHub PRs
    using Claude AI.

    \b
    Commands:
      fix       Autonomously fix a PR and merge it

    \b
    Examples:
      # Fix and merge a PR
      $ aieng-bot fix --repo owner/repo --pr 42

    \b
      # Fix with dashboard logging
      $ aieng-bot fix --repo owner/repo --pr 42 --log

    Use 'aieng-bot COMMAND --help' for command-specific help.
    """
    # Store in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["no_banner"] = no_banner

    # Show banner only if no subcommand and not disabled
    if ctx.invoked_subcommand is None:
        console = get_console()
        if not no_banner:
            print_banner(console)
        click.echo(ctx.get_help())


# Register subcommands
cli.add_command(fix)


if __name__ == "__main__":
    cli()
