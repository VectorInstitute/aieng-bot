"""CLI command for applying agent fixes to PR failures."""

import asyncio
import json
import os
import shutil
import sys
import traceback
from pathlib import Path

import click
from dotenv import load_dotenv

from ...agent_fixer import AgentFixer, AgentFixRequest
from ...classifier.models import FailureType
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


def _load_and_validate_classification(
    classification_file: str,
) -> tuple[str, float, list[str]]:
    """Load classification result and validate failure type.

    Parameters
    ----------
    classification_file : str
        Path to classification JSON file.

    Returns
    -------
    tuple[str, float, list[str]]
        (failure_type, confidence, failed_check_names)

    Raises
    ------
    ValueError
        If failure type is unknown or unsupported.

    """
    log_info(f"Loading classification from {classification_file}")
    with open(classification_file) as f:
        classification = json.load(f)

    failure_type = classification["failure_type"]
    confidence = classification["confidence"]
    failed_check_names = classification["failed_check_names"]

    log_success(f"Classification: {failure_type} (confidence: {confidence:.1%})")

    # Validate failure type is supported
    if failure_type == FailureType.UNKNOWN.value:
        log_error("Cannot fix unknown failure type")
        log_info(f"Reasoning: {classification['reasoning']}")
        raise ValueError("Unknown failure type cannot be fixed")

    if failure_type not in ["test", "lint", "security", "build", "merge_conflict"]:
        raise ValueError(f"Unsupported failure type: {failure_type}")

    return failure_type, confidence, failed_check_names


def _fetch_pr_data(
    repo: str,
    pr_number: int,
    cwd: str,
    github_token: str | None,
) -> tuple[str, str, str, str, str]:
    """Fetch PR details and failure logs from GitHub.

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
    tuple[str, str, str, str, str]
        (pr_title, pr_author, head_ref, base_ref, failure_logs_file)

    """
    log_info(f"Fetching PR details for {repo}#{pr_number}")
    github_client = GitHubClient(github_token=github_token)
    pr_context = github_client.get_pr_details(repo, pr_number)

    log_success(f"PR: {pr_context.pr_title}")
    log_info(f"Author: {pr_context.pr_author}")
    log_info(f"Branch: {pr_context.head_ref} → {pr_context.base_ref}")

    # Fetch failure logs from failed checks
    failed_checks = github_client.get_failed_checks(repo, pr_number)
    if not failed_checks:
        log_warning("No failed checks found - using classification data only")
        # Create empty failure logs file
        failure_logs_file = str(Path(cwd) / ".failure-logs.txt")
        with open(failure_logs_file, "w") as f:
            f.write("No failure logs available from CI checks\n")
    else:
        log_info(f"Fetching logs from {len(failed_checks)} failed checks")
        temp_logs_file = github_client.get_failure_logs(repo, failed_checks)

        # Move logs to working directory
        failure_logs_file = str(Path(cwd) / ".failure-logs.txt")
        shutil.move(temp_logs_file, failure_logs_file)
        log_success(f"Failure logs saved to {failure_logs_file}")

    return (
        pr_context.pr_title,
        pr_context.pr_author,
        pr_context.head_ref,
        pr_context.base_ref,
        failure_logs_file,
    )


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


@click.command()
@click.option(
    "--repo",
    required=True,
    help="Repository name in owner/repo format (e.g., VectorInstitute/aieng-bot)",
)
@click.option(
    "--pr",
    "pr_number",
    required=True,
    type=int,
    help="Pull request number",
)
@click.option(
    "--cls",
    "classification_file",
    required=True,
    type=click.Path(exists=True),
    help="Path to classification JSON file from classify command",
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
def fix(
    repo: str,
    pr_number: int,
    classification_file: str,
    cwd: str,
    workflow_run_id: str,
    github_run_url: str,
    github_token: str | None,
    anthropic_api_key: str | None,
) -> None:
    """Apply automated fixes to PR failures.

    This command performs the following steps:

    \b
    1. Loads the classification result from the classify command
    2. Fetches PR details from GitHub API
    3. Downloads failure logs from failed checks
    4. Prepares the agent execution environment
    5. Runs Claude Agent SDK to apply fixes
    6. Cleans up temporary files

    Examples:
    \b
      # Basic usage (after running classify command)
      aieng-bot classify --repo VectorInstitute/repo-name --pr 123 --output /tmp/cls.json
      aieng-bot fix --repo VectorInstitute/repo-name --pr 123 --cls /tmp/cls.json

    \b
      # With custom working directory
      aieng-bot fix \\
        --repo VectorInstitute/repo-name \\
        --pr 123 \\
        --cls /tmp/classification.json \\
        --cwd /path/to/repo

    \b
      # With workflow traceability (for CI/CD)
      aieng-bot fix \\
        --repo VectorInstitute/repo-name \\
        --pr 123 \\
        --cls /tmp/classification.json \\
        --workflow-run-id 1234567890 \\
        --github-run-url "https://github.com/.../actions/runs/1234567890"

    \b
    Required Environment Variables:
    ANTHROPIC_API_KEY  - Claude API key (https://console.anthropic.com)
    GITHUB_TOKEN       - GitHub token (or GH_TOKEN)

    """
    # Check environment variables
    env_ok, missing_vars = _check_environment_variables()
    if not env_ok:
        log_error("Missing required environment variables:")
        for var_info in missing_vars:
            print(f"  • {var_info}")
        print()
        print(
            "💡 Tip: Create a .env file with these variables or export them in your shell"
        )
        sys.exit(1)

    failure_logs_file = None
    bot_skills_copied = False

    try:
        # 1. Load and validate classification
        failure_type, confidence, failed_check_names = (
            _load_and_validate_classification(classification_file)
        )

        # 2. Fetch PR data from GitHub
        pr_title, pr_author, head_ref, base_ref, failure_logs_file = _fetch_pr_data(
            repo, pr_number, cwd, github_token
        )

        # 3. Prepare agent environment
        bot_skills_copied = _prepare_agent_environment(cwd)

        # 4. Create fix request and run agent
        log_info("Initializing AgentFixer...")
        pr_url = f"https://github.com/{repo}/pull/{pr_number}"
        failed_check_names_str = ",".join(failed_check_names)

        request = AgentFixRequest(
            repo=repo,
            pr_number=pr_number,
            pr_title=pr_title,
            pr_author=pr_author,
            pr_url=pr_url,
            head_ref=head_ref,
            base_ref=base_ref,
            failure_type=failure_type,
            failed_check_names=failed_check_names_str,
            failure_logs_file=failure_logs_file,
            workflow_run_id=workflow_run_id,
            github_run_url=github_run_url,
            cwd=cwd,
        )

        fixer = AgentFixer()
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
    except json.JSONDecodeError as e:
        log_error(f"Invalid classification JSON: {e}")
        sys.exit(1)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        # 5. Cleanup temporary files
        _cleanup_temporary_files(cwd, failure_logs_file, bot_skills_copied)
