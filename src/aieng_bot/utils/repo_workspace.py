"""Isolated workspace management for PR fixes."""

from __future__ import annotations

import atexit
import contextlib
import os
import shutil
import signal
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .logging import log_error, log_info, log_success, log_warning

if TYPE_CHECKING:
    from types import FrameType


@dataclass
class RepoWorkspace:
    """Context manager for creating an isolated workspace for PR fixes.

    Creates a temporary directory, clones the repo, and checks out the PR branch.
    Cleans up the temp directory on exit, including on signals like SIGINT/SIGTERM.

    Parameters
    ----------
    repo : str
        Repository in format 'owner/repo'.
    pr_number : int
        Pull request number.
    head_ref : str
        Head branch reference (PR branch name).
    base_ref : str
        Base branch reference (target branch).
    github_token : str | None
        GitHub token for API access.
    has_merge_conflicts : bool
        If True, attempts to merge base branch into PR branch (allows failure).

    """

    repo: str
    pr_number: int
    head_ref: str
    base_ref: str
    github_token: str | None = None
    has_merge_conflicts: bool = False

    _temp_dir: str | None = field(default=None, init=False, repr=False)
    _original_sigint: Any = field(default=None, init=False, repr=False)
    _original_sigterm: Any = field(default=None, init=False, repr=False)
    _atexit_registered: bool = field(default=False, init=False, repr=False)

    def __enter__(self) -> str:
        """Create isolated workspace and return the working directory path.

        Returns
        -------
        str
            Path to the cloned repository working directory.

        Raises
        ------
        RuntimeError
            If cloning or checkout fails.

        """
        # Create temp directory
        self._temp_dir = tempfile.mkdtemp(
            prefix=f"aieng-bot-{self.repo.replace('/', '-')}-pr{self.pr_number}-"
        )
        log_info(f"Created isolated workspace: {self._temp_dir}")

        # Register cleanup handlers
        self._register_cleanup_handlers()

        try:
            self._clone_repo()
            self._checkout_pr_branch()
            self._configure_git()

            if self.has_merge_conflicts:
                self._attempt_base_merge()

            log_success(f"Workspace ready: {self._temp_dir}")
            return self._temp_dir

        except Exception as e:
            log_error(f"Failed to setup workspace: {e}")
            self._cleanup()
            raise RuntimeError(f"Failed to setup isolated workspace: {e}") from e

    def __exit__(
        self,
        exc_type: type[BaseException] | None,  # noqa: ARG002
        exc_val: BaseException | None,  # noqa: ARG002
        exc_tb: object,  # noqa: ARG002
    ) -> None:
        """Clean up the isolated workspace."""
        self._restore_signal_handlers()
        self._cleanup()

    def _register_cleanup_handlers(self) -> None:
        """Register signal handlers and atexit for cleanup."""
        # Save original signal handlers
        self._original_sigint = signal.getsignal(signal.SIGINT)
        self._original_sigterm = signal.getsignal(signal.SIGTERM)

        # Register our cleanup handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Register atexit handler
        atexit.register(self._cleanup)
        self._atexit_registered = True

    def _restore_signal_handlers(self) -> None:
        """Restore original signal handlers."""
        if self._original_sigint is not None:
            signal.signal(signal.SIGINT, self._original_sigint)
        if self._original_sigterm is not None:
            signal.signal(signal.SIGTERM, self._original_sigterm)

        # Unregister atexit handler
        if self._atexit_registered:
            with contextlib.suppress(Exception):
                atexit.unregister(self._cleanup)
            self._atexit_registered = False

    def _signal_handler(
        self,
        signum: int,
        frame: FrameType | None,  # noqa: ARG002
    ) -> None:
        """Handle signals by cleaning up and re-raising."""
        log_warning(f"Received signal {signum}, cleaning up workspace...")
        self._cleanup()
        self._restore_signal_handlers()

        # Re-raise the signal with default handler
        if signum == signal.SIGINT:
            raise KeyboardInterrupt
        if signum == signal.SIGTERM:
            raise SystemExit(128 + signum)

    def _cleanup(self) -> None:
        """Clean up the temporary directory."""
        if self._temp_dir and os.path.exists(self._temp_dir):
            try:
                shutil.rmtree(self._temp_dir)
                log_info(f"Cleaned up workspace: {self._temp_dir}")
            except Exception as e:
                log_warning(f"Failed to clean up workspace: {e}")
            finally:
                self._temp_dir = None

    def _get_env(self) -> dict[str, str]:
        """Get environment with GitHub token set."""
        env = os.environ.copy()
        if self.github_token:
            env["GH_TOKEN"] = self.github_token
        return env

    def _clone_repo(self) -> None:
        """Clone the repository to the temp directory."""
        assert self._temp_dir is not None, "_temp_dir must be set before cloning"
        log_info(f"Cloning {self.repo} (shallow clone)...")

        result = subprocess.run(
            [
                "gh",
                "repo",
                "clone",
                self.repo,
                self._temp_dir,
                "--",
                "--depth=1",
                "--no-single-branch",
            ],
            capture_output=True,
            text=True,
            env=self._get_env(),
            timeout=300,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to clone repo: {result.stderr}")

        log_success(f"Cloned {self.repo}")

    def _checkout_pr_branch(self) -> None:
        """Fetch and checkout the PR branch."""
        log_info(f"Fetching PR #{self.pr_number} branch...")

        # Fetch the PR branch
        result = subprocess.run(
            [
                "git",
                "fetch",
                "origin",
                f"refs/pull/{self.pr_number}/head:pr-{self.pr_number}",
            ],
            capture_output=True,
            text=True,
            cwd=self._temp_dir,
            env=self._get_env(),
            timeout=120,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to fetch PR branch: {result.stderr}")

        # Checkout the PR branch
        result = subprocess.run(
            ["git", "checkout", f"pr-{self.pr_number}"],
            capture_output=True,
            text=True,
            cwd=self._temp_dir,
            timeout=30,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to checkout PR branch: {result.stderr}")

        log_success(f"Checked out PR #{self.pr_number} branch")

    def _configure_git(self) -> None:
        """Configure git user for commits."""
        subprocess.run(
            ["git", "config", "user.email", "aieng-bot@vectorinstitute.ai"],
            capture_output=True,
            cwd=self._temp_dir,
            timeout=10,
            check=False,
        )
        subprocess.run(
            ["git", "config", "user.name", "AI Engineering Bot"],
            capture_output=True,
            cwd=self._temp_dir,
            timeout=10,
            check=False,
        )

    def _attempt_base_merge(self) -> None:
        """Attempt to merge base branch to expose merge conflicts.

        This allows the agent to see and resolve merge conflicts.
        Failure is expected and handled gracefully.
        """
        log_info(f"Attempting merge with {self.base_ref} to expose conflicts...")

        # First fetch the base branch
        subprocess.run(
            ["git", "fetch", "origin", self.base_ref],
            capture_output=True,
            text=True,
            cwd=self._temp_dir,
            env=self._get_env(),
            timeout=120,
            check=False,
        )

        # Attempt the merge (allow failure for conflicts)
        result = subprocess.run(
            ["git", "merge", f"origin/{self.base_ref}", "--no-edit"],
            capture_output=True,
            text=True,
            cwd=self._temp_dir,
            timeout=60,
            check=False,
        )

        if result.returncode == 0:
            log_success("Merge completed without conflicts")
        else:
            log_warning("Merge has conflicts - agent will need to resolve them")
