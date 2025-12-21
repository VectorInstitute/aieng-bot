"""CLI command for PR failure classification."""

import argparse
import json
import sys

from ...classifier import PRFailureClassifier
from ...utils.logging import get_console, log_error, log_info, log_success
from ..utils import get_version, parse_pr_inputs, read_failure_logs


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
        failure_logs = read_failure_logs(args)

        # Run classification
        log_info(f"Classifying PR {pr_context.repo}#{pr_context.pr_number}")
        log_info(f"Number of failed checks: {len(failed_checks)}")
        log_info(f"Failure logs length: {len(failure_logs)} characters")
        if failure_logs:
            log_info(f"First 200 chars of logs: {failure_logs[:200]}")
        classifier = PRFailureClassifier()
        result = classifier.classify(pr_context, failed_checks, failure_logs)
        log_info(
            f"Classification result: {result.failure_type.value} (confidence: {result.confidence:.2f})"
        )

        # Output results
        if args.output_format == "json":
            output = {
                "failure_type": result.failure_type.value,
                "confidence": result.confidence,
                "reasoning": result.reasoning,
                "failed_check_names": result.failed_check_names,
                "recommended_action": result.recommended_action,
            }
            console.print_json(data=output)
        else:  # github format - output for GITHUB_OUTPUT
            print(f"failure-type={result.failure_type.value}")
            print(f"confidence={result.confidence}")
            print(f"reasoning={result.reasoning}")
            print(f"failed-check-names={','.join(result.failed_check_names)}")
            print(f"recommended-action={result.recommended_action}")

        # Log summary
        if result.failure_type.value != "unknown":
            log_success(
                f"Classified as [bold]{result.failure_type.value}[/bold] "
                f"(confidence: {result.confidence:.2f})"
            )
        else:
            log_error("Unable to classify failure (unknown type)")
            sys.exit(1)

    except json.JSONDecodeError as e:
        log_error(f"Invalid JSON input: {e}")
        sys.exit(1)
    except KeyError as e:
        log_error(f"Missing required field in input: {e}")
        sys.exit(1)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        sys.exit(1)
