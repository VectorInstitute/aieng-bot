"""CLI entry points for aieng-bot-maintain."""

import argparse
import json
import os
import sys
from importlib.metadata import PackageNotFoundError, version

from .classifier import PRFailureClassifier
from .classifier.models import CheckFailure, PRContext
from .metrics import MetricsCollector
from .utils.logging import get_console, log_error, log_info, log_success


def get_version() -> str:
    """Get the installed version of the package.

    Returns
    -------
    str
        Version string from package metadata.

    """
    try:
        return version("aieng-bot-maintain")
    except PackageNotFoundError:
        return "unknown"


def _read_failure_logs(args: argparse.Namespace) -> str:
    """Read failure logs from file or command-line argument.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed command-line arguments.

    Returns
    -------
    str
        Failure logs content.

    """
    if args.failure_logs_file:
        log_info(f"Reading failure logs from file: {args.failure_logs_file}")
        try:
            with open(args.failure_logs_file, "r") as f:
                failure_logs = f.read()
            log_info(f"Read {len(failure_logs)} characters from file")
            return failure_logs
        except FileNotFoundError:
            log_error(f"Failure logs file not found: {args.failure_logs_file}")
            return ""
    elif args.failure_logs:
        return args.failure_logs
    else:
        log_error("Neither --failure-logs nor --failure-logs-file provided")
        return ""


def _parse_pr_inputs(
    args: argparse.Namespace,
) -> tuple[PRContext, list[CheckFailure]]:
    """Parse PR context and failed checks from command-line arguments.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed command-line arguments.

    Returns
    -------
    tuple[PRContext, list[CheckFailure]]
        Parsed PR context and list of failed checks.

    """
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

    return pr_context, failed_checks


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
        pr_context, failed_checks = _parse_pr_inputs(args)
        failure_logs = _read_failure_logs(args)

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


def collect_metrics_cli() -> None:
    """CLI entry point for bot metrics collection.

    Queries GitHub for bot PRs, calculates aggregate metrics, and saves results
    to JSON files with optional GCS upload.

    Notes
    -----
    Exits with code 1 on errors.

    """
    parser = argparse.ArgumentParser(
        prog="collect-bot-metrics",
        description="Collect bot PR metrics from GitHub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Collect last 30 days of metrics
  collect-bot-metrics --output /tmp/metrics.json

  # Collect with history and upload to GCS
  collect-bot-metrics --days 90 --output /tmp/latest.json \\
    --history /tmp/history.json --upload-to-gcs
        """,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {get_version()}",
        help="Show version number and exit",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to look back (default: 30)",
    )
    parser.add_argument(
        "--output",
        default="/tmp/bot_metrics_latest.json",
        help="Output file for latest metrics (default: /tmp/bot_metrics_latest.json)",
    )
    parser.add_argument(
        "--history",
        default="/tmp/bot_metrics_history.json",
        help="Output file for historical data (default: /tmp/bot_metrics_history.json)",
    )
    parser.add_argument(
        "--upload-to-gcs",
        action="store_true",
        help="Upload results to GCS",
    )
    parser.add_argument(
        "--gcs-bucket",
        default="bot-dashboard-vectorinstitute",
        help="GCS bucket name (default: bot-dashboard-vectorinstitute)",
    )

    args = parser.parse_args()

    try:
        print("=" * 60)
        print("Bot Metrics Collection")
        print("=" * 60)
        print(f"Looking back: {args.days} days")
        print("")

        # Initialize collector
        collector = MetricsCollector(days_back=args.days)

        # Query PRs
        log_info("Querying GitHub for bot PRs...")
        prs = collector.query_bot_prs()
        log_success(f"Found {len(prs)} bot PRs")
        print("")

        # Calculate metrics
        log_info("Calculating aggregate metrics...")
        metrics = collector.aggregate_metrics(prs)
        log_success("Metrics calculated")
        print("")

        # Print summary
        print("Summary:")
        print(f"  Total PRs: {metrics['stats']['total_prs_scanned']}")
        print(f"  Auto-merged: {metrics['stats']['prs_auto_merged']}")
        print(f"  Bot-fixed: {metrics['stats']['prs_bot_fixed']}")
        print(f"  Failed: {metrics['stats']['prs_failed']}")
        print(f"  Success rate: {metrics['stats']['success_rate']:.1%}")
        print(f"  Avg fix time: {metrics['stats']['avg_fix_time_hours']:.1f} hours")
        print("")

        # Save locally
        collector.save_metrics(metrics, args.output, args.history)
        print("")

        # Upload to GCS if requested
        if args.upload_to_gcs:
            log_info("Uploading to GCS...")
            collector.upload_to_gcs(
                args.output, args.gcs_bucket, "data/bot_metrics_latest.json"
            )
            collector.upload_to_gcs(
                args.history, args.gcs_bucket, "data/bot_metrics_history.json"
            )
            print("")

        log_success("Metrics collection complete")

    except Exception as e:
        log_error(f"Failed to collect metrics: {e}")
        sys.exit(1)


def process_repo_queue_cli() -> None:
    """CLI entry point for processing a repository's PR queue.

    Called by monitor-org-bot-prs.yml matrix job per repository.
    Loads or creates queue state, processes PRs sequentially, and handles
    timeout gracefully with state persistence.

    Notes
    -----
    Exits with code 1 on errors.

    """
    parser = argparse.ArgumentParser(
        prog="process-repo-queue",
        description="Process sequential PR queue for a repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process queue for a specific repository
  process-repo-queue --repo VectorInstitute/repo-name \\
    --workflow-run-id 1234567890 \\
    --all-prs '[{"repo": "VectorInstitute/repo-name", "number": 123, ...}]'
        """,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {get_version()}",
        help="Show version number and exit",
    )
    parser.add_argument("--repo", required=True, help="Repository name (owner/repo)")
    parser.add_argument(
        "--workflow-run-id", required=True, help="GitHub workflow run ID"
    )
    parser.add_argument(
        "--all-prs", required=True, help="JSON array of all discovered PRs"
    )

    args = parser.parse_args()

    try:
        all_prs = json.loads(args.all_prs)

        # Filter to this repo
        repo_prs = [pr for pr in all_prs if pr["repo"] == args.repo]

        log_info(f"Processing {len(repo_prs)} PRs for {args.repo}")

        # Initialize queue manager
        gh_token = os.environ.get("GH_TOKEN")
        if not gh_token:
            log_error("GH_TOKEN environment variable not set")
            sys.exit(1)

        from .auto_merger import QueueManager

        manager = QueueManager(gh_token=gh_token)

        # Load or create state
        state = manager.state_manager.load_state()

        if state and state.workflow_run_id == args.workflow_run_id:
            log_info("Resuming from existing state")
        else:
            log_info("Creating new queue state")
            state = manager.state_manager.create_initial_state(
                workflow_run_id=args.workflow_run_id,
                prs=repo_prs,
            )
            manager.state_manager.save_state(state)

        # Process this repo's queue
        completed = manager.process_repo_queue(args.repo, state)

        if completed:
            log_success(f"Completed all PRs in {args.repo}")

            # Clean up state if all repos done
            if len(state.completed_repos) == len(state.repo_queues):
                log_info("All repositories completed, cleaning up state")
                manager.state_manager.clear_state()
        else:
            log_info(f"Queue processing interrupted for {args.repo}, state saved")

    except json.JSONDecodeError as e:
        log_error(f"Invalid JSON input: {e}")
        sys.exit(1)
    except Exception as e:
        log_error(f"Failed to process queue: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    classify_pr_failure_cli()
