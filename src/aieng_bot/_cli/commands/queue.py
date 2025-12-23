"""CLI command for processing repository PR queues."""

import json
import os
import sys
import traceback

import click

from ...utils.logging import log_error, log_info, log_success


@click.command()
@click.option(
    "--repo",
    required=True,
    help="Repository name in owner/repo format (e.g., VectorInstitute/aieng-bot)",
)
@click.option(
    "--workflow-run-id",
    required=True,
    help="GitHub workflow run ID for state management and traceability",
)
@click.option(
    "--all-prs",
    required=True,
    help="JSON array of all discovered PRs across repositories",
)
def queue(repo: str, workflow_run_id: str, all_prs: str) -> None:
    r"""Process sequential PR queue for a repository.

    Called by monitor-org-bot-prs.yml matrix job per repository.
    Loads or creates queue state, processes PRs sequentially (oldest first),
    and handles timeout gracefully with state persistence for resumption.

    Sequential processing prevents merge conflicts between multiple PRs
    in the same repository.

    Examples:
      \b
      # Process queue for a specific repository
      aieng-bot queue --repo VectorInstitute/repo-name \\
        --workflow-run-id 1234567890 \\
        --all-prs '[{"repo": "VectorInstitute/repo-name", "number": 123, ...}]'

    """
    try:
        all_prs_list = json.loads(all_prs)

        # Filter to this repo
        repo_prs = [pr for pr in all_prs_list if pr["repo"] == repo]

        log_info(f"Processing {len(repo_prs)} PRs for {repo}")

        # Initialize queue manager
        gh_token = os.environ.get("GH_TOKEN")
        if not gh_token:
            log_error("GH_TOKEN environment variable not set")
            sys.exit(1)

        # Lazy import after environment validation
        from ...auto_merger import (  # noqa: PLC0415
            QueueManager,
        )

        manager = QueueManager(gh_token=gh_token)

        # Load or create state
        state = manager.state_manager.load_state()

        if state and state.workflow_run_id == workflow_run_id:
            log_info("Resuming from existing state")
        else:
            log_info("Creating new queue state")
            state = manager.state_manager.create_initial_state(
                workflow_run_id=workflow_run_id,
                prs=all_prs_list,
            )
            manager.state_manager.save_state(state)

        # Process this repo's queue
        completed = manager.process_repo_queue(repo, state)

        if completed:
            log_success(f"Completed all PRs in {repo}")

            # Save state to persist completed_repos update
            manager.state_manager.save_state(state)

            # Clean up state if all repos done
            if len(state.completed_repos) == len(state.repo_queues):
                log_info("All repositories completed, cleaning up state")
                manager.state_manager.clear_state()
        else:
            log_info(f"Queue processing interrupted for {repo}, state saved")

    except json.JSONDecodeError as e:
        log_error(f"Invalid JSON input: {e}")
        sys.exit(1)
    except Exception as e:
        log_error(f"Failed to process queue: {e}")
        traceback.print_exc()
        sys.exit(1)
