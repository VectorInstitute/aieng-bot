"""CLI command for PR failure classification."""

import argparse
import json
import sys
import tempfile

from ...classifier import PRFailureClassifier
from ...classifier.models import ClassificationResult
from ...utils.logging import get_console, log_error, log_info, log_success
from ..utils import get_version, parse_pr_inputs


def _get_failure_logs_file(args: argparse.Namespace) -> str | None:
    """Get failure logs file path from args, return None on error."""
    if args.failure_logs_file:
        return args.failure_logs_file

    if args.failure_logs:
        # Backward compatibility: write logs to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".txt"
        ) as temp_file:
            temp_file.write(args.failure_logs)
            return temp_file.name

    log_error("Either --failure-logs or --failure-logs-file must be provided")
    return None


def _output_results(
    result: ClassificationResult, output_format: str, console: object
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
        console.print_json(data=output)  # type: ignore[attr-defined]
    else:  # github format - output for GITHUB_OUTPUT
        print(f"failure-type={result.failure_type.value}")
        print(f"confidence={result.confidence}")
        print(f"reasoning={result.reasoning}")
        print(f"failed-check-names={','.join(result.failed_check_names)}")
        print(f"recommended-action={result.recommended_action}")


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


def classify_pr_failure_cli() -> None:
    """CLI entry point for PR failure classification.

    Reads PR context, failed checks, and failure logs from command-line arguments
    and outputs classification results in GitHub Actions format or JSON.

    """
    parser = argparse.ArgumentParser(
        prog="classify-pr-failure",
        description="Classify PR failure type using Claude API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Classify with GitHub Actions output
  classify-pr-failure --pr-info '$PR_JSON' --failed-checks '$CHECKS_JSON' \\
    --failure-logs "$(cat logs.txt)"

  # Classify with JSON output
  classify-pr-failure --pr-info '$PR_JSON' --failed-checks '$CHECKS_JSON' \\
    --failure-logs "$(cat logs.txt)" --output-format json
        """,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {get_version()}",
        help="Show version number and exit",
    )
    parser.add_argument("--pr-info", required=True, help="PR info JSON string")
    parser.add_argument(
        "--failed-checks", required=True, help="Failed checks JSON array"
    )
    parser.add_argument(
        "--failure-logs", required=False, help="Failure logs (truncated)"
    )
    parser.add_argument(
        "--failure-logs-file",
        required=False,
        help="Path to file containing failure logs (alternative to --failure-logs)",
    )
    parser.add_argument(
        "--output-format",
        choices=["json", "github"],
        default="github",
        help="Output format (default: github)",
    )

    args = parser.parse_args()
    console = get_console()

    try:
        # Parse inputs
        pr_context, failed_checks = parse_pr_inputs(args)

        # Get failure logs file path
        failure_logs_file = _get_failure_logs_file(args)
        if not failure_logs_file:
            sys.exit(1)

        # Run classification
        log_info(f"Classifying PR {pr_context.repo}#{pr_context.pr_number}")
        log_info(f"Number of failed checks: {len(failed_checks)}")
        log_info(f"Failure logs file: {failure_logs_file}")

        classifier = PRFailureClassifier()
        result = classifier.classify(pr_context, failed_checks, failure_logs_file)

        log_info(
            f"Classification result: {result.failure_type.value} "
            f"(confidence: {result.confidence:.2f})"
        )

        # Output results
        _output_results(result, args.output_format, console)

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
