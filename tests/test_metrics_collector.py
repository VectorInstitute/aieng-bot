"""Tests for metrics collection module."""

import json
import subprocess
from unittest.mock import MagicMock, mock_open, patch

import pytest

from aieng_bot_maintain.metrics import MetricsCollector


@pytest.fixture
def sample_pr_auto_merged():
    """Create sample auto-merged PR data."""
    return {
        "repository": {"nameWithOwner": "VectorInstitute/test-repo"},
        "number": 123,
        "title": "Bump package version",
        "author": {"login": "dependabot[bot]"},
        "createdAt": "2025-01-01T10:00:00Z",
        "mergedAt": "2025-01-01T12:00:00Z",
        "closedAt": "2025-01-01T12:00:00Z",
        "state": "MERGED",
        "commits": {"nodes": []},
        "statusCheckRollup": {
            "contexts": {
                "nodes": [
                    {"name": "test", "conclusion": "SUCCESS"},
                ]
            }
        },
    }


@pytest.fixture
def sample_pr_bot_fixed():
    """Create sample bot-fixed PR data."""
    return {
        "repository": {"nameWithOwner": "VectorInstitute/test-repo"},
        "number": 124,
        "title": "Bump dependency",
        "author": {"login": "dependabot[bot]"},
        "createdAt": "2025-01-01T10:00:00Z",
        "mergedAt": "2025-01-01T14:00:00Z",
        "closedAt": "2025-01-01T14:00:00Z",
        "state": "MERGED",
        "commits": {
            "nodes": [
                {
                    "commit": {
                        "author": {
                            "name": "aieng-bot-maintain[bot]",
                            "email": "aieng-bot@vectorinstitute.ai",
                        },
                        "message": "Fix test failures",
                    }
                }
            ]
        },
        "statusCheckRollup": {
            "contexts": {
                "nodes": [
                    {"name": "pytest", "conclusion": "FAILURE"},
                ]
            }
        },
    }


@pytest.fixture
def sample_pr_failed():
    """Create sample failed PR data."""
    return {
        "repository": {"nameWithOwner": "VectorInstitute/test-repo"},
        "number": 125,
        "title": "Update dependency",
        "author": {"login": "dependabot[bot]"},
        "createdAt": "2025-01-01T10:00:00Z",
        "mergedAt": None,
        "closedAt": "2025-01-01T11:00:00Z",
        "state": "CLOSED",
        "commits": {"nodes": []},
        "statusCheckRollup": {
            "contexts": {
                "nodes": [
                    {"name": "security-audit", "conclusion": "FAILURE"},
                ]
            }
        },
    }


@pytest.fixture
def collector():
    """Create a MetricsCollector instance."""
    return MetricsCollector(days_back=30)


