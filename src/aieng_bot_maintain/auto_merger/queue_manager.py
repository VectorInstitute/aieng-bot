"""Queue manager for orchestrating PR queue processing."""

from datetime import UTC, datetime

from .models import QueueState
from .pr_processor import PRProcessor
from .state_manager import StateManager
from .status_poller import StatusPoller
from .workflow_client import WorkflowClient


class QueueManager:
    """Manage parallel processing of repository queues.

    Each repository processes PRs sequentially.
    Repositories are processed in parallel via GitHub Actions matrix.

    Parameters
    ----------
    gh_token : str
        GitHub personal access token.
    gcs_bucket : str, optional
        GCS bucket name (default="bot-dashboard-vectorinstitute").

    Attributes
    ----------
    state_manager : StateManager
        Manager for GCS state persistence.
    workflow_client : WorkflowClient
        Client for GitHub operations.
    status_poller : StatusPoller
        Client for status polling.
    pr_processor : PRProcessor
        Processor for individual PRs.

    """

    def __init__(
        self,
        gh_token: str,
        gcs_bucket: str = "bot-dashboard-vectorinstitute",
    ):
        """Initialize queue manager.

        Parameters
        ----------
        gh_token : str
            GitHub personal access token.
        gcs_bucket : str, optional
            GCS bucket name (default="bot-dashboard-vectorinstitute").

        """
        self.state_manager = StateManager(bucket=gcs_bucket)
        self.workflow_client = WorkflowClient(gh_token=gh_token)
        self.status_poller = StatusPoller(gh_token=gh_token)
        self.pr_processor = PRProcessor(
            workflow_client=self.workflow_client,
            status_poller=self.status_poller,
        )

    def is_timeout_approaching(self, state: QueueState) -> bool:
        """Check if we're within 10 minutes of timeout.

        Parameters
        ----------
        state : QueueState
            Current queue state.

        Returns
        -------
        bool
            True if timeout is approaching.

        """
        now = datetime.now(UTC)
        timeout = datetime.fromisoformat(state.timeout_at)
        remaining = (timeout - now).total_seconds() / 60
        return remaining < 10

    def process_repo_queue(
        self,
        repo: str,
        state: QueueState,
    ) -> bool:
        """Process all PRs in a repository queue.

        Parameters
        ----------
        repo : str
            Repository name (owner/repo format).
        state : QueueState
            Current queue state.

        Returns
        -------
        bool
            True if queue completed, False if interrupted.

        """
        queue = state.repo_queues.get(repo)
        if not queue:
            print(f"⚠ No queue found for {repo}")
            return True

        print(f"\n{'#' * 70}")
        print(f"# Processing repository: {repo}")
        print(f"# PRs in queue: {len(queue.prs)}")
        print(f"# Current position: {queue.current_index + 1}/{len(queue.prs)}")
        print(f"{'#' * 70}\n")

        while not queue.is_complete():
            # Check timeout
            if self.is_timeout_approaching(state):
                print("\n⚠ TIMEOUT APPROACHING - Saving state and stopping")
                self.state_manager.save_state(state)
                return False

            pr = queue.get_current_pr()
            if not pr:
                break

            # Process PR
            should_advance = self.pr_processor.process_pr(pr)

            # Save state after each PR
            self.state_manager.save_state(state)

            if should_advance:
                print(f"  → Moving to next PR in {repo}")
                queue.advance()
            else:
                print("  → PR needs more time, will retry next run")
                # Don't advance, will resume on next workflow run
                return False

        print(f"\n✓ Completed all PRs in {repo}")
        state.completed_repos.append(repo)
        return True
