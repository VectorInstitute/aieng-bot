"""CLI command for processing repository PR queues."""

import argparse
import json
import os
import sys
import traceback

from ...utils.logging import log_error, log_info, log_success
from ..utils import get_version


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

        from ...auto_merger import QueueManager

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
        traceback.print_exc()
        sys.exit(1)
