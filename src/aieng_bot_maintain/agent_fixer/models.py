"""Data models for agent fixer."""

from dataclasses import dataclass


@dataclass
class AgentFixRequest:
    """Request for agent to fix a PR failure.

    Attributes
    ----------
    repo : str
        Repository name (owner/repo).
    pr_number : int
        Pull request number.
    pr_title : str
        Pull request title.
    pr_author : str
        Pull request author username.
    pr_url : str
        Full URL to the pull request.
    failure_type : str
        Type of failure (test, lint, security, build, merge_conflict).
    failed_check_names : str
        Comma-separated list of failed check names.
    failure_logs_file : str
        Path to file containing failure logs.
    workflow_run_id : str
        GitHub Actions workflow run ID.
    github_run_url : str
        URL to the GitHub Actions run.
    cwd : str
        Working directory where agent should operate.

    """

    repo: str
    pr_number: int
    pr_title: str
    pr_author: str
    pr_url: str
    failure_type: str
    failed_check_names: str
    failure_logs_file: str
    workflow_run_id: str
    github_run_url: str
    cwd: str


@dataclass
class AgentFixResult:
    """Result from agent fix attempt.

    Attributes
    ----------
    status : str
        Status of the fix attempt (SUCCESS, FAILED, ERROR).
    trace_file : str
        Path to the saved trace file.
    summary_file : str
        Path to the saved summary file.
    error_message : str | None
        Error message if fix failed.

    """

    status: str
    trace_file: str
    summary_file: str
    error_message: str | None = None
