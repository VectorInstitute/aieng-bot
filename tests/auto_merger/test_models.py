"""Tests for auto_merger data models."""

from aieng_bot_maintain.auto_merger.models import (
    PRQueueItem,
    PRStatus,
    QueueState,
    RepoQueue,
)


class TestPRStatus:
    """Test suite for PRStatus enum."""

    def test_enum_values(self):
        """Test enum has expected values."""
        assert PRStatus.PENDING.value == "pending"
        assert PRStatus.REBASING.value == "rebasing"
        assert PRStatus.WAITING_CHECKS.value == "waiting_checks"
        assert PRStatus.CHECKS_PASSED.value == "checks_passed"
        assert PRStatus.CHECKS_FAILED.value == "checks_failed"
        assert PRStatus.FIXING.value == "fixing"
        assert PRStatus.MERGED.value == "merged"
        assert PRStatus.FAILED.value == "failed"
        assert PRStatus.SKIPPED.value == "skipped"


class TestPRQueueItem:
    """Test suite for PRQueueItem."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        pr = PRQueueItem(
            repo="VectorInstitute/test-repo",
            pr_number=123,
            pr_title="Bump dependency",
            pr_author="dependabot[bot]",
            pr_url="https://github.com/VectorInstitute/test-repo/pull/123",
            status=PRStatus.PENDING,
            queued_at="2025-01-15T10:00:00Z",
            last_updated="2025-01-15T10:00:00Z",
        )

        data = pr.to_dict()

        assert data["repo"] == "VectorInstitute/test-repo"
        assert data["pr_number"] == 123
        assert data["pr_title"] == "Bump dependency"
        assert data["pr_author"] == "dependabot[bot]"
        assert data["status"] == "pending"
        assert data["attempt_count"] == 0
        assert data["max_attempts"] == 3

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "repo": "VectorInstitute/test-repo",
            "pr_number": 123,
            "pr_title": "Bump dependency",
            "pr_author": "dependabot[bot]",
            "pr_url": "https://github.com/VectorInstitute/test-repo/pull/123",
            "status": "pending",
            "queued_at": "2025-01-15T10:00:00Z",
            "last_updated": "2025-01-15T10:00:00Z",
            "attempt_count": 1,
            "max_attempts": 3,
            "error_message": "Test error",
            "fix_workflow_run_id": "123456",
        }

        pr = PRQueueItem.from_dict(data)

        assert pr.repo == "VectorInstitute/test-repo"
        assert pr.pr_number == 123
        assert pr.status == PRStatus.PENDING
        assert pr.attempt_count == 1
        assert pr.error_message == "Test error"
        assert pr.fix_workflow_run_id == "123456"

    def test_round_trip_serialization(self):
        """Test serialization round-trip."""
        original = PRQueueItem(
            repo="VectorInstitute/test-repo",
            pr_number=123,
            pr_title="Bump dependency",
            pr_author="dependabot[bot]",
            pr_url="https://github.com/VectorInstitute/test-repo/pull/123",
            status=PRStatus.FIXING,
            queued_at="2025-01-15T10:00:00Z",
            last_updated="2025-01-15T10:30:00Z",
            fix_workflow_run_id="789",
        )

        restored = PRQueueItem.from_dict(original.to_dict())

        assert restored.repo == original.repo
        assert restored.pr_number == original.pr_number
        assert restored.status == original.status
        assert restored.fix_workflow_run_id == original.fix_workflow_run_id


class TestRepoQueue:
    """Test suite for RepoQueue."""

    def test_get_current_pr(self):
        """Test getting current PR."""
        pr1 = PRQueueItem(
            repo="VectorInstitute/test",
            pr_number=1,
            pr_title="PR 1",
            pr_author="bot",
            pr_url="https://github.com/VectorInstitute/test/pull/1",
            status=PRStatus.PENDING,
            queued_at="2025-01-15T10:00:00Z",
            last_updated="2025-01-15T10:00:00Z",
        )
        pr2 = PRQueueItem(
            repo="VectorInstitute/test",
            pr_number=2,
            pr_title="PR 2",
            pr_author="bot",
            pr_url="https://github.com/VectorInstitute/test/pull/2",
            status=PRStatus.PENDING,
            queued_at="2025-01-15T10:00:00Z",
            last_updated="2025-01-15T10:00:00Z",
        )

        queue = RepoQueue(repo="VectorInstitute/test", prs=[pr1, pr2])

        assert queue.get_current_pr() == pr1

    def test_advance(self):
        """Test advancing to next PR."""
        pr1 = PRQueueItem(
            repo="VectorInstitute/test",
            pr_number=1,
            pr_title="PR 1",
            pr_author="bot",
            pr_url="https://github.com/VectorInstitute/test/pull/1",
            status=PRStatus.PENDING,
            queued_at="2025-01-15T10:00:00Z",
            last_updated="2025-01-15T10:00:00Z",
        )
        pr2 = PRQueueItem(
            repo="VectorInstitute/test",
            pr_number=2,
            pr_title="PR 2",
            pr_author="bot",
            pr_url="https://github.com/VectorInstitute/test/pull/2",
            status=PRStatus.PENDING,
            queued_at="2025-01-15T10:00:00Z",
            last_updated="2025-01-15T10:00:00Z",
        )

        queue = RepoQueue(repo="VectorInstitute/test", prs=[pr1, pr2])

        has_more = queue.advance()
        assert has_more is True
        assert queue.get_current_pr() == pr2

        has_more = queue.advance()
        assert has_more is False
        assert queue.get_current_pr() is None

    def test_is_complete(self):
        """Test checking if queue is complete."""
        pr = PRQueueItem(
            repo="VectorInstitute/test",
            pr_number=1,
            pr_title="PR 1",
            pr_author="bot",
            pr_url="https://github.com/VectorInstitute/test/pull/1",
            status=PRStatus.PENDING,
            queued_at="2025-01-15T10:00:00Z",
            last_updated="2025-01-15T10:00:00Z",
        )

        queue = RepoQueue(repo="VectorInstitute/test", prs=[pr])

        assert queue.is_complete() is False
        queue.advance()
        assert queue.is_complete() is True

    def test_to_dict(self):
        """Test serialization to dictionary."""
        pr = PRQueueItem(
            repo="VectorInstitute/test",
            pr_number=1,
            pr_title="PR 1",
            pr_author="bot",
            pr_url="https://github.com/VectorInstitute/test/pull/1",
            status=PRStatus.PENDING,
            queued_at="2025-01-15T10:00:00Z",
            last_updated="2025-01-15T10:00:00Z",
        )

        queue = RepoQueue(repo="VectorInstitute/test", prs=[pr], current_index=0)

        data = queue.to_dict()

        assert data["repo"] == "VectorInstitute/test"
        assert len(data["prs"]) == 1
        assert data["current_index"] == 0

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "repo": "VectorInstitute/test",
            "current_index": 1,
            "prs": [
                {
                    "repo": "VectorInstitute/test",
                    "pr_number": 1,
                    "pr_title": "PR 1",
                    "pr_author": "bot",
                    "pr_url": "https://github.com/VectorInstitute/test/pull/1",
                    "status": "pending",
                    "queued_at": "2025-01-15T10:00:00Z",
                    "last_updated": "2025-01-15T10:00:00Z",
                }
            ],
        }

        queue = RepoQueue.from_dict(data)

        assert queue.repo == "VectorInstitute/test"
        assert queue.current_index == 1
        assert len(queue.prs) == 1


class TestQueueState:
    """Test suite for QueueState."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        pr = PRQueueItem(
            repo="VectorInstitute/test",
            pr_number=1,
            pr_title="PR 1",
            pr_author="bot",
            pr_url="https://github.com/VectorInstitute/test/pull/1",
            status=PRStatus.PENDING,
            queued_at="2025-01-15T10:00:00Z",
            last_updated="2025-01-15T10:00:00Z",
        )
        queue = RepoQueue(repo="VectorInstitute/test", prs=[pr])

        state = QueueState(
            workflow_run_id="123",
            started_at="2025-01-15T10:00:00Z",
            last_updated="2025-01-15T10:00:00Z",
            timeout_at="2025-01-15T15:30:00Z",
            repo_queues={"VectorInstitute/test": queue},
            completed_repos=[],
        )

        data = state.to_dict()

        assert data["workflow_run_id"] == "123"
        assert "VectorInstitute/test" in data["repo_queues"]
        assert data["completed_repos"] == []

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "workflow_run_id": "123",
            "started_at": "2025-01-15T10:00:00Z",
            "last_updated": "2025-01-15T10:00:00Z",
            "timeout_at": "2025-01-15T15:30:00Z",
            "repo_queues": {
                "VectorInstitute/test": {
                    "repo": "VectorInstitute/test",
                    "current_index": 0,
                    "prs": [
                        {
                            "repo": "VectorInstitute/test",
                            "pr_number": 1,
                            "pr_title": "PR 1",
                            "pr_author": "bot",
                            "pr_url": "https://github.com/VectorInstitute/test/pull/1",
                            "status": "pending",
                            "queued_at": "2025-01-15T10:00:00Z",
                            "last_updated": "2025-01-15T10:00:00Z",
                        }
                    ],
                }
            },
            "completed_repos": ["VectorInstitute/other"],
        }

        state = QueueState.from_dict(data)

        assert state.workflow_run_id == "123"
        assert "VectorInstitute/test" in state.repo_queues
        assert state.completed_repos == ["VectorInstitute/other"]

    def test_round_trip_serialization(self):
        """Test full round-trip serialization."""
        pr = PRQueueItem(
            repo="VectorInstitute/test",
            pr_number=1,
            pr_title="PR 1",
            pr_author="bot",
            pr_url="https://github.com/VectorInstitute/test/pull/1",
            status=PRStatus.MERGED,
            queued_at="2025-01-15T10:00:00Z",
            last_updated="2025-01-15T10:30:00Z",
        )
        queue = RepoQueue(repo="VectorInstitute/test", prs=[pr])

        original = QueueState(
            workflow_run_id="123",
            started_at="2025-01-15T10:00:00Z",
            last_updated="2025-01-15T10:30:00Z",
            timeout_at="2025-01-15T15:30:00Z",
            repo_queues={"VectorInstitute/test": queue},
            completed_repos=[],
        )

        restored = QueueState.from_dict(original.to_dict())

        assert restored.workflow_run_id == original.workflow_run_id
        assert "VectorInstitute/test" in restored.repo_queues
        assert (
            restored.repo_queues["VectorInstitute/test"].prs[0].status
            == PRStatus.MERGED
        )
