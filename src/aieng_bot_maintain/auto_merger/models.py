"""Data models for auto-merger queue system."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PRStatus(str, Enum):
    """Status of PR in queue processing."""

    PENDING = "pending"
    REBASING = "rebasing"
    WAITING_CHECKS = "waiting_checks"
    CHECKS_PASSED = "checks_passed"
    CHECKS_FAILED = "checks_failed"
    FIXING = "fixing"
    MERGED = "merged"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PRQueueItem:
    """Individual PR in processing queue.

    Parameters
    ----------
    repo : str
        Repository name (owner/repo format).
    pr_number : int
        PR number.
    pr_title : str
        PR title.
    pr_author : str
        PR author login.
    pr_url : str
        PR URL.
    status : PRStatus
        Current processing status.
    queued_at : str
        ISO timestamp when PR was queued.
    last_updated : str
        ISO timestamp of last status update.
    rebase_started_at : str or None, optional
        ISO timestamp when rebase was triggered.
    fix_started_at : str or None, optional
        ISO timestamp when fix workflow was triggered.
    attempt_count : int, optional
        Number of fix attempts (default=0).
    max_attempts : int, optional
        Maximum number of fix attempts (default=3).
    error_message : str or None, optional
        Error message if PR failed.
    fix_workflow_run_id : str or None, optional
        GitHub workflow run ID for fix attempt.

    """

    repo: str
    pr_number: int
    pr_title: str
    pr_author: str
    pr_url: str
    status: PRStatus

    queued_at: str
    last_updated: str
    rebase_started_at: str | None = None
    fix_started_at: str | None = None

    attempt_count: int = 0
    max_attempts: int = 3
    error_message: str | None = None
    fix_workflow_run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns
        -------
        dict[str, Any]
            Dictionary representation of PR queue item.

        """
        return {
            "repo": self.repo,
            "pr_number": self.pr_number,
            "pr_title": self.pr_title,
            "pr_author": self.pr_author,
            "pr_url": self.pr_url,
            "status": self.status.value,
            "queued_at": self.queued_at,
            "last_updated": self.last_updated,
            "rebase_started_at": self.rebase_started_at,
            "fix_started_at": self.fix_started_at,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "error_message": self.error_message,
            "fix_workflow_run_id": self.fix_workflow_run_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PRQueueItem":
        """Create from dictionary.

        Parameters
        ----------
        data : dict[str, Any]
            Dictionary representation.

        Returns
        -------
        PRQueueItem
            Reconstructed PR queue item.

        """
        return cls(
            repo=data["repo"],
            pr_number=data["pr_number"],
            pr_title=data["pr_title"],
            pr_author=data["pr_author"],
            pr_url=data["pr_url"],
            status=PRStatus(data["status"]),
            queued_at=data["queued_at"],
            last_updated=data["last_updated"],
            rebase_started_at=data.get("rebase_started_at"),
            fix_started_at=data.get("fix_started_at"),
            attempt_count=data.get("attempt_count", 0),
            max_attempts=data.get("max_attempts", 3),
            error_message=data.get("error_message"),
            fix_workflow_run_id=data.get("fix_workflow_run_id"),
        )


@dataclass
class RepoQueue:
    """Queue of PRs for a single repository.

    Parameters
    ----------
    repo : str
        Repository name (owner/repo format).
    prs : list[PRQueueItem], optional
        List of PRs in queue (default=[]).
    current_index : int, optional
        Index of current PR being processed (default=0).

    """

    repo: str
    prs: list[PRQueueItem] = field(default_factory=list)
    current_index: int = 0

    def get_current_pr(self) -> PRQueueItem | None:
        """Get current PR being processed.

        Returns
        -------
        PRQueueItem or None
            Current PR, or None if queue is complete.

        """
        if self.current_index < len(self.prs):
            return self.prs[self.current_index]
        return None

    def advance(self) -> bool:
        """Move to next PR.

        Returns
        -------
        bool
            True if more PRs remain, False if queue is complete.

        """
        self.current_index += 1
        return self.current_index < len(self.prs)

    def is_complete(self) -> bool:
        """Check if all PRs processed.

        Returns
        -------
        bool
            True if all PRs have been processed.

        """
        return self.current_index >= len(self.prs)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns
        -------
        dict[str, Any]
            Dictionary representation of repository queue.

        """
        return {
            "repo": self.repo,
            "prs": [pr.to_dict() for pr in self.prs],
            "current_index": self.current_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepoQueue":
        """Create from dictionary.

        Parameters
        ----------
        data : dict[str, Any]
            Dictionary representation.

        Returns
        -------
        RepoQueue
            Reconstructed repository queue.

        """
        return cls(
            repo=data["repo"],
            prs=[PRQueueItem.from_dict(pr) for pr in data["prs"]],
            current_index=data["current_index"],
        )


@dataclass
class QueueState:
    """Global queue state for all repositories.

    Parameters
    ----------
    workflow_run_id : str
        GitHub Actions workflow run ID.
    started_at : str
        ISO timestamp when processing started.
    last_updated : str
        ISO timestamp of last state update.
    timeout_at : str
        ISO timestamp when to stop processing (5.5 hours from start).
    repo_queues : dict[str, RepoQueue], optional
        Mapping of repo name to repository queue (default={}).
    completed_repos : list[str], optional
        List of repositories that have completed processing (default=[]).

    """

    workflow_run_id: str
    started_at: str
    last_updated: str
    timeout_at: str

    repo_queues: dict[str, RepoQueue] = field(default_factory=dict)
    completed_repos: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for GCS storage.

        Returns
        -------
        dict[str, Any]
            Dictionary representation of queue state.

        """
        return {
            "workflow_run_id": self.workflow_run_id,
            "started_at": self.started_at,
            "last_updated": self.last_updated,
            "timeout_at": self.timeout_at,
            "repo_queues": {
                repo: queue.to_dict() for repo, queue in self.repo_queues.items()
            },
            "completed_repos": self.completed_repos,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueueState":
        """Load from dictionary.

        Parameters
        ----------
        data : dict[str, Any]
            Dictionary representation.

        Returns
        -------
        QueueState
            Reconstructed queue state.

        """
        return cls(
            workflow_run_id=data["workflow_run_id"],
            started_at=data["started_at"],
            last_updated=data["last_updated"],
            timeout_at=data["timeout_at"],
            repo_queues={
                repo: RepoQueue.from_dict(queue_data)
                for repo, queue_data in data["repo_queues"].items()
            },
            completed_repos=data["completed_repos"],
        )
