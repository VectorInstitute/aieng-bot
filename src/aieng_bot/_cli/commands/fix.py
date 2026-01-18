"""CLI command for running agentic fix loop on PR failures."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path

import click
from dotenv import load_dotenv

from ...agent_fixer import AgentFixer
from ...agent_fixer.models import AgentFixResult, AgenticLoopRequest
from ...auto_merger.activity_logger import ActivityLogger, ActivityStatus
from ...utils.github_client import GitHubClient
from ...utils.logging import log_error, log_info, log_success, log_warning

# Load .env file at module import time
load_dotenv()


def _check_environment_variables() -> tuple[bool, list[str]]:
    """Check if required environment variables are set.

    Returns
    -------
    tuple[bool, list[str]]
        (all_set, missing_vars) - True if all vars set, list of missing var names

    """
    required_vars = {
        "ANTHROPIC_API_KEY": "Get from https://console.anthropic.com/settings/keys",
        "GITHUB_TOKEN": "GitHub personal access token (or GH_TOKEN)",
    }

    missing = []
    for var, description in required_vars.items():
        if var == "GITHUB_TOKEN":
            # Check both GITHUB_TOKEN and GH_TOKEN
            if not os.environ.get("GITHUB_TOKEN") and not os.environ.get("GH_TOKEN"):
                missing.append(f"{var} (or GH_TOKEN): {description}")
        elif not os.environ.get(var):
            missing.append(f"{var}: {description}")

    return len(missing) == 0, missing


def _check_pr_status(
    repo: str, pr_number: int, github_token: str | None
) -> tuple[str, bool]:
    """Check PR state and whether it has failing checks.

    Parameters
    ----------
    repo : str
        Repository in format owner/repo.
    pr_number : int
        Pull request number.
    github_token : str | None
        GitHub token for API access.

    Returns
    -------
    tuple[str, bool]
        (state, has_failing_checks) - state is "OPEN", "MERGED", or "CLOSED"

    """
    env = os.environ.copy()
    if github_token:
        env["GH_TOKEN"] = github_token

    # Get PR state
    state = "UNKNOWN"
    result = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--repo", repo, "--json", "state"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if result.returncode == 0:
        data = json.loads(result.stdout)
        state = data.get("state", "UNKNOWN")

    # Check for failing checks
    has_failing_checks = False
    result = subprocess.run(
        ["gh", "pr", "checks", str(pr_number), "--repo", repo],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    # gh pr checks returns exit code 1 if any check failed
    if result.returncode == 1 or "fail" in result.stdout.lower():
        has_failing_checks = True

    return state, has_failing_checks


def _fetch_pr_details(
    repo: str,
    pr_number: int,
    github_token: str | None,
) -> tuple[str, str, str, str]:
    """Fetch PR details from GitHub.

    Parameters
    ----------
    repo : str
        Repository in format owner/repo.
    pr_number : int
        Pull request number.
    github_token : str | None
        GitHub token for API access.

    Returns
    -------
    tuple[str, str, str, str]
        (pr_title, pr_author, head_ref, base_ref)

    """
    log_info(f"Fetching PR details for {repo}#{pr_number}")
    github_client = GitHubClient(github_token=github_token)
    pr_context = github_client.get_pr_details(repo, pr_number)

    log_success(f"PR: {pr_context.pr_title}")
    log_info(f"Author: {pr_context.pr_author}")
    log_info(f"Branch: {pr_context.head_ref} -> {pr_context.base_ref}")

    return (
        pr_context.pr_title,
        pr_context.pr_author,
        pr_context.head_ref,
        pr_context.base_ref,
    )


def _fetch_initial_failure_logs(
    repo: str,
    pr_number: int,
    cwd: str,
    github_token: str | None,
) -> str:
    """Fetch initial failure logs from failed checks.

    Parameters
    ----------
    repo : str
        Repository in format owner/repo.
    pr_number : int
        Pull request number.
    cwd : str
        Working directory for logs file.
    github_token : str | None
        GitHub token for API access.

    Returns
    -------
    str
        Path to failure logs file.

    """
    github_client = GitHubClient(github_token=github_token)

    # Fetch failure logs from failed checks
    failed_checks = github_client.get_failed_checks(repo, pr_number)
    failure_logs_file = str(Path(cwd) / ".failure-logs.txt")

    if not failed_checks:
        log_warning("No failed checks found - creating empty logs file")
        with open(failure_logs_file, "w") as f:
            f.write("No failure logs available from CI checks\n")
    else:
        log_info(f"Fetching logs from {len(failed_checks)} failed checks")
        temp_logs_file = github_client.get_failure_logs(repo, failed_checks)
        shutil.move(temp_logs_file, failure_logs_file)
        log_success(f"Initial failure logs saved to {failure_logs_file}")

    return failure_logs_file


def _prepare_agent_environment(cwd: str) -> bool:
    """Copy bot skills to working directory and configure git exclude.

    Parameters
    ----------
    cwd : str
        Working directory for agent.

    Returns
    -------
    bool
        True if skills were copied, False otherwise.

    """
    bot_repo_path = Path(__file__).parent.parent.parent.parent.parent
    skills_source = bot_repo_path / ".claude"

    if not skills_source.exists():
        log_warning(f"Skills directory not found at {skills_source}")
        return False

    skills_dest = Path(cwd) / ".claude"

    # Check if source and destination are the same (running from bot repo)
    try:
        if skills_source.resolve() == skills_dest.resolve():
            log_info("Running from bot repo - skills already in place")
            return False  # No cleanup needed
    except OSError:
        pass  # If resolve fails, continue with copy attempt

    log_info(f"Copying Claude Code skills to {skills_dest}")
    shutil.copytree(skills_source, skills_dest, dirs_exist_ok=True)
    log_success("Skills copied successfully")

    # Add bot files to git exclude list (safety net)
    git_exclude_file = Path(cwd) / ".git" / "info" / "exclude"
    if git_exclude_file.parent.exists():
        with open(git_exclude_file, "a") as f:
            f.write("\n# AI Engineering Bot temporary files - DO NOT COMMIT\n")
            f.write(".claude/\n")
            f.write(".pr-context.json\n")
            f.write(".failure-logs.txt\n")
        log_success("Bot files added to .git/info/exclude")

    return True


def _cleanup_temporary_files(
    cwd: str, failure_logs_file: str | None, skills_copied: bool
) -> None:
    """Clean up temporary files created during fix process.

    Parameters
    ----------
    cwd : str
        Working directory.
    failure_logs_file : str | None
        Path to failure logs file.
    skills_copied : bool
        Whether skills were copied to working directory.

    """
    log_info("Cleaning up temporary files...")
    try:
        if failure_logs_file and Path(failure_logs_file).exists():
            os.unlink(failure_logs_file)
            log_success(f"Removed {failure_logs_file}")

        if skills_copied:
            skills_dest = Path(cwd) / ".claude"
            if skills_dest.exists():
                shutil.rmtree(skills_dest)
                log_success("Removed .claude/ directory")

            pr_context_file = Path(cwd) / ".pr-context.json"
            if pr_context_file.exists():
                os.unlink(pr_context_file)
                log_success("Removed .pr-context.json")
    except Exception as e:
        log_warning(f"Error during cleanup: {e}")


def _get_detected_failure_type(cwd: str) -> str:
    """Read the detected failure type from .pr-context.json.

    The agent updates this file with the failure type after analysis.

    Parameters
    ----------
    cwd : str
        Working directory containing .pr-context.json.

    Returns
    -------
    str
        Detected failure type or "unknown" if not found.

    """
    context_file = Path(cwd) / ".pr-context.json"
    try:
        if context_file.exists():
            with open(context_file) as f:
                context = json.load(f)
                return context.get("failure_type", "unknown")
    except Exception as e:
        log_warning(f"Could not read failure type from context: {e}")
    return "unknown"


def _handle_result(
    result: AgentFixResult,
    repo: str,
    pr_number: int,
    pr_title: str,
    pr_author: str,
    workflow_run_id: str,
    github_run_url: str,
    elapsed_hours: float,
    failure_type: str,
    log_to_gcs: bool,
) -> None:
    """Handle the result of the agentic loop and optionally log to GCS.

    Parameters
    ----------
    result : AgentFixResult
        Result from the agentic loop.
    repo : str
        Repository name.
    pr_number : int
        PR number.
    pr_title : str
        PR title.
    pr_author : str
        PR author.
    workflow_run_id : str
        GitHub workflow run ID.
    github_run_url : str
        GitHub workflow run URL.
    elapsed_hours : float
        Time spent on fix in hours.
    failure_type : str
        Type of failure that was fixed.
    log_to_gcs : bool
        Whether to log activity to GCS.

    Raises
    ------
    SystemExit
        Exits with 0 on success, 1 on failure.

    """
    if result.status == "SUCCESS":
        log_success("PR fixed and merged successfully!")
        log_info(f"Trace saved to: {result.trace_file}")
        log_info(f"Summary saved to: {result.summary_file}")
        log_info(f"Failure type: {failure_type}")
        status: ActivityStatus = "SUCCESS"
        trace_path = result.trace_file
        exit_code = 0
    else:
        log_error(f"Agentic fix failed: {result.error_message}")
        status = "FAILED"
        trace_path = result.trace_file or ""
        exit_code = 1

    if log_to_gcs:
        _log_activity_to_gcs(
            repo=repo,
            pr_number=pr_number,
            pr_title=pr_title,
            pr_author=pr_author,
            workflow_run_id=workflow_run_id,
            github_run_url=github_run_url,
            status=status,
            trace_path=trace_path,
            fix_time_hours=elapsed_hours,
            failure_type=failure_type,
        )

    sys.exit(exit_code)


def _log_activity_to_gcs(
    repo: str,
    pr_number: int,
    pr_title: str,
    pr_author: str,
    workflow_run_id: str,
    github_run_url: str,
    status: ActivityStatus,
    trace_path: str,
    fix_time_hours: float,
    failure_type: str,
) -> None:
    """Log activity to GCS for dashboard.

    Parameters
    ----------
    repo : str
        Repository name.
    pr_number : int
        PR number.
    pr_title : str
        PR title.
    pr_author : str
        PR author.
    workflow_run_id : str
        GitHub workflow run ID.
    github_run_url : str
        GitHub workflow run URL.
    status : ActivityStatus
        Fix status (SUCCESS, FAILED, PARTIAL).
    trace_path : str
        Path to trace file in GCS.
    fix_time_hours : float
        Time spent on fix in hours.
    failure_type : str
        Type of failure that was fixed (lint, test, build, security, merge_conflict, etc.).

    """
    try:
        logger = ActivityLogger()
        pr_url = f"https://github.com/{repo}/pull/{pr_number}"

        logger.log_fix(
            repo=repo,
            pr_number=pr_number,
            pr_title=pr_title,
            pr_author=pr_author,
            pr_url=pr_url,
            workflow_run_id=workflow_run_id,
            github_run_url=github_run_url,
            status=status,
            failure_type=failure_type,
            trace_path=trace_path,
            fix_time_hours=fix_time_hours,
        )
    except Exception as e:
        log_warning(f"Failed to log activity to GCS: {e}")


@click.command("fix")
@click.option(
    "--repo",
    required=True,
    help="Repository name in owner/repo format (e.g., VectorInstitute/repo-name)",
)
@click.option(
    "--pr",
    "pr_number",
    required=True,
    type=int,
    help="Pull request number",
)
@click.option(
    "--max-retries",
    default=3,
    type=int,
    help="Maximum number of fix attempts (default: 3)",
)
@click.option(
    "--timeout-minutes",
    default=330,
    type=int,
    help="Maximum time for entire fix loop in minutes (default: 330 = 5.5 hours)",
)
@click.option(
    "--cwd",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=".",
    help="Working directory for agent (defaults to current directory)",
)
@click.option(
    "--workflow-run-id",
    default="",
    help="GitHub workflow run ID for traceability (optional)",
)
@click.option(
    "--github-run-url",
    default="",
    help="GitHub workflow run URL for logging (optional)",
)
@click.option(
    "--github-token",
    envvar="GITHUB_TOKEN",
    help="GitHub token (or set GITHUB_TOKEN/GH_TOKEN env var)",
)
@click.option(
    "--anthropic-api-key",
    envvar="ANTHROPIC_API_KEY",
    help="Anthropic API key (or set ANTHROPIC_API_KEY env var)",
)
@click.option(
    "--log",
    "log_to_gcs",
    is_flag=True,
    default=False,
    help="Log fix activity to GCS for dashboard (requires gcloud auth)",
)
def fix(
    repo: str,
    pr_number: int,
    max_retries: int,
    timeout_minutes: int,
    cwd: str,
    workflow_run_id: str,
    github_run_url: str,
    github_token: str | None,
    anthropic_api_key: str | None,  # noqa: ARG001 - used by env var loading
    log_to_gcs: bool,
) -> None:
    """Fix and merge a PR by running Claude in an autonomous loop.

    This command handles the full PR lifecycle:
    - PRs with failures: Analyze, fix, commit, push, wait for CI, merge
    - PRs without failures: Check if rebase needed, rebase, wait for CI, merge
    - Already merged/closed PRs: Exit early (no API calls)

    Claude will automatically determine what action is needed and apply
    the appropriate fix or merge strategy. If CI fails, it retries automatically.

    Examples:
    \b
      # Basic usage - fix failures and merge
      aieng-bot fix --repo VectorInstitute/repo-name --pr 123

    \b
      # With GCS logging for dashboard
      aieng-bot fix --repo VectorInstitute/repo-name --pr 123 --log

    \b
      # With custom retries and timeout
      aieng-bot fix \\
        --repo VectorInstitute/repo-name \\
        --pr 123 \\
        --max-retries 5 \\
        --timeout-minutes 180

    \b
    Required Environment Variables:
    ANTHROPIC_API_KEY  - Claude API key (https://console.anthropic.com)
    GITHUB_TOKEN       - GitHub token (or GH_TOKEN)

    For --log flag (GCS logging):
    Requires gcloud CLI authenticated with access to bot-dashboard-vectorinstitute bucket.

    """
    start_time = time.time()

    # Check environment variables
    env_ok, missing_vars = _check_environment_variables()
    if not env_ok:
        log_error("Missing required environment variables:")
        for var_info in missing_vars:
            print(f"  - {var_info}")
        print()
        print(
            "Tip: Create a .env file with these variables or export them in your shell"
        )
        sys.exit(1)

    # Generate a run ID if logging is enabled but no workflow ID provided
    if log_to_gcs and not workflow_run_id:
        workflow_run_id = f"local-{uuid.uuid4().hex[:8]}"
        log_info(f"Generated run ID for logging: {workflow_run_id}")

    # Check PR state
    pr_state, has_failing_checks = _check_pr_status(repo, pr_number, github_token)
    if pr_state == "MERGED":
        log_info(f"PR #{pr_number} is already merged. Nothing to do.")
        sys.exit(0)
    elif pr_state == "CLOSED":
        log_warning(f"PR #{pr_number} is closed (not merged). Skipping.")
        sys.exit(0)
    elif not has_failing_checks:
        log_info(
            f"PR #{pr_number} has no failing checks. Will check for rebase and merge."
        )

    failure_logs_file = None
    bot_skills_copied = False

    try:
        # 1. Fetch PR details
        pr_title, pr_author, head_ref, base_ref = _fetch_pr_details(
            repo, pr_number, github_token
        )

        # 2. Fetch initial failure logs
        failure_logs_file = _fetch_initial_failure_logs(
            repo, pr_number, cwd, github_token
        )

        # 3. Prepare agent environment
        bot_skills_copied = _prepare_agent_environment(cwd)

        # 4. Create agentic loop request and run agent
        log_info("Initializing AgentFixer for agentic loop...")
        pr_url = f"https://github.com/{repo}/pull/{pr_number}"

        request = AgenticLoopRequest(
            repo=repo,
            pr_number=pr_number,
            pr_title=pr_title,
            pr_author=pr_author,
            pr_url=pr_url,
            head_ref=head_ref,
            base_ref=base_ref,
            failure_logs_file=failure_logs_file,
            max_retries=max_retries,
            timeout_minutes=timeout_minutes,
            workflow_run_id=workflow_run_id,
            github_run_url=github_run_url,
            cwd=cwd,
        )

        fixer = AgentFixer()
        result = asyncio.run(fixer.run_agentic_loop(request))

        elapsed_hours = (time.time() - start_time) / 3600
        detected_failure_type = _get_detected_failure_type(cwd)

        _handle_result(
            result=result,
            repo=repo,
            pr_number=pr_number,
            pr_title=pr_title,
            pr_author=pr_author,
            workflow_run_id=workflow_run_id,
            github_run_url=github_run_url,
            elapsed_hours=elapsed_hours,
            failure_type=detected_failure_type,
            log_to_gcs=log_to_gcs,
        )

    except (ValueError, FileNotFoundError) as e:
        log_error(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        # 5. Cleanup temporary files
        _cleanup_temporary_files(cwd, failure_logs_file, bot_skills_copied)
