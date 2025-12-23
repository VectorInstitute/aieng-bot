"""CLI command for waiting on PR checks to complete."""

import os
import sys
import traceback

import click

from ...check_waiter import CheckStatus, CheckWaiter
from ...utils.logging import log_error, log_info, log_success


@click.command(name="wait-checks")
@click.option(
    "--repo",
    required=True,
    help="Repository name in owner/repo format (e.g., VectorInstitute/aieng-bot)",
)
@click.option(
    "--pr-number",
    required=True,
    type=int,
    help="PR number to wait for",
)
@click.option(
    "--max-wait-minutes",
    default=15,
    type=int,
    help="Maximum time to wait in minutes (default: 15)",
)
@click.option(
    "--check-interval",
    default=30,
    type=int,
    help="Seconds between status checks (default: 30)",
)
def wait_checks(
    repo: str,
    pr_number: int,
    max_wait_minutes: int,
    check_interval: int,
) -> None:
    r"""Wait for PR checks to complete.

    Monitors check status and waits until all checks complete successfully,
    fail, or timeout is reached. Filters out stale/malformed checks.

    Exit codes:
      0 - All checks completed successfully
      1 - Some checks failed
      2 - Timeout waiting for checks
      3 - No checks found on PR
      4 - Error occurred

    Examples:
      \b
      # Wait for checks on PR #123
      aieng-bot wait-checks --repo VectorInstitute/repo-name --pr-number 123

      \b
      # Wait up to 30 minutes with 60s intervals
      aieng-bot wait-checks --repo VectorInstitute/repo-name --pr-number 123 \\
        --max-wait-minutes 30 --check-interval 60

    """
    try:
        gh_token = os.environ.get("GH_TOKEN")
        if not gh_token:
            log_error("GH_TOKEN environment variable not set")
            sys.exit(4)

        log_info(f"Waiting for checks on {repo}#{pr_number}...")
        log_info(
            f"Max wait: {max_wait_minutes} minutes, check interval: {check_interval}s"
        )

        waiter = CheckWaiter(
            repo=repo,
            pr_number=pr_number,
            gh_token=gh_token,
            max_wait_seconds=max_wait_minutes * 60,
            check_interval_seconds=check_interval,
        )

        result = waiter.wait()

        log_info(f"Status: {result.status}")
        log_info(f"Elapsed: {result.elapsed_seconds:.1f}s ({result.attempts} checks)")

        if result.status == CheckStatus.COMPLETED:
            log_success(result.message)
            sys.exit(0)
        elif result.status == CheckStatus.FAILED:
            log_error(result.message)
            sys.exit(1)
        elif result.status == CheckStatus.TIMEOUT:
            log_error(result.message)
            sys.exit(2)
        elif result.status == CheckStatus.NO_CHECKS:
            log_error(result.message)
            sys.exit(3)
        else:
            log_error(f"Unexpected status: {result.status}")
            sys.exit(4)

    except Exception as e:
        log_error(f"Failed to wait for checks: {e}")
        traceback.print_exc()
        sys.exit(4)
