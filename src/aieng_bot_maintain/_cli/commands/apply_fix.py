"""CLI command for applying agent fixes to PR failures."""

import argparse
import asyncio
import sys
import traceback

from ...agent_fixer import AgentFixer, AgentFixRequest
from ...utils.logging import log_error, log_info, log_success
from ..utils import get_version


def apply_agent_fix_cli() -> None:
    """CLI entry point for applying agent fixes to PR failures.

    Loads prompt template, invokes Claude Agent SDK to apply fixes,
    and saves execution trace and summary.

    """
    parser = argparse.ArgumentParser(
        prog="apply-agent-fix",
        description="Apply automated fixes to PR failures using Claude Agent SDK",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Apply fixes for a test failure
  apply-agent-fix \\
    --repo VectorInstitute/repo-name \\
    --pr-number 123 \\
    --pr-title "Bump dependency" \\
    --pr-author "app/dependabot" \\
    --pr-url "https://github.com/..." \\
    --failure-type test \\
    --failed-check-names "Run Tests" \\
    --prompt-file .github/prompts/fix-test-failures.md \\
    --failure-logs-file .failure-logs.txt \\
    --workflow-run-id 1234567890 \\
    --github-run-url "https://github.com/.../runs/..." \\
    --cwd /path/to/repo
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
        "--pr-number", required=True, type=int, help="Pull request number"
    )
    parser.add_argument("--pr-title", required=True, help="Pull request title")
    parser.add_argument("--pr-author", required=True, help="Pull request author")
    parser.add_argument("--pr-url", required=True, help="Pull request URL")
    parser.add_argument(
        "--failure-type",
        required=True,
        choices=["test", "lint", "security", "build", "merge_conflict"],
        help="Type of failure",
    )
    parser.add_argument(
        "--failed-check-names",
        required=True,
        help="Comma-separated list of failed check names",
    )
    parser.add_argument(
        "--prompt-file", required=True, help="Path to prompt template file"
    )
    parser.add_argument(
        "--failure-logs-file",
        required=True,
        help="Path to file containing failure logs",
    )
    parser.add_argument(
        "--workflow-run-id", required=True, help="GitHub workflow run ID"
    )
    parser.add_argument(
        "--github-run-url", required=True, help="GitHub workflow run URL"
    )
    parser.add_argument("--cwd", required=True, help="Working directory for agent")

    args = parser.parse_args()

    try:
        # Create fix request
        request = AgentFixRequest(
            repo=args.repo,
            pr_number=args.pr_number,
            pr_title=args.pr_title,
            pr_author=args.pr_author,
            pr_url=args.pr_url,
            failure_type=args.failure_type,
            failed_check_names=args.failed_check_names,
            prompt_file=args.prompt_file,
            failure_logs_file=args.failure_logs_file,
            workflow_run_id=args.workflow_run_id,
            github_run_url=args.github_run_url,
            cwd=args.cwd,
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
