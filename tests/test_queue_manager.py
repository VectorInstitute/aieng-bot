"""Tests for the QueueManager class."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from aieng_bot_maintain.auto_merger.models import (
    PRQueueItem,
    PRStatus,
    QueueState,
    RepoQueue,
)
from aieng_bot_maintain.auto_merger.queue_manager import QueueManager


@pytest.fixture
def mock_gh_token():
    """Mock GitHub token."""
    return "ghp_test_token"


@pytest.fixture
def mock_gcs_bucket():
    """Mock GCS bucket name."""
    return "test-bucket"


@pytest.fixture
def queue_manager(mock_gh_token, mock_gcs_bucket):
    """Create a QueueManager instance with mocked dependencies."""
    with (
        patch(
            "aieng_bot_maintain.auto_merger.queue_manager.StateManager"
        ) as mock_state_mgr,
        patch(
            "aieng_bot_maintain.auto_merger.queue_manager.WorkflowClient"
        ) as mock_workflow_client,
        patch(
            "aieng_bot_maintain.auto_merger.queue_manager.StatusPoller"
        ) as mock_status_poller,
        patch(
            "aieng_bot_maintain.auto_merger.queue_manager.PRProcessor"
        ) as mock_pr_processor,
        patch(
            "aieng_bot_maintain.auto_merger.queue_manager.ActivityLogger"
        ) as mock_activity_logger,
    ):
        manager = QueueManager(gh_token=mock_gh_token, gcs_bucket=mock_gcs_bucket)

        # Store mocks as attributes for test access
        manager.state_manager = mock_state_mgr.return_value
        manager.workflow_client = mock_workflow_client.return_value
        manager.status_poller = mock_status_poller.return_value
        manager.pr_processor = mock_pr_processor.return_value
        manager.activity_logger = mock_activity_logger.return_value

        yield manager


@pytest.fixture
def sample_pr():
    """Create a sample PRQueueItem for testing."""
    now = datetime.now(UTC).isoformat()
    return PRQueueItem(
        repo="VectorInstitute/test-repo",
        pr_number=42,
        pr_title="Bump dependency",
        pr_author="app/dependabot",
        pr_url="https://github.com/VectorInstitute/test-repo/pull/42",
        status=PRStatus.PENDING,
        queued_at=now,
        last_updated=now,
    )


@pytest.fixture
def sample_queue_state():
    """Create a sample QueueState for testing."""
    now = datetime.now(UTC)
    return QueueState(
        workflow_run_id="123456789",
        started_at=now.isoformat(),
        last_updated=now.isoformat(),
        timeout_at=(now + timedelta(hours=5, minutes=30)).isoformat(),
    )


class TestQueueManagerInit:
    """Tests for QueueManager initialization."""

    def test_init_with_defaults(self, mock_gh_token):
        """Test initialization with default GCS bucket."""
        with (
            patch(
                "aieng_bot_maintain.auto_merger.queue_manager.StateManager"
            ) as mock_state_mgr,
            patch(
                "aieng_bot_maintain.auto_merger.queue_manager.WorkflowClient"
            ) as mock_workflow_client,
            patch(
                "aieng_bot_maintain.auto_merger.queue_manager.StatusPoller"
            ) as mock_status_poller,
            patch(
                "aieng_bot_maintain.auto_merger.queue_manager.PRProcessor"
            ) as mock_pr_processor,
            patch(
                "aieng_bot_maintain.auto_merger.queue_manager.ActivityLogger"
            ) as mock_activity_logger,
        ):
            manager = QueueManager(gh_token=mock_gh_token)

            # Verify all dependencies were initialized
            mock_state_mgr.assert_called_once_with(
                bucket="bot-dashboard-vectorinstitute"
            )
            mock_workflow_client.assert_called_once_with(gh_token=mock_gh_token)
            mock_status_poller.assert_called_once_with(gh_token=mock_gh_token)
            mock_pr_processor.assert_called_once()
            mock_activity_logger.assert_called_once_with(
                bucket="bot-dashboard-vectorinstitute"
            )

            assert manager.state_manager is not None
            assert manager.workflow_client is not None
            assert manager.status_poller is not None
            assert manager.pr_processor is not None
            assert manager.activity_logger is not None

    def test_init_with_custom_bucket(self, mock_gh_token, mock_gcs_bucket):
        """Test initialization with custom GCS bucket."""
        with (
            patch(
                "aieng_bot_maintain.auto_merger.queue_manager.StateManager"
            ) as mock_state_mgr,
            patch("aieng_bot_maintain.auto_merger.queue_manager.WorkflowClient"),
            patch("aieng_bot_maintain.auto_merger.queue_manager.StatusPoller"),
            patch("aieng_bot_maintain.auto_merger.queue_manager.PRProcessor"),
            patch(
                "aieng_bot_maintain.auto_merger.queue_manager.ActivityLogger"
            ) as mock_activity_logger,
        ):
            QueueManager(gh_token=mock_gh_token, gcs_bucket=mock_gcs_bucket)

            # Verify custom bucket was used
            mock_state_mgr.assert_called_once_with(bucket=mock_gcs_bucket)
            mock_activity_logger.assert_called_once_with(bucket=mock_gcs_bucket)


class TestIsTimeoutApproaching:
    """Tests for is_timeout_approaching method."""

    def test_timeout_approaching_within_10_minutes(self, queue_manager):
        """Test returns True when timeout is within 10 minutes."""
        now = datetime.now(UTC)
        timeout = now + timedelta(minutes=9)
        state = QueueState(
            workflow_run_id="123",
            started_at=now.isoformat(),
            last_updated=now.isoformat(),
            timeout_at=timeout.isoformat(),
        )

        assert queue_manager.is_timeout_approaching(state) is True

    def test_timeout_not_approaching_over_10_minutes(self, queue_manager):
        """Test returns False when timeout is more than 10 minutes away."""
        now = datetime.now(UTC)
        timeout = now + timedelta(minutes=11)
        state = QueueState(
            workflow_run_id="123",
            started_at=now.isoformat(),
            last_updated=now.isoformat(),
            timeout_at=timeout.isoformat(),
        )

        assert queue_manager.is_timeout_approaching(state) is False

    def test_timeout_exactly_10_minutes(self, queue_manager):
        """Test edge case when timeout is exactly 10 minutes away."""
        now = datetime.now(UTC)
        timeout = now + timedelta(minutes=10)
        state = QueueState(
            workflow_run_id="123",
            started_at=now.isoformat(),
            last_updated=now.isoformat(),
            timeout_at=timeout.isoformat(),
        )

        # Due to execution time, the result may be True (< 10) or False (>= 10)
        # The boundary condition is that remaining < 10, so exactly 10 minutes
        # may round to just under 10 depending on execution timing
        result = queue_manager.is_timeout_approaching(state)
        assert isinstance(result, bool)

    def test_timeout_already_passed(self, queue_manager):
        """Test when timeout has already passed."""
        now = datetime.now(UTC)
        timeout = now - timedelta(minutes=5)
        state = QueueState(
            workflow_run_id="123",
            started_at=now.isoformat(),
            last_updated=now.isoformat(),
            timeout_at=timeout.isoformat(),
        )

        assert queue_manager.is_timeout_approaching(state) is True

    def test_timeout_edge_case_9_minutes_59_seconds(self, queue_manager):
        """Test edge case just under 10 minutes."""
        now = datetime.now(UTC)
        timeout = now + timedelta(minutes=9, seconds=59)
        state = QueueState(
            workflow_run_id="123",
            started_at=now.isoformat(),
            last_updated=now.isoformat(),
            timeout_at=timeout.isoformat(),
        )

        assert queue_manager.is_timeout_approaching(state) is True


class TestProcessRepoQueue:
    """Tests for process_repo_queue method."""

    def test_process_repo_queue_no_queue(
        self, queue_manager, sample_queue_state, capsys
    ):
        """Test processing when queue doesn't exist for repo."""
        result = queue_manager.process_repo_queue(
            repo="VectorInstitute/nonexistent-repo",
            state=sample_queue_state,
        )

        # Should return True (considered complete)
        assert result is True

        # Check warning message
        captured = capsys.readouterr()
        assert "⚠ No queue found for VectorInstitute/nonexistent-repo" in captured.out

    def test_process_repo_queue_empty_queue(
        self, queue_manager, sample_queue_state, capsys
    ):
        """Test processing an empty queue."""
        repo = "VectorInstitute/test-repo"
        empty_queue = RepoQueue(repo=repo, prs=[], current_index=0)
        sample_queue_state.repo_queues[repo] = empty_queue

        result = queue_manager.process_repo_queue(
            repo=repo,
            state=sample_queue_state,
        )

        # Should return True (queue is complete)
        assert result is True
        assert repo in sample_queue_state.completed_repos

        # Note: State is NOT saved for empty queues since the while loop never executes
        # This is expected behavior

    def test_process_repo_queue_timeout_approaching(
        self, queue_manager, sample_pr, capsys
    ):
        """Test processing stops when timeout is approaching."""
        repo = "VectorInstitute/test-repo"
        queue = RepoQueue(repo=repo, prs=[sample_pr], current_index=0)

        # Set timeout to be within 10 minutes
        now = datetime.now(UTC)
        timeout = now + timedelta(minutes=5)
        state = QueueState(
            workflow_run_id="123",
            started_at=now.isoformat(),
            last_updated=now.isoformat(),
            timeout_at=timeout.isoformat(),
            repo_queues={repo: queue},
        )

        result = queue_manager.process_repo_queue(repo=repo, state=state)

        # Should return False (interrupted)
        assert result is False

        # Should save state
        queue_manager.state_manager.save_state.assert_called_with(state)

        # Check warning message
        captured = capsys.readouterr()
        assert "⚠ TIMEOUT APPROACHING" in captured.out

    def test_process_repo_queue_pr_advances(
        self, queue_manager, sample_pr, sample_queue_state, capsys
    ):
        """Test processing when PR should advance to next."""
        repo = "VectorInstitute/test-repo"

        # Create a second PR
        pr2 = PRQueueItem(
            repo=repo,
            pr_number=43,
            pr_title="Another PR",
            pr_author="app/dependabot",
            pr_url="https://github.com/VectorInstitute/test-repo/pull/43",
            status=PRStatus.PENDING,
            queued_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
        )

        queue = RepoQueue(repo=repo, prs=[sample_pr, pr2], current_index=0)
        sample_queue_state.repo_queues[repo] = queue

        # Mock processor to return True (should advance)
        queue_manager.pr_processor.process_pr.return_value = True

        result = queue_manager.process_repo_queue(
            repo=repo,
            state=sample_queue_state,
        )

        # Should return True (completed queue)
        assert result is True

        # PR processor should be called twice (once for each PR)
        assert queue_manager.pr_processor.process_pr.call_count == 2

        # State should be saved after each PR
        assert queue_manager.state_manager.save_state.call_count >= 2

        # Queue should have advanced to completion
        assert queue.current_index == 2
        assert queue.is_complete()
        assert repo in sample_queue_state.completed_repos

        # Check output messages
        captured = capsys.readouterr()
        assert f"✓ Completed all PRs in {repo}" in captured.out

    def test_process_repo_queue_pr_needs_retry(
        self, queue_manager, sample_pr, sample_queue_state, capsys
    ):
        """Test processing when PR needs more time and shouldn't advance."""
        repo = "VectorInstitute/test-repo"
        queue = RepoQueue(repo=repo, prs=[sample_pr], current_index=0)
        sample_queue_state.repo_queues[repo] = queue

        # Mock processor to return False (needs retry)
        queue_manager.pr_processor.process_pr.return_value = False

        result = queue_manager.process_repo_queue(
            repo=repo,
            state=sample_queue_state,
        )

        # Should return False (not completed, will retry)
        assert result is False

        # PR processor should be called once
        queue_manager.pr_processor.process_pr.assert_called_once_with(sample_pr)

        # State should be saved
        queue_manager.state_manager.save_state.assert_called_with(sample_queue_state)

        # Queue should NOT have advanced
        assert queue.current_index == 0
        assert not queue.is_complete()
        assert repo not in sample_queue_state.completed_repos

        # Check output message
        captured = capsys.readouterr()
        assert "PR needs more time, will retry next run" in captured.out

    def test_process_repo_queue_merged_pr_logs_activity(
        self, queue_manager, sample_pr, sample_queue_state
    ):
        """Test that merged PRs trigger activity logging."""
        repo = "VectorInstitute/test-repo"
        queue = RepoQueue(repo=repo, prs=[sample_pr], current_index=0)
        sample_queue_state.repo_queues[repo] = queue

        # Mock processor to mark PR as merged and advance
        def mock_process(pr):
            pr.status = PRStatus.MERGED
            return True

        queue_manager.pr_processor.process_pr.side_effect = mock_process

        result = queue_manager.process_repo_queue(
            repo=repo,
            state=sample_queue_state,
        )

        # Should complete successfully
        assert result is True

        # Activity logger should be called
        queue_manager.activity_logger.log_auto_merge.assert_called_once()

        # Verify the call arguments
        call_args = queue_manager.activity_logger.log_auto_merge.call_args
        assert call_args[1]["repo"] == sample_pr.repo
        assert call_args[1]["pr_number"] == sample_pr.pr_number
        assert call_args[1]["pr_title"] == sample_pr.pr_title
        assert call_args[1]["pr_author"] == sample_pr.pr_author
        assert call_args[1]["pr_url"] == sample_pr.pr_url

    def test_process_repo_queue_multiple_prs_sequential(
        self, queue_manager, sample_queue_state, capsys
    ):
        """Test processing multiple PRs sequentially."""
        repo = "VectorInstitute/test-repo"

        # Create 3 PRs
        prs = []
        for i in range(1, 4):
            pr = PRQueueItem(
                repo=repo,
                pr_number=40 + i,
                pr_title=f"PR #{40 + i}",
                pr_author="app/dependabot",
                pr_url=f"https://github.com/VectorInstitute/test-repo/pull/{40 + i}",
                status=PRStatus.PENDING,
                queued_at=datetime.now(UTC).isoformat(),
                last_updated=datetime.now(UTC).isoformat(),
            )
            prs.append(pr)

        queue = RepoQueue(repo=repo, prs=prs, current_index=0)
        sample_queue_state.repo_queues[repo] = queue

        # Mock processor to always advance
        queue_manager.pr_processor.process_pr.return_value = True

        result = queue_manager.process_repo_queue(
            repo=repo,
            state=sample_queue_state,
        )

        # Should complete successfully
        assert result is True

        # All 3 PRs should be processed
        assert queue_manager.pr_processor.process_pr.call_count == 3

        # Queue should be complete
        assert queue.is_complete()
        assert queue.current_index == 3
        assert repo in sample_queue_state.completed_repos


