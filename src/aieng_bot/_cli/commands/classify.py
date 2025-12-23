"""CLI command for PR failure classification."""

import json
import sys
import tempfile

import click
from rich.console import Console

from ...classifier import PRFailureClassifier
from ...classifier.models import ClassificationResult
from ...utils.logging import get_console, log_error, log_info, log_success
from ..utils import parse_pr_inputs


def _get_failure_logs_file(
    failure_logs: str | None, failure_logs_file: str | None
) -> str | None:
    """Get failure logs file path, return None on error."""
    if failure_logs_file:
        return failure_logs_file

    if failure_logs:
        # Write logs to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".txt"
        ) as temp_file:
            temp_file.write(failure_logs)
            return temp_file.name

    log_error("Either --failure-logs or --failure-logs-file must be provided")
    return None


def _output_results(
    result: ClassificationResult, output_format: str, console: Console
) -> None:
    """Output classification results in the specified format."""
    if output_format == "json":
        output = {
            "failure_type": result.failure_type.value,
            "confidence": result.confidence,
            "reasoning": result.reasoning,
            "failed_check_names": result.failed_check_names,
            "recommended_action": result.recommended_action,
        }
        console.print_json(data=output)
    else:  # github format - output for GITHUB_OUTPUT
        # Escape special characters to prevent bash interpretation
        # Replace backticks, dollar signs, and double quotes
        def escape_for_bash(s: str) -> str:
            return (
                s.replace("\\", "\\\\")
                .replace("`", "\\`")
                .replace("$", "\\$")
                .replace('"', '\\"')
            )

        reasoning_escaped = escape_for_bash(result.reasoning)
        action_escaped = escape_for_bash(result.recommended_action)

        # Create a stdout console for GitHub Actions output (stderr console is used for logging)
        stdout_console = Console(stderr=False, highlight=False)

        # Output to stdout for GitHub Actions to capture
        stdout_console.print(f"failure-type={result.failure_type.value}")
        stdout_console.print(f"confidence={result.confidence}")
        stdout_console.print(f"reasoning={reasoning_escaped}")
        stdout_console.print(
            f"failed-check-names={','.join(result.failed_check_names)}"
        )
        stdout_console.print(f"recommended-action={action_escaped}")


def _log_summary(result: ClassificationResult) -> None:
    """Log summary of classification result."""
    if result.failure_type.value != "unknown":
        log_success(
            f"Classified as [bold]{result.failure_type.value}[/bold] "
            f"(confidence: {result.confidence:.2f})"
        )
    else:
        log_error("Unable to classify failure (unknown type)")
        sys.exit(1)


@click.command()
@click.option(
    "--pr-info",
    required=True,
    help="PR info JSON string containing repo, pr_number, title, author, etc.",
)
@click.option(
    "--failed-checks",
    required=True,
    help="Failed checks JSON array with check names and conclusions",
)
@click.option(
    "--failure-logs",
    required=False,
    help="Failure logs content (truncated). Use --failure-logs-file for large logs.",
)
@click.option(
    "--failure-logs-file",
    required=False,
    type=click.Path(exists=True),
    help="Path to file containing failure logs (alternative to --failure-logs)",
)
@click.option(
    "--output-format",
    type=click.Choice(["json", "github"], case_sensitive=False),
    default="github",
    help="Output format: 'github' for GitHub Actions variables, 'json' for structured output",
)
def classify(
    pr_info: str,
    failed_checks: str,
    failure_logs: str | None,
    failure_logs_file: str | None,
    output_format: str,
) -> None:
    r"""Classify PR failure type using Claude API.

    Analyzes PR context, failed checks, and logs to determine failure category
    (test, lint, security, build, merge_conflict, unknown).

    Examples:
      \b
      # Classify with GitHub Actions output
      aieng-bot classify --pr-info '$PR_JSON' --failed-checks '$CHECKS_JSON' \\
        --failure-logs-file logs.txt

      \b
      # Classify with JSON output
      aieng-bot classify --pr-info '$PR_JSON' --failed-checks '$CHECKS_JSON' \\
        --failure-logs "$(cat logs.txt)" --output-format json

    """
    console = get_console()

    try:
        # Parse inputs - create argparse.Namespace for compatibility with parse_pr_inputs
        import argparse  # noqa: PLC0415

        args = argparse.Namespace(pr_info=pr_info, failed_checks=failed_checks)
        pr_context, failed_check_list = parse_pr_inputs(args)

        # Get failure logs file path
        failure_logs_path = _get_failure_logs_file(failure_logs, failure_logs_file)
        if not failure_logs_path:
            sys.exit(1)

        # Run classification
        log_info(f"Classifying PR {pr_context.repo}#{pr_context.pr_number}")
        log_info(f"Number of failed checks: {len(failed_check_list)}")
        log_info(f"Failure logs file: {failure_logs_path}")

        classifier = PRFailureClassifier()
        result = classifier.classify(pr_context, failed_check_list, failure_logs_path)

        log_info(
            f"Classification result: {result.failure_type.value} "
            f"(confidence: {result.confidence:.2f})"
        )

        # Output results
        _output_results(result, output_format, console)

        # Log summary
        _log_summary(result)

    except json.JSONDecodeError as e:
        log_error(f"Invalid JSON input: {e}")
        sys.exit(1)
    except KeyError as e:
        log_error(f"Missing required field in input: {e}")
        sys.exit(1)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        sys.exit(1)
