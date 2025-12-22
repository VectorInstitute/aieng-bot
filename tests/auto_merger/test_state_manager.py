"""Tests for state manager."""

import subprocess
from datetime import UTC, datetime
from unittest.mock import MagicMock, mock_open, patch

import pytest

from aieng_bot_maintain.auto_merger.models import PRStatus
from aieng_bot_maintain.auto_merger.state_manager import StateManager


@pytest.fixture
def state_manager():
    """Create a StateManager instance."""
    return StateManager(bucket="test-bucket")


@pytest.fixture
def sample_prs():
    """Sample PR data for testing."""
    return [
        {
            "repo": "VectorInstitute/test-repo",
            "number": 123,
            "title": "Bump dependency 1",
            "url": "https://github.com/VectorInstitute/test-repo/pull/123",
            "author": {"login": "dependabot[bot]"},
        },
        {
            "repo": "VectorInstitute/test-repo",
            "number": 124,
            "title": "Bump dependency 2",
            "url": "https://github.com/VectorInstitute/test-repo/pull/124",
            "author": {"login": "dependabot[bot]"},
        },
    ]


class TestStateManager:
    """Test suite for StateManager."""

    def test_init(self):
        """Test StateManager initialization."""
        manager = StateManager(bucket="custom-bucket")
        assert manager.bucket == "custom-bucket"
        assert manager.state_path == "data/pr_queue_state.json"

    @patch("subprocess.run")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"workflow_run_id": "123", "started_at": "2025-01-15T10:00:00Z", "last_updated": "2025-01-15T10:00:00Z", "timeout_at": "2025-01-15T15:30:00Z", "repo_queues": {}, "completed_repos": []}',
    )
    @patch("aieng_bot_maintain.auto_merger.state_manager.datetime")
    def test_load_state_success(
        self, mock_datetime, mock_file, mock_run, state_manager
    ):
        """Test successful state loading."""
        # Mock current time to be shortly after state creation
        mock_datetime.now.return_value = datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC)
        mock_datetime.fromisoformat = datetime.fromisoformat

        mock_run.return_value = MagicMock(returncode=0)

        state = state_manager.load_state()

        assert state is not None
        assert state.workflow_run_id == "123"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_load_state_not_found(self, mock_run, state_manager, capsys):
        """Test loading state when file doesn't exist."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "gcloud")

        state = state_manager.load_state()

        assert state is None
        captured = capsys.readouterr()
        assert "No existing state found" in captured.err

    @patch("subprocess.run")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"workflow_run_id": "123", "started_at": "2025-01-14T10:00:00Z", "last_updated": "2025-01-14T10:00:00Z", "timeout_at": "2025-01-14T15:30:00Z", "repo_queues": {}, "completed_repos": []}',
    )
    @patch("aieng_bot_maintain.auto_merger.state_manager.datetime")
    def test_load_state_stale(
        self, mock_datetime, mock_file, mock_run, state_manager, capsys
    ):
        """Test loading stale state (>24 hours old)."""
        # Mock current time to be 25 hours after state creation
        mock_datetime.now.return_value = datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC)
        mock_datetime.fromisoformat = datetime.fromisoformat

        mock_run.return_value = MagicMock(returncode=0)

        state = state_manager.load_state()

        assert state is None
        captured = capsys.readouterr()
        assert "stale" in captured.err

    @patch("subprocess.run")
    @patch("builtins.open", new_callable=mock_open, read_data="invalid json")
    def test_load_state_invalid_json(self, mock_file, mock_run, state_manager, capsys):
        """Test loading state with invalid JSON."""
        mock_run.return_value = MagicMock(returncode=0)

        state = state_manager.load_state()

        assert state is None
        captured = capsys.readouterr()
        assert "Failed to parse state" in captured.err

    @patch("subprocess.run")
    @patch("builtins.open", new_callable=mock_open)
    @patch("aieng_bot_maintain.auto_merger.state_manager.datetime")
    def test_save_state_success(
        self, mock_datetime, mock_file, mock_run, state_manager, capsys
    ):
        """Test successful state saving."""
        mock_datetime.now.return_value = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Create a simple state
        state = state_manager.create_initial_state("123", [])

        result = state_manager.save_state(state)

        assert result is True
        mock_run.assert_called_once()
        captured = capsys.readouterr()
        assert "State saved to GCS" in captured.err

    @patch("subprocess.run")
    @patch("builtins.open", new_callable=mock_open)
    def test_save_state_failure(self, mock_file, mock_run, state_manager, capsys):
        """Test state saving failure."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "gcloud")

        state = state_manager.create_initial_state("123", [])

        result = state_manager.save_state(state)

        assert result is False
        captured = capsys.readouterr()
        assert "Failed to save state" in captured.err

    @patch("aieng_bot_maintain.auto_merger.state_manager.datetime")
    def test_create_initial_state(self, mock_datetime, state_manager, sample_prs):
        """Test creating initial state from PRs."""
        mock_now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        state = state_manager.create_initial_state("123", sample_prs)

        assert state.workflow_run_id == "123"
        assert "VectorInstitute/test-repo" in state.repo_queues
        assert len(state.repo_queues["VectorInstitute/test-repo"].prs) == 2
        assert state.repo_queues["VectorInstitute/test-repo"].prs[0].pr_number == 123
        assert (
            state.repo_queues["VectorInstitute/test-repo"].prs[0].status
            == PRStatus.PENDING
        )

    @patch("aieng_bot_maintain.auto_merger.state_manager.datetime")
    def test_create_initial_state_multiple_repos(self, mock_datetime, state_manager):
        """Test creating initial state with PRs from multiple repos."""
        mock_now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        prs = [
            {
                "repo": "VectorInstitute/repo1",
                "number": 1,
                "title": "PR 1",
                "url": "https://github.com/VectorInstitute/repo1/pull/1",
                "author": {"login": "bot"},
            },
            {
                "repo": "VectorInstitute/repo2",
                "number": 2,
                "title": "PR 2",
                "url": "https://github.com/VectorInstitute/repo2/pull/2",
                "author": {"login": "bot"},
            },
        ]

        state = state_manager.create_initial_state("123", prs)

        assert len(state.repo_queues) == 2
        assert "VectorInstitute/repo1" in state.repo_queues
        assert "VectorInstitute/repo2" in state.repo_queues

    @patch("aieng_bot_maintain.auto_merger.state_manager.datetime")
    def test_create_initial_state_sorts_prs(self, mock_datetime, state_manager):
        """Test that PRs are sorted by number."""
        mock_now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        prs = [
            {
                "repo": "VectorInstitute/test",
                "number": 125,
                "title": "PR 125",
                "url": "https://github.com/VectorInstitute/test/pull/125",
                "author": {"login": "bot"},
            },
            {
                "repo": "VectorInstitute/test",
                "number": 123,
                "title": "PR 123",
                "url": "https://github.com/VectorInstitute/test/pull/123",
                "author": {"login": "bot"},
            },
            {
                "repo": "VectorInstitute/test",
                "number": 124,
                "title": "PR 124",
                "url": "https://github.com/VectorInstitute/test/pull/124",
                "author": {"login": "bot"},
            },
        ]

        state = state_manager.create_initial_state("123", prs)

        queue = state.repo_queues["VectorInstitute/test"]
        assert queue.prs[0].pr_number == 123
        assert queue.prs[1].pr_number == 124
        assert queue.prs[2].pr_number == 125

    @patch("aieng_bot_maintain.auto_merger.state_manager.datetime")
    def test_create_initial_state_missing_author(self, mock_datetime, state_manager):
        """Test creating initial state when author field is missing.

        This regression test ensures the bot handles PRs from workflows that
        don't fetch the author field (e.g., gh pr list without --json author).
        """
        mock_now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        prs = [
            {
                "repo": "VectorInstitute/test-repo",
                "number": 100,
                "title": "PR without author",
                "url": "https://github.com/VectorInstitute/test-repo/pull/100",
                # author field intentionally missing
            },
            {
                "repo": "VectorInstitute/test-repo",
                "number": 101,
                "title": "PR with partial author",
                "url": "https://github.com/VectorInstitute/test-repo/pull/101",
                "author": {},  # Empty author dict
            },
        ]

        state = state_manager.create_initial_state("123", prs)

        queue = state.repo_queues["VectorInstitute/test-repo"]
        assert len(queue.prs) == 2

        # Both PRs should default to "unknown" author
        assert queue.prs[0].pr_author == "unknown"
        assert queue.prs[1].pr_author == "unknown"

        # Other fields should still be populated correctly
        assert queue.prs[0].pr_number == 100
        assert queue.prs[0].pr_title == "PR without author"
        assert queue.prs[1].pr_number == 101
        assert queue.prs[1].pr_title == "PR with partial author"

    @patch("subprocess.run")
    def test_clear_state_success(self, mock_run, state_manager, capsys):
        """Test successful state clearing."""
        mock_run.return_value = MagicMock(returncode=0)

        result = state_manager.clear_state()

        assert result is True
        mock_run.assert_called_once()
        captured = capsys.readouterr()
        assert "State cleared from GCS" in captured.err

    @patch("subprocess.run")
    def test_clear_state_not_found(self, mock_run, state_manager, capsys):
        """Test clearing state when it doesn't exist."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "gcloud")

        result = state_manager.clear_state()

        assert result is False
        captured = capsys.readouterr()
        assert "No state to clear" in captured.err