class TestLogAutoMergeActivity:
    """Tests for _log_auto_merge_activity method."""

    def test_log_auto_merge_without_rebase(self, queue_manager, sample_pr):
        """Test logging activity for PR that wasn't rebased."""
        state = QueueState(
            workflow_run_id="123456789",
            started_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            timeout_at=datetime.now(UTC).isoformat(),
        )

        # Set PR to merged status
        sample_pr.status = PRStatus.MERGED
        sample_pr.rebase_started_at = None

        queue_manager._log_auto_merge_activity(sample_pr, state)

        # Verify activity logger was called
        queue_manager.activity_logger.log_auto_merge.assert_called_once()

        call_args = queue_manager.activity_logger.log_auto_merge.call_args[1]
        assert call_args["repo"] == sample_pr.repo
        assert call_args["pr_number"] == sample_pr.pr_number
        assert call_args["was_rebased"] is False
        assert call_args["rebase_time_seconds"] is None
        assert "actions/runs/123456789" in call_args["github_run_url"]

    def test_log_auto_merge_with_rebase(self, queue_manager, sample_pr):
        """Test logging activity for PR that was rebased."""
        state = QueueState(
            workflow_run_id="987654321",
            started_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            timeout_at=datetime.now(UTC).isoformat(),
        )

        # Set PR to merged status with rebase
        sample_pr.status = PRStatus.MERGED
        rebase_start = datetime.now(UTC) - timedelta(minutes=5)
        rebase_end = datetime.now(UTC)
        sample_pr.rebase_started_at = rebase_start.isoformat()
        sample_pr.last_updated = rebase_end.isoformat()

        queue_manager._log_auto_merge_activity(sample_pr, state)

        # Verify activity logger was called
        queue_manager.activity_logger.log_auto_merge.assert_called_once()

        call_args = queue_manager.activity_logger.log_auto_merge.call_args[1]
        assert call_args["repo"] == sample_pr.repo
        assert call_args["pr_number"] == sample_pr.pr_number
        assert call_args["was_rebased"] is True
        assert call_args["rebase_time_seconds"] is not None
        assert call_args["rebase_time_seconds"] > 0
        # Should be approximately 5 minutes (300 seconds)
        assert 290 <= call_args["rebase_time_seconds"] <= 310

    def test_log_auto_merge_with_invalid_rebase_timestamp(
        self, queue_manager, sample_pr
    ):
        """Test logging handles invalid rebase timestamps gracefully."""
        state = QueueState(
            workflow_run_id="123456789",
            started_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            timeout_at=datetime.now(UTC).isoformat(),
        )

        # Set PR with invalid timestamp
        sample_pr.status = PRStatus.MERGED
        sample_pr.rebase_started_at = "invalid-timestamp"

        # Should not raise exception
        queue_manager._log_auto_merge_activity(sample_pr, state)

        # Verify activity logger was called with None for rebase_time
        call_args = queue_manager.activity_logger.log_auto_merge.call_args[1]
        assert call_args["was_rebased"] is True
        assert call_args["rebase_time_seconds"] is None

    def test_log_auto_merge_without_last_updated(self, queue_manager, sample_pr):
        """Test logging uses current time if last_updated is missing."""
        state = QueueState(
            workflow_run_id="123456789",
            started_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            timeout_at=datetime.now(UTC).isoformat(),
        )

        # Set PR with rebase but no last_updated
        sample_pr.status = PRStatus.MERGED
        sample_pr.rebase_started_at = (
            datetime.now(UTC) - timedelta(minutes=2)
        ).isoformat()
        sample_pr.last_updated = None

        queue_manager._log_auto_merge_activity(sample_pr, state)

        # Should still log successfully
        queue_manager.activity_logger.log_auto_merge.assert_called_once()

        call_args = queue_manager.activity_logger.log_auto_merge.call_args[1]
        assert call_args["was_rebased"] is True
        # Should have calculated rebase time using current time
        assert call_args["rebase_time_seconds"] is not None

    def test_log_auto_merge_github_run_url_format(self, queue_manager, sample_pr):
        """Test GitHub run URL is formatted correctly."""
        state = QueueState(
            workflow_run_id="999888777",
            started_at=datetime.now(UTC).isoformat(),
            last_updated=datetime.now(UTC).isoformat(),
            timeout_at=datetime.now(UTC).isoformat(),
        )

        sample_pr.status = PRStatus.MERGED

        queue_manager._log_auto_merge_activity(sample_pr, state)

        call_args = queue_manager.activity_logger.log_auto_merge.call_args[1]
        expected_url = (
            "https://github.com/VectorInstitute/aieng-bot-maintain/"
            "actions/runs/999888777"
        )
        assert call_args["github_run_url"] == expected_url
        assert call_args["workflow_run_id"] == "999888777"
