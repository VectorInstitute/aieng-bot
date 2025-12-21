"""CLI command for bot metrics collection."""

import argparse
import sys

from ...metrics import MetricsCollector
from ...utils.logging import log_error, log_info, log_success
from ..utils import get_version


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
