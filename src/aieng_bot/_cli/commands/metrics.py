"""CLI command for bot metrics collection."""

import sys

import click

from ...metrics import MetricsCollector
from ...utils.logging import log_error, log_info, log_success


@click.command()
@click.option(
    "--days",
    type=int,
    default=30,
    help="Number of days to look back for PR analysis (default: 30)",
)
@click.option(
    "--output",
    type=click.Path(),
    default="/tmp/bot_metrics_latest.json",
    help="Output file for latest metrics snapshot (default: /tmp/bot_metrics_latest.json)",
)
@click.option(
    "--history",
    type=click.Path(),
    default="/tmp/bot_metrics_history.json",
    help="Output file for historical data time series (default: /tmp/bot_metrics_history.json)",
)
@click.option(
    "--upload-to-gcs",
    is_flag=True,
    help="Upload results to Google Cloud Storage bucket",
)
@click.option(
    "--gcs-bucket",
    default="bot-dashboard-vectorinstitute",
    help="GCS bucket name for uploads (default: bot-dashboard-vectorinstitute)",
)
def metrics(
    days: int,
    output: str,
    history: str,
    upload_to_gcs: bool,
    gcs_bucket: str,
) -> None:
    r"""Collect bot PR metrics from GitHub.

    Queries GitHub for bot PRs (Dependabot, pre-commit-ci), calculates aggregate metrics
    including success rates, fix times, and failure types, then saves results to JSON files
    with optional GCS upload.

    Examples:
      \b
      # Collect last 30 days of metrics
      aieng-bot metrics --output /tmp/metrics.json

      \b
      # Collect 90 days with history and upload to GCS
      aieng-bot metrics --days 90 --output /tmp/latest.json \\
        --history /tmp/history.json --upload-to-gcs

    """
    try:
        log_info("=" * 60)
        log_info("Bot Metrics Collection")
        log_info("=" * 60)
        log_info(f"Looking back: {days} days")
        log_info("")

        # Initialize collector
        collector = MetricsCollector(days_back=days)

        # Query PRs
        log_info("Querying GitHub for bot PRs...")
        prs = collector.query_bot_prs()
        log_success(f"Found {len(prs)} bot PRs")
        log_info("")

        # Calculate metrics
        log_info("Calculating aggregate metrics...")
        metrics_data = collector.aggregate_metrics(prs)
        log_success("Metrics calculated")
        log_info("")

        # Print summary
        log_info("Summary:")
        log_info(f"  Total PRs: {metrics_data['stats']['total_prs_scanned']}")
        log_info(f"  Auto-merged: {metrics_data['stats']['prs_auto_merged']}")
        log_info(f"  Bot-fixed: {metrics_data['stats']['prs_bot_fixed']}")
        log_info(f"  Failed: {metrics_data['stats']['prs_failed']}")
        log_info(f"  Success rate: {metrics_data['stats']['success_rate']:.1%}")
        log_info(
            f"  Avg fix time: {metrics_data['stats']['avg_fix_time_hours']:.1f} hours"
        )
        log_info("")

        # Save locally
        collector.save_metrics(metrics_data, output, history)
        log_info("")

        # Upload to GCS if requested
        if upload_to_gcs:
            log_info("Uploading to GCS...")
            collector.upload_to_gcs(output, gcs_bucket, "data/bot_metrics_latest.json")
            collector.upload_to_gcs(
                history, gcs_bucket, "data/bot_metrics_history.json"
            )
            log_info("")

        log_success("Metrics collection complete")

    except Exception as e:
        log_error(f"Failed to collect metrics: {e}")
        sys.exit(1)
