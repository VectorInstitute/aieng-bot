"""Tests for collect_metrics_cli command."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from aieng_bot_maintain.cli import collect_metrics_cli


class TestCollectMetricsCLI:
    """Test suite for collect_metrics_cli function."""

    @patch("aieng_bot_maintain.cli.MetricsCollector")
    @patch.object(sys, "argv", ["collect-bot-metrics", "--days", "7"])
    def test_collect_metrics_cli_basic(self, mock_collector_class):
        """Test basic CLI execution."""
        mock_collector = MagicMock()
        mock_collector.query_bot_prs.return_value = []
        mock_collector.aggregate_metrics.return_value = {
            "stats": {
                "total_prs_scanned": 0,
                "prs_auto_merged": 0,
                "prs_bot_fixed": 0,
                "prs_failed": 0,
                "success_rate": 0.0,
                "avg_fix_time_hours": 0.0,
            }
        }
        mock_collector_class.return_value = mock_collector

        collect_metrics_cli()

        mock_collector_class.assert_called_once_with(days_back=7)
        mock_collector.query_bot_prs.assert_called_once()
        mock_collector.aggregate_metrics.assert_called_once()

    @patch("aieng_bot_maintain.cli.MetricsCollector")
    @patch.object(
        sys,
        "argv",
        [
            "collect-bot-metrics",
            "--days",
            "30",
            "--output",
            "/tmp/test.json",
            "--upload-to-gcs",
        ],
    )
    def test_collect_metrics_cli_with_gcs(self, mock_collector_class):
        """Test CLI with GCS upload."""
        mock_collector = MagicMock()
        mock_collector.query_bot_prs.return_value = []
        mock_collector.aggregate_metrics.return_value = {
            "stats": {
                "total_prs_scanned": 0,
                "prs_auto_merged": 0,
                "prs_bot_fixed": 0,
                "prs_failed": 0,
                "success_rate": 0.0,
                "avg_fix_time_hours": 0.0,
            }
        }
        mock_collector_class.return_value = mock_collector

        collect_metrics_cli()

        mock_collector.upload_to_gcs.assert_called()

    @patch("aieng_bot_maintain.cli.MetricsCollector")
    @patch.object(sys, "argv", ["collect-bot-metrics"])
    def test_collect_metrics_cli_error(self, mock_collector_class):
        """Test CLI with error."""
        mock_collector_class.side_effect = Exception("Test error")

        with pytest.raises(SystemExit) as exc_info:
            collect_metrics_cli()

        assert exc_info.value.code == 1
