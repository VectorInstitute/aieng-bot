"""CLI command for applying agent fixes to PR failures."""

import asyncio
import sys
import traceback

import click

from ...agent_fixer import AgentFixer, AgentFixRequest
from ...utils.logging import log_error, log_info, log_success


@click.command()
@click.option(
    "--repo",
    required=True,
    help="Repository name in owner/repo format (e.g., VectorInstitute/aieng-bot)",
)
@click.option(
    "--pr-number",
    required=True,
    type=int,
    help="Pull request number",
)
@click.option(
    "--pr-title",
    required=True,
    help="Pull request title",
)
@click.option(
    "--pr-author",
    required=True,
    help="Pull request author (e.g., app/dependabot, app/pre-commit-ci)",
)
@click.option(
    "--pr-url",
    required=True,
    help="Pull request URL (e.g., https://github.com/owner/repo/pull/123)",
)
@click.option(
    "--head-ref",
    required=True,
    help="PR source branch name (e.g., dependabot/uv/package-1.0.0)",
)
@click.option(
    "--base-ref",
    required=True,
    help="PR target branch name (e.g., main, develop)",
)
@click.option(
    "--failure-type",
    required=True,
    type=click.Choice(["test", "lint", "security", "build", "merge_conflict"]),
    help="Type of failure detected by classifier",
)
@click.option(
    "--failed-check-names",
    required=True,
    help="Comma-separated list of failed check names",
)
@click.option(
    "--failure-logs-file",
    required=True,
    type=click.Path(exists=True),
    help="Path to file containing failure logs (up to 5000 lines)",
)
@click.option(
    "--workflow-run-id",
    required=True,
    help="GitHub workflow run ID for traceability",
)
@click.option(
    "--github-run-url",
    required=True,
    help="GitHub workflow run URL for logging",
)
@click.option(
    "--cwd",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Working directory for agent (repository root)",
)
def fix(
    repo: str,
    pr_number: int,
    pr_title: str,
    pr_author: str,
    pr_url: str,
    head_ref: str,
    base_ref: str,
    failure_type: str,
    failed_check_names: str,
    failure_logs_file: str,
    workflow_run_id: str,
    github_run_url: str,
    cwd: str,
) -> None:
    r"""Apply automated fixes to PR failures using Claude Agent SDK with Skills.

    This command uses the Claude Agent SDK to analyze failures and apply fixes automatically.
    Skills are loaded from .claude/skills/ directory and invoked based on failure type.

    Examples:
      \b
      # Apply fixes for a test failure
      aieng-bot fix \\
        --repo VectorInstitute/repo-name \\
        --pr-number 123 \\
        --pr-title "Bump pytest from 7.0 to 8.0" \\
        --pr-author "app/dependabot" \\
        --pr-url "https://github.com/VectorInstitute/repo/pull/123" \\
        --head-ref "dependabot/uv/pytest-8.0.0" \\
        --base-ref "main" \\
        --failure-type test \\
        --failed-check-names "Run Tests" \\
        --failure-logs-file .failure-logs.txt \\
        --workflow-run-id 1234567890 \\
        --github-run-url "https://github.com/.../actions/runs/1234567890" \\
        --cwd /path/to/repo

    """
    try:
        # Create fix request
        request = AgentFixRequest(
            repo=repo,
            pr_number=pr_number,
            pr_title=pr_title,
            pr_author=pr_author,
            pr_url=pr_url,
            head_ref=head_ref,
            base_ref=base_ref,
            failure_type=failure_type,
            failed_check_names=failed_check_names,
            failure_logs_file=failure_logs_file,
            workflow_run_id=workflow_run_id,
            github_run_url=github_run_url,
            cwd=cwd,
        )

        # Initialize fixer and apply fixes
        log_info("Initializing AgentFixer...")
        fixer = AgentFixer()

        # Run async fix operation
        result = asyncio.run(fixer.apply_fixes(request))

        if result.status == "SUCCESS":
            log_success("Fixes applied successfully")
            log_info(f"Trace saved to: {result.trace_file}")
            log_info(f"Summary saved to: {result.summary_file}")
            sys.exit(0)
        else:
            log_error(f"Fix attempt failed: {result.error_message}")
            sys.exit(1)

    except ValueError as e:
        log_error(f"Configuration error: {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        log_error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        traceback.print_exc()
        sys.exit(1)
