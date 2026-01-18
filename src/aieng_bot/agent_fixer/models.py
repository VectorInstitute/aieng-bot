"""Data models for agent fixer."""

from dataclasses import dataclass


@dataclass
class AgenticLoopRequest:
    """Request for running the full agentic fix loop.

    This model is used for the new simplified agentic fix flow where Claude
    handles the entire fix-wait-check-retry loop autonomously.

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
    head_ref : str
        PR source branch name (e.g., dependabot/uv/pytest-cov-7.0.0).
    base_ref : str
        PR target branch name (e.g., main).
    failure_types : list[str]
        Pre-classified failure types (lint, test, build, security, merge_conflict, merge_only, unknown).
        Multiple types can be present for PRs with multiple issues.
    failure_logs_file : str
        Path to file containing initial failure logs.
    max_retries : int
        Maximum number of fix attempts before giving up.
    timeout_minutes : int
        Maximum time for entire fix loop in minutes.
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
    head_ref: str
    base_ref: str
    failure_types: list[str]
    failure_logs_file: str
    max_retries: int
    timeout_minutes: int
    workflow_run_id: str
    github_run_url: str
    cwd: str

    @property
    def failure_type(self) -> str:
        """Return primary failure type for backward compatibility."""
        return self.failure_types[0] if self.failure_types else "unknown"

    @property
    def failure_types_str(self) -> str:
        """Return failure types as comma-separated string."""
        return ",".join(self.failure_types)


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
    head_ref : str
        PR source branch name (e.g., dependabot/uv/pytest-cov-7.0.0).
    base_ref : str
        PR target branch name (e.g., main).
    failure_types : list[str]
        Types of failure (test, lint, security, build, merge_conflict).
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
    head_ref: str
    base_ref: str
    failure_types: list[str]
    failed_check_names: str
    failure_logs_file: str
    workflow_run_id: str
    github_run_url: str
    cwd: str

    @property
    def failure_type(self) -> str:
        """Return primary failure type for backward compatibility."""
        return self.failure_types[0] if self.failure_types else "unknown"


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
