"""Rich-click help configuration for aieng-bot CLI.

This module configures rich-click with Vector Institute branding colors
and provides consistent styling across all CLI commands.
"""

import rich_click as click

# Vector Institute color palette
VECTOR_MAGENTA = "#EB088A"  # Primary brand color
VECTOR_BLUE = "#0066CC"  # Primary blue
VECTOR_TEAL = "#00A0B0"  # Teal accent
VECTOR_ORANGE = "#FF6B35"  # Orange accent

# Configure rich-click styling
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.USE_MARKDOWN = False
click.rich_click.SHOW_ARGUMENTS = True
click.rich_click.SHOW_METAVARS_COLUMN = True
click.rich_click.APPEND_METAVARS_HELP = True
click.rich_click.GROUP_ARGUMENTS_OPTIONS = True

# Style the help headers
click.rich_click.STYLE_HELPTEXT = ""
click.rich_click.STYLE_HELPTEXT_FIRST_LINE = "bold"
click.rich_click.STYLE_HEADER_TEXT = f"bold {VECTOR_MAGENTA}"
click.rich_click.STYLE_FOOTER_TEXT = "dim"

# Style options and arguments
click.rich_click.STYLE_OPTION = f"bold {VECTOR_TEAL}"
click.rich_click.STYLE_ARGUMENT = f"bold {VECTOR_TEAL}"
click.rich_click.STYLE_COMMAND = f"bold {VECTOR_BLUE}"
click.rich_click.STYLE_SWITCH = f"bold {VECTOR_TEAL}"
click.rich_click.STYLE_METAVAR = "bold yellow"
click.rich_click.STYLE_METAVAR_APPEND = "dim yellow"
click.rich_click.STYLE_METAVAR_SEPARATOR = "dim"
click.rich_click.STYLE_USAGE = "bold"
click.rich_click.STYLE_USAGE_COMMAND = f"bold {VECTOR_MAGENTA}"
click.rich_click.STYLE_REQUIRED_SHORT = "bold red"
click.rich_click.STYLE_REQUIRED_LONG = "red dim"
click.rich_click.STYLE_OPTIONS_PANEL_BORDER = f"dim {VECTOR_TEAL}"
click.rich_click.STYLE_COMMANDS_PANEL_BORDER = f"dim {VECTOR_MAGENTA}"
click.rich_click.STYLE_ERRORS_PANEL_BORDER = "red"
click.rich_click.STYLE_ERRORS_SUGGESTION = "dim"

# Style option groups (for organizing options)
click.rich_click.OPTION_GROUPS = {
    "aieng-bot": [
        {
            "name": "Global Options",
            "options": ["--version", "--no-banner", "--help"],
        },
    ],
    "aieng-bot classify": [
        {
            "name": "Required",
            "options": ["--repo", "--pr"],
            "panel_styles": {"border_style": VECTOR_MAGENTA},
        },
        {
            "name": "Output Format",
            "options": ["--json", "--output"],
        },
        {
            "name": "Authentication",
            "options": ["--github-token", "--anthropic-api-key"],
        },
    ],
    "aieng-bot fix": [
        {
            "name": "Required",
            "options": ["--repo", "--pr"],
            "panel_styles": {"border_style": VECTOR_MAGENTA},
        },
        {
            "name": "Execution Control",
            "options": ["--max-retries", "--timeout-minutes", "--cwd"],
        },
        {
            "name": "Logging & Tracing",
            "options": ["--log", "--workflow-run-id", "--github-run-url"],
        },
        {
            "name": "Authentication",
            "options": ["--github-token", "--anthropic-api-key"],
        },
    ],
}

# Command groups for main help
click.rich_click.COMMAND_GROUPS = {
    "aieng-bot": [
        {
            "name": "Commands",
            "commands": ["classify", "fix"],
        },
    ],
}

# Error suggestions
click.rich_click.ERRORS_SUGGESTION = (
    "Try 'aieng-bot --help' for help.\n\n"
    "[dim]Report issues at: https://github.com/VectorInstitute/aieng-bot/issues[/dim]"
)
click.rich_click.ERRORS_EPILOGUE = ""


def format_examples_panel(examples: list[tuple[str, str]]) -> str:
    """Format examples as a Rich-styled panel for help text.

    Parameters
    ----------
    examples : list[tuple[str, str]]
        List of (description, command) tuples.

    Returns
    -------
    str
        Formatted examples string with Rich markup.

    """
    lines = []
    for description, command in examples:
        lines.append(f"  [dim]{description}[/dim]")
        lines.append(f"  [bold cyan]$ {command}[/bold cyan]")
        lines.append("")
    return "\n".join(lines).rstrip()


# Export configured click module
__all__ = [
    "click",
    "VECTOR_MAGENTA",
    "VECTOR_BLUE",
    "VECTOR_TEAL",
    "VECTOR_ORANGE",
    "format_examples_panel",
]
