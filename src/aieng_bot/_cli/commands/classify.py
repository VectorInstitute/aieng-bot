"""CLI command for PR failure classification."""

import contextlib
import json
import os
import sys
import traceback
from typing import Any

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ...classifier import PRFailureClassifier
from ...classifier.models import ClassificationResult, FailureType
from ...utils.github_client import GitHubClient
from ...utils.logging import get_console, log_error, log_info, log_success, log_warning

# Load .env file at module import time (before Click processes envvars)
load_dotenv()


def _check_environment_variables() -> tuple[bool, list[str]]:
    """Check if required environment variables are set.

    Returns
    -------
    tuple[bool, list[str]]
        (all_set, missing_vars) - True if all vars set, list of missing var names

    """
    required_vars = {
        "ANTHROPIC_API_KEY": "Get from https://console.anthropic.com/settings/keys",
        "GITHUB_TOKEN": "GitHub personal access token (or GH_TOKEN)",
    }

    missing = []
    for var, description in required_vars.items():
        if var == "GITHUB_TOKEN":
            # Check both GITHUB_TOKEN and GH_TOKEN
            if not os.environ.get("GITHUB_TOKEN") and not os.environ.get("GH_TOKEN"):
                missing.append(f"{var} (or GH_TOKEN): {description}")
        elif not os.environ.get(var):
            missing.append(f"{var}: {description}")

    return len(missing) == 0, missing


def _output_rich_format(result: ClassificationResult, console: Console) -> None:
    """Output classification results in Rich formatted style for terminal.

    Parameters
    ----------
    result : ClassificationResult
        Classification result to display.
    console : Console
        Rich console for output.

    """
    # Determine status color based on Vector Institute branding
    # Vector colors: primary blue (#0066CC), teal (#00A0B0), orange (#FF6B35)
    if result.failure_type == FailureType.UNKNOWN:
        status_color = "yellow"
        status_text = "UNKNOWN"
    elif result.confidence < 0.7:
        status_color = "yellow"
        status_text = result.failure_type.value.upper()
    else:
        status_color = "bright_cyan"  # Vector teal
        status_text = result.failure_type.value.upper()

    # Build unified content
    content = Text()

    # Classification Result section
    content.append("Classification Result\n", style="bold bright_blue")
    content.append("─" * 60 + "\n", style="bright_blue dim")
    content.append("Failure Type:   ", style="dim")
    content.append(f"{status_text}\n", style=f"{status_color} bold")
    content.append("Confidence:     ", style="dim")
    content.append(f"{result.confidence:.1%}\n", style="white")

    if result.failed_check_names:
        content.append("Failed Checks:  ", style="dim")
        content.append(f"{', '.join(result.failed_check_names)}\n", style="white")

    content.append("\n")

    # Reasoning section
    content.append("Reasoning\n", style="bold #00A0B0")  # Vector teal
    content.append("─" * 60 + "\n", style="#00A0B0 dim")
    content.append(f"{result.reasoning}\n\n", style="white")

    # Recommended Action section
    content.append("Recommended Action\n", style="bold #FF6B35")  # Vector orange
    content.append("─" * 60 + "\n", style="#FF6B35 dim")
    content.append(f"{result.recommended_action}", style="white")

    # Print in one unified panel
    console.print()
    console.print(
        Panel(
            content,
            border_style="bright_blue",
            padding=(1, 2),
        )
    )
    console.print()


def _get_json_output(result: ClassificationResult) -> dict[str, Any]:
    """Get classification result as JSON dict.

    Parameters
    ----------
    result : ClassificationResult
        Classification result to convert.

    Returns
    -------
    dict
        JSON-serializable dictionary.

    """
    return {
        "failure_type": result.failure_type.value,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "failed_check_names": result.failed_check_names,
        "recommended_action": result.recommended_action,
    }


def _output_json_format(
    result: ClassificationResult, console: Console, output_file: str | None = None
) -> None:
    """Output classification results in JSON format.

    Parameters
    ----------
    result : ClassificationResult
        Classification result to output.
    console : Console
        Rich console for output.
    output_file : str, optional
        If provided, write JSON to this file instead of stdout.

    """
    output = _get_json_output(result)

    if output_file:
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)
        log_success(f"Classification result saved to {output_file}")
    else:
        console.print_json(data=output)


def _output_result(
    result: ClassificationResult,
    console: Console,
    json_output: bool,
    output_file: str | None,
) -> None:
    """Output classification result in the requested format.

    Parameters
    ----------
    result : ClassificationResult
        Classification result to output.
    console : Console
        Rich console for output.
    json_output : bool
        Whether to output as JSON.
    output_file : str, optional
        File path for JSON output.

    """
    if json_output or output_file:
        _output_json_format(result, console, output_file)
    else:
        _output_rich_format(result, console)


