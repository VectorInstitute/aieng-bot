"""CLI entry points for aieng-bot-maintain."""

import argparse
import json
import sys

from .classifier import PRFailureClassifier
from .classifier.models import CheckFailure, PRContext
from .utils.logging import get_console, log_error, log_info, log_success


def classify_pr_failure_cli() -> None:
    """CLI entry point for PR failure classification.

    Reads PR context, failed checks, and failure logs from command-line arguments
    and outputs classification results in GitHub Actions format or JSON.

    """
    parser = argparse.ArgumentParser(
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
    parser.add_argument("--pr-info", required=True, help="PR info JSON string")
    parser.add_argument(
        "--failed-checks", required=True, help="Failed checks JSON array"
    )
    parser.add_argument(
        "--failure-logs", required=True, help="Failure logs (truncated)"
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
        pr_data = json.loads(args.pr_info)
        checks_data = json.loads(args.failed_checks)

        pr_context = PRContext(
            repo=pr_data["repo"],
            pr_number=int(pr_data["pr_number"]),
            pr_title=pr_data["pr_title"],
            pr_author=pr_data["pr_author"],
            base_ref=pr_data["base_ref"],
            head_ref=pr_data["head_ref"],
        )

        failed_checks = [
            CheckFailure(
                name=check["name"],
                conclusion=check["conclusion"],
                workflow_name=check.get("workflowName", ""),
                details_url=check.get("detailsUrl", ""),
                started_at=check.get("startedAt", ""),
                completed_at=check.get("completedAt", ""),
            )
            for check in checks_data
        ]

        # Run classification
        log_info(f"Classifying PR {pr_context.repo}#{pr_context.pr_number}")
        classifier = PRFailureClassifier()
        result = classifier.classify(pr_context, failed_checks, args.failure_logs)

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


if __name__ == "__main__":
    classify_pr_failure_cli()