class TestMetricsCollector:
    """Test suite for MetricsCollector class."""

    def test_init(self):
        """Test MetricsCollector initialization."""
        collector = MetricsCollector(days_back=7)
        assert collector.days_back == 7

    def test_init_default(self):
        """Test MetricsCollector initialization with defaults."""
        collector = MetricsCollector()
        assert collector.days_back == 30

    @patch("subprocess.run")
    def test_query_bot_prs_success(self, mock_run, collector):
        """Test successful PR query."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(
            {"search": {"edges": [{"node": {"number": 123}}]}}
        )
        mock_run.return_value = mock_result

        prs = collector.query_bot_prs()

        assert len(prs) == 1
        assert prs[0]["number"] == 123
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_query_bot_prs_api_error(self, mock_run, collector, capsys):
        """Test PR query with API error."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "gh", stderr="API error"
        )

        prs = collector.query_bot_prs()

        assert prs == []
        captured = capsys.readouterr()
        assert "Error querying GitHub API" in captured.out

    @patch("subprocess.run")
    def test_query_bot_prs_json_decode_error(self, mock_run, collector, capsys):
        """Test PR query with invalid JSON."""
        mock_result = MagicMock()
        mock_result.stdout = "invalid json"
        mock_run.return_value = mock_result

        prs = collector.query_bot_prs()

        assert prs == []
        captured = capsys.readouterr()
        assert "Error parsing GitHub API response" in captured.out

    def test_classify_pr_status_open(self, collector):
        """Test classification of open PR."""
        pr = {"state": "OPEN", "mergedAt": None}
        assert collector.classify_pr_status(pr) == "open"

    def test_classify_pr_status_auto_merged(self, collector, sample_pr_auto_merged):
        """Test classification of auto-merged PR."""
        assert collector.classify_pr_status(sample_pr_auto_merged) == "auto_merged"

    def test_classify_pr_status_bot_fixed(self, collector, sample_pr_bot_fixed):
        """Test classification of bot-fixed PR."""
        assert collector.classify_pr_status(sample_pr_bot_fixed) == "bot_fixed"

    def test_classify_pr_status_failed(self, collector, sample_pr_failed):
        """Test classification of failed PR."""
        assert collector.classify_pr_status(sample_pr_failed) == "failed"

    def test_analyze_failure_type_test(self, collector):
        """Test failure type analysis for test failures."""
        pr = {
            "statusCheckRollup": {
                "contexts": {
                    "nodes": [
                        {"name": "pytest", "conclusion": "FAILURE"},
                        {"name": "test-suite", "conclusion": "FAILURE"},
                    ]
                }
            }
        }
        assert collector.analyze_failure_type(pr) == "test"

    def test_analyze_failure_type_lint(self, collector):
        """Test failure type analysis for lint failures."""
        pr = {
            "statusCheckRollup": {
                "contexts": {
                    "nodes": [
                        {"name": "eslint", "conclusion": "FAILURE"},
                        {"name": "pre-commit", "conclusion": "FAILURE"},
                    ]
                }
            }
        }
        assert collector.analyze_failure_type(pr) == "lint"

    def test_analyze_failure_type_security(self, collector):
        """Test failure type analysis for security failures."""
        pr = {
            "statusCheckRollup": {
                "contexts": {
                    "nodes": [
                        {"name": "pip-audit", "conclusion": "FAILURE"},
                    ]
                }
            }
        }
        assert collector.analyze_failure_type(pr) == "security"

    def test_analyze_failure_type_build(self, collector):
        """Test failure type analysis for build failures."""
        pr = {
            "statusCheckRollup": {
                "contexts": {
                    "nodes": [
                        {"name": "webpack", "conclusion": "FAILURE"},
                    ]
                }
            }
        }
        assert collector.analyze_failure_type(pr) == "build"

    def test_analyze_failure_type_unknown(self, collector):
        """Test failure type analysis for unknown failures."""
        pr = {
            "statusCheckRollup": {
                "contexts": {
                    "nodes": [
                        {"name": "custom-check", "conclusion": "FAILURE"},
                    ]
                }
            }
        }
        assert collector.analyze_failure_type(pr) == "unknown"

    def test_analyze_failure_type_none(self, collector):
        """Test failure type analysis with no failures."""
        pr = {
            "statusCheckRollup": {
                "contexts": {
                    "nodes": [
                        {"name": "test", "conclusion": "SUCCESS"},
                    ]
                }
            }
        }
        assert collector.analyze_failure_type(pr) is None

    def test_calculate_fix_time(self, collector):
        """Test fix time calculation."""
        pr = {
            "createdAt": "2025-01-01T10:00:00Z",
            "mergedAt": "2025-01-01T12:00:00Z",
        }
        fix_time = collector.calculate_fix_time(pr)
        assert fix_time == 2.0

    def test_calculate_fix_time_not_merged(self, collector):
        """Test fix time calculation for unmerged PR."""
        pr = {
            "createdAt": "2025-01-01T10:00:00Z",
            "mergedAt": None,
        }
        assert collector.calculate_fix_time(pr) is None

    def test_aggregate_metrics(
        self, collector, sample_pr_auto_merged, sample_pr_bot_fixed, sample_pr_failed
    ):
        """Test metrics aggregation."""
        prs = [sample_pr_auto_merged, sample_pr_bot_fixed, sample_pr_failed]
        metrics = collector.aggregate_metrics(prs)

        assert metrics["stats"]["total_prs_scanned"] == 3
        assert metrics["stats"]["prs_auto_merged"] == 1
        assert metrics["stats"]["prs_bot_fixed"] == 1
        assert metrics["stats"]["prs_failed"] == 1
        assert metrics["stats"]["success_rate"] == 0.667  # 2/3

    def test_aggregate_metrics_empty(self, collector):
        """Test metrics aggregation with empty list."""
        metrics = collector.aggregate_metrics([])

        assert metrics["stats"]["total_prs_scanned"] == 0
        assert metrics["stats"]["success_rate"] == 0.0

    @patch("os.path.exists")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"snapshots": [], "last_updated": null}',
    )
    def test_load_history_existing(self, mock_file, mock_exists, collector):
        """Test loading existing history file."""
        mock_exists.return_value = True

        history = collector.load_history("/tmp/history.json")

        assert history["snapshots"] == []
        assert history["last_updated"] is None

    @patch("os.path.exists")
    def test_load_history_nonexistent(self, mock_exists, collector):
        """Test loading nonexistent history file."""
        mock_exists.return_value = False

        history = collector.load_history("/tmp/history.json")

        assert history == {"snapshots": [], "last_updated": None}

    @patch("builtins.open", new_callable=mock_open)
    @patch("os.makedirs")
    def test_save_metrics_without_history(
        self, mock_makedirs, mock_file, collector, capsys
    ):
        """Test saving metrics without history."""
        metrics = {"snapshot_date": "2025-01-01", "stats": {}}

        collector.save_metrics(metrics, "/tmp/latest.json")

        mock_makedirs.assert_called_once()
        mock_file.assert_called()
        captured = capsys.readouterr()
        assert "Latest metrics saved" in captured.out

    @patch("builtins.open", new_callable=mock_open)
    @patch("os.makedirs")
    @patch("os.path.exists")
    def test_save_metrics_with_history(
        self, mock_exists, mock_makedirs, mock_file, collector, capsys
    ):
        """Test saving metrics with history."""
        mock_exists.return_value = False
        metrics = {"snapshot_date": "2025-01-01", "stats": {}}

        collector.save_metrics(metrics, "/tmp/latest.json", "/tmp/history.json")

        captured = capsys.readouterr()
        assert "Latest metrics saved" in captured.out
        assert "History updated" in captured.out

    @patch("subprocess.run")
    def test_upload_to_gcs_success(self, mock_run, collector, capsys):
        """Test successful GCS upload."""
        mock_run.return_value = MagicMock()

        result = collector.upload_to_gcs(
            "/tmp/metrics.json", "test-bucket", "data/metrics.json"
        )

        assert result is True
        mock_run.assert_called_once()
        captured = capsys.readouterr()
        assert "Uploaded to gs://test-bucket" in captured.out

    @patch("subprocess.run")
    def test_upload_to_gcs_failure(self, mock_run, collector, capsys):
        """Test failed GCS upload."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "gcloud", stderr=b"Upload failed"
        )

        result = collector.upload_to_gcs(
            "/tmp/metrics.json", "test-bucket", "data/metrics.json"
        )

        assert result is False
        captured = capsys.readouterr()
        assert "Failed to upload to GCS" in captured.out