def _handle_merge_conflict(
    console: Console, json_output: bool, output_file: str | None
) -> None:
    """Handle merge conflict case and exit.

    Parameters
    ----------
    console : Console
        Rich console for output.
    json_output : bool
        Whether to output as JSON.
    output_file : str, optional
        File path for JSON output.

    """
    log_warning("PR has merge conflicts")
    result = ClassificationResult(
        failure_type=FailureType.MERGE_CONFLICT,
        confidence=1.0,
        reasoning="PR has merge conflicts with base branch (mergeable=CONFLICTING)",
        failed_check_names=["merge-conflict"],
        recommended_action="Resolve merge conflicts manually or use automated conflict resolution",
    )
    _output_result(result, console, json_output, output_file)
    sys.exit(0)


def _handle_no_failed_checks(
    console: Console, json_output: bool, output_file: str | None
) -> None:
    """Handle no failed checks case and exit.

    Parameters
    ----------
    console : Console
        Rich console for output.
    json_output : bool
        Whether to output as JSON.
    output_file : str, optional
        File path for JSON output.

    """
    log_warning("No failed checks found on this PR")
    result = ClassificationResult(
        failure_type=FailureType.UNKNOWN,
        confidence=0.0,
        reasoning="No failed CI checks found on this PR",
        failed_check_names=[],
        recommended_action="Verify that CI checks are configured and have run",
    )
    _output_result(result, console, json_output, output_file)
    sys.exit(0)


@click.command()
@click.option(
    "--repo",
    required=True,
    help="Repository in format 'owner/repo' (e.g., VectorInstitute/aieng-template-mvp)",
)
@click.option(
    "--pr",
    "pr_number",
    required=True,
    type=int,
    help="Pull request number to classify",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output in JSON format to stdout (default: Rich formatted for terminal)",
)
@click.option(
    "--output",
    "output_file",
    type=click.Path(),
    help="Save JSON result to file (e.g., classification.json)",
)
@click.option(
    "--github-token",
    envvar="GITHUB_TOKEN",
    help="GitHub token (or set GITHUB_TOKEN/GH_TOKEN env var)",
)
@click.option(
    "--anthropic-api-key",
    envvar="ANTHROPIC_API_KEY",
    help="Anthropic API key (or set ANTHROPIC_API_KEY env var)",
)
def classify(
    repo: str,
    pr_number: int,
    json_output: bool,
    output_file: str | None,
    github_token: str | None,
    anthropic_api_key: str | None,
) -> None:
    """Classify PR failure type.

    Analyzes a GitHub PR to determine the type of CI/CD failure
    (test, lint, security, build, merge_conflict, or unknown).

    \b
    Examples:
    \b
      # Rich formatted output (default)
      aieng-bot classify --repo VectorInstitute/aieng-template-mvp --pr 17
    \b
      # JSON output to stdout
      aieng-bot classify --repo VectorInstitute/repo-name --pr 123 --json
    \b
      # Save JSON to file
      aieng-bot classify --repo owner/repo --pr 42 --output classification.json

    \b
    Required Environment Variables:
      ANTHROPIC_API_KEY  - Claude API key (https://console.anthropic.com)
      GITHUB_TOKEN       - GitHub token (or GH_TOKEN)

    """
    console = get_console()

    # Check environment variables
    env_ok, missing_vars = _check_environment_variables()
    if not env_ok:
        log_error("Missing required environment variables:")
        for var_info in missing_vars:
            console.print(f"  • {var_info}", style="red")
        console.print()
        console.print(
            "💡 Tip: Create a .env file with these variables or export them in your shell",
            style="yellow",
        )
        sys.exit(1)

    try:
        # Initialize GitHub client
        log_info(f"Analyzing PR {repo}#{pr_number}")
        github_client = GitHubClient(github_token=github_token)

        # Check for merge conflicts first (fast path)
        if github_client.check_merge_conflicts(repo, pr_number):
            _handle_merge_conflict(console, json_output, output_file)

        # Fetch PR details
        pr_context = github_client.get_pr_details(repo, pr_number)
        log_success(f"PR: {pr_context.pr_title}")
        log_info(f"Author: {pr_context.pr_author}")
        log_info(f"Branch: {pr_context.head_ref} → {pr_context.base_ref}")

        # Fetch failed checks
        failed_checks = github_client.get_failed_checks(repo, pr_number)
        if not failed_checks:
            _handle_no_failed_checks(console, json_output, output_file)

        log_info(f"Found {len(failed_checks)} failed checks")
        for check in failed_checks:
            log_info(f"  • {check.name}")

        # Fetch failure logs (full logs, no truncation)
        failure_logs_file = github_client.get_failure_logs(repo, failed_checks)

        # Run classification
        log_info("Classifying failure type using Claude AI...")
        classifier = PRFailureClassifier(api_key=anthropic_api_key)
        result = classifier.classify(pr_context, failed_checks, failure_logs_file)

        # Clean up temp log file
        with contextlib.suppress(Exception):
            os.unlink(failure_logs_file)

        # Output result
        _output_result(result, console, json_output, output_file)

        # Exit with error code if classification failed
        if result.failure_type == FailureType.UNKNOWN:
            sys.exit(1)

    except ValueError as e:
        log_error(str(e))
        sys.exit(1)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        console.print(traceback.format_exc(), style="red dim")
        sys.exit(1)
