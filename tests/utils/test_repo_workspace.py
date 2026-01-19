"""Tests for RepoWorkspace context manager."""

import os
import signal
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aieng_bot.utils.repo_workspace import RepoWorkspace


class TestRepoWorkspaceInit:
    """Tests for RepoWorkspace initialization."""

    def test_init_sets_attributes(self):
        """Test that initialization sets all required attributes."""
        workspace = RepoWorkspace(
            repo="owner/repo",
            pr_number=123,
            head_ref="feature-branch",
            base_ref="main",
            github_token="test-token",
            has_merge_conflicts=True,
        )

        assert workspace.repo == "owner/repo"
        assert workspace.pr_number == 123
        assert workspace.head_ref == "feature-branch"
        assert workspace.base_ref == "main"
        assert workspace.github_token == "test-token"
        assert workspace.has_merge_conflicts is True
        assert workspace._temp_dir is None

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        workspace = RepoWorkspace(
            repo="owner/repo",
            pr_number=456,
            head_ref="branch",
            base_ref="main",
        )

        assert workspace.github_token is None
        assert workspace.has_merge_conflicts is False


class TestRepoWorkspaceEnter:
    """Tests for RepoWorkspace __enter__ method."""

    @patch("aieng_bot.utils.repo_workspace.subprocess.run")
    @patch("aieng_bot.utils.repo_workspace.tempfile.mkdtemp")
    def test_enter_creates_temp_directory(self, mock_mkdtemp, mock_run):
        """Test that __enter__ creates a temp directory."""
        mock_mkdtemp.return_value = "/tmp/aieng-bot-owner-repo-pr123-abc123"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        workspace = RepoWorkspace(
            repo="owner/repo",
            pr_number=123,
            head_ref="feature",
            base_ref="main",
        )

        with workspace as working_dir:
            assert working_dir == "/tmp/aieng-bot-owner-repo-pr123-abc123"
            mock_mkdtemp.assert_called_once()
            assert "aieng-bot-owner-repo-pr123-" in mock_mkdtemp.call_args[1]["prefix"]

    @patch("aieng_bot.utils.repo_workspace.subprocess.run")
    @patch("aieng_bot.utils.repo_workspace.tempfile.mkdtemp")
    def test_enter_clones_repo(self, mock_mkdtemp, mock_run):
        """Test that __enter__ clones the repository."""
        mock_mkdtemp.return_value = "/tmp/workspace"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        workspace = RepoWorkspace(
            repo="owner/repo",
            pr_number=123,
            head_ref="feature",
            base_ref="main",
            github_token="token123",
        )

        with workspace:
            # Find the clone command call
            clone_calls = [
                call
                for call in mock_run.call_args_list
                if "gh" in call[0][0] and "clone" in call[0][0]
            ]
            assert len(clone_calls) == 1
            clone_cmd = clone_calls[0][0][0]
            assert "gh" in clone_cmd
            assert "repo" in clone_cmd
            assert "clone" in clone_cmd
            assert "owner/repo" in clone_cmd

    @patch("aieng_bot.utils.repo_workspace.subprocess.run")
    @patch("aieng_bot.utils.repo_workspace.tempfile.mkdtemp")
    def test_enter_fetches_and_checkouts_pr_branch(self, mock_mkdtemp, mock_run):
        """Test that __enter__ fetches and checks out the PR branch."""
        mock_mkdtemp.return_value = "/tmp/workspace"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        workspace = RepoWorkspace(
            repo="owner/repo",
            pr_number=123,
            head_ref="feature",
            base_ref="main",
        )

        with workspace:
            # Find fetch call
            fetch_calls = [
                call
                for call in mock_run.call_args_list
                if "git" in str(call[0][0]) and "fetch" in str(call[0][0])
            ]
            assert len(fetch_calls) >= 1

            # Find checkout call
            checkout_calls = [
                call
                for call in mock_run.call_args_list
                if "git" in str(call[0][0]) and "checkout" in str(call[0][0])
            ]
            assert len(checkout_calls) == 1

    @patch("aieng_bot.utils.repo_workspace.subprocess.run")
    @patch("aieng_bot.utils.repo_workspace.tempfile.mkdtemp")
    def test_enter_configures_git_user(self, mock_mkdtemp, mock_run):
        """Test that __enter__ configures git user."""
        mock_mkdtemp.return_value = "/tmp/workspace"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        workspace = RepoWorkspace(
            repo="owner/repo",
            pr_number=123,
            head_ref="feature",
            base_ref="main",
        )

        with workspace:
            config_calls = [
                call
                for call in mock_run.call_args_list
                if "git" in str(call[0][0]) and "config" in str(call[0][0])
            ]
            assert len(config_calls) >= 2  # user.email and user.name

    @patch("aieng_bot.utils.repo_workspace.subprocess.run")
    @patch("aieng_bot.utils.repo_workspace.tempfile.mkdtemp")
    def test_enter_attempts_merge_when_has_conflicts(self, mock_mkdtemp, mock_run):
        """Test that __enter__ attempts merge when has_merge_conflicts is True."""
        mock_mkdtemp.return_value = "/tmp/workspace"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        workspace = RepoWorkspace(
            repo="owner/repo",
            pr_number=123,
            head_ref="feature",
            base_ref="main",
            has_merge_conflicts=True,
        )

        with workspace:
            merge_calls = [
                call
                for call in mock_run.call_args_list
                if "git" in str(call[0][0]) and "merge" in str(call[0][0])
            ]
            assert len(merge_calls) == 1

    @patch("aieng_bot.utils.repo_workspace.subprocess.run")
    @patch("aieng_bot.utils.repo_workspace.tempfile.mkdtemp")
    def test_enter_skips_merge_when_no_conflicts(self, mock_mkdtemp, mock_run):
        """Test that __enter__ skips merge when has_merge_conflicts is False."""
        mock_mkdtemp.return_value = "/tmp/workspace"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        workspace = RepoWorkspace(
            repo="owner/repo",
            pr_number=123,
            head_ref="feature",
            base_ref="main",
            has_merge_conflicts=False,
        )

        with workspace:
            merge_calls = [
                call
                for call in mock_run.call_args_list
                if "git" in str(call[0][0]) and "merge" in str(call[0][0])
            ]
            assert len(merge_calls) == 0

    @patch("aieng_bot.utils.repo_workspace.os.path.exists", return_value=True)
    @patch("aieng_bot.utils.repo_workspace.shutil.rmtree")
    @patch("aieng_bot.utils.repo_workspace.subprocess.run")
    @patch("aieng_bot.utils.repo_workspace.tempfile.mkdtemp")
    def test_enter_raises_on_clone_failure(
        self, mock_mkdtemp, mock_run, mock_rmtree, mock_exists
    ):
        """Test that __enter__ raises RuntimeError on clone failure."""
        mock_mkdtemp.return_value = "/tmp/workspace"
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="clone failed"
        )

        workspace = RepoWorkspace(
            repo="owner/repo",
            pr_number=123,
            head_ref="feature",
            base_ref="main",
        )

        with (
            pytest.raises(RuntimeError, match="Failed to setup isolated workspace"),
            workspace,
        ):
            pass

        # Should cleanup on failure
        mock_rmtree.assert_called_once()


class TestRepoWorkspaceExit:
    """Tests for RepoWorkspace __exit__ method."""

    @patch("aieng_bot.utils.repo_workspace.os.path.exists", return_value=True)
    @patch("aieng_bot.utils.repo_workspace.shutil.rmtree")
    @patch("aieng_bot.utils.repo_workspace.subprocess.run")
    @patch("aieng_bot.utils.repo_workspace.tempfile.mkdtemp")
    def test_exit_cleans_up_temp_directory(
        self, mock_mkdtemp, mock_run, mock_rmtree, mock_exists
    ):
        """Test that __exit__ cleans up the temp directory."""
        mock_mkdtemp.return_value = "/tmp/workspace"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        workspace = RepoWorkspace(
            repo="owner/repo",
            pr_number=123,
            head_ref="feature",
            base_ref="main",
        )

        with workspace:
            pass

        mock_rmtree.assert_called_with("/tmp/workspace")

    @patch("aieng_bot.utils.repo_workspace.os.path.exists", return_value=True)
    @patch("aieng_bot.utils.repo_workspace.shutil.rmtree")
    @patch("aieng_bot.utils.repo_workspace.subprocess.run")
    @patch("aieng_bot.utils.repo_workspace.tempfile.mkdtemp")
    def test_exit_cleans_up_on_exception(
        self, mock_mkdtemp, mock_run, mock_rmtree, mock_exists
    ):
        """Test that __exit__ cleans up even when an exception occurs."""
        mock_mkdtemp.return_value = "/tmp/workspace"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        workspace = RepoWorkspace(
            repo="owner/repo",
            pr_number=123,
            head_ref="feature",
            base_ref="main",
        )

        with pytest.raises(ValueError), workspace:
            raise ValueError("test error")

        mock_rmtree.assert_called_with("/tmp/workspace")

    @patch("aieng_bot.utils.repo_workspace.shutil.rmtree")
    @patch("aieng_bot.utils.repo_workspace.subprocess.run")
    @patch("aieng_bot.utils.repo_workspace.tempfile.mkdtemp")
    def test_exit_handles_cleanup_errors_gracefully(
        self, mock_mkdtemp, mock_run, mock_rmtree
    ):
        """Test that __exit__ handles cleanup errors gracefully."""
        mock_mkdtemp.return_value = "/tmp/workspace"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_rmtree.side_effect = OSError("permission denied")

        workspace = RepoWorkspace(
            repo="owner/repo",
            pr_number=123,
            head_ref="feature",
            base_ref="main",
        )

        # Should not raise
        with (
            patch("aieng_bot.utils.repo_workspace.os.path.exists", return_value=True),
            workspace,
        ):
            pass


class TestRepoWorkspaceSignalHandling:
    """Tests for RepoWorkspace signal handling."""

    @patch("aieng_bot.utils.repo_workspace.os.path.exists", return_value=True)
    @patch("aieng_bot.utils.repo_workspace.shutil.rmtree")
    @patch("aieng_bot.utils.repo_workspace.subprocess.run")
    @patch("aieng_bot.utils.repo_workspace.tempfile.mkdtemp")
    def test_registers_signal_handlers(
        self, mock_mkdtemp, mock_run, mock_rmtree, mock_exists
    ):
        """Test that signal handlers are registered on enter."""
        mock_mkdtemp.return_value = "/tmp/workspace"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        workspace = RepoWorkspace(
            repo="owner/repo",
            pr_number=123,
            head_ref="feature",
            base_ref="main",
        )

        original_sigint = signal.getsignal(signal.SIGINT)

        with workspace:
            # Signal handler should be changed
            current_sigint = signal.getsignal(signal.SIGINT)
            assert current_sigint != original_sigint

        # Signal handler should be restored
        assert signal.getsignal(signal.SIGINT) == original_sigint

    @patch("aieng_bot.utils.repo_workspace.os.path.exists", return_value=True)
    @patch("aieng_bot.utils.repo_workspace.shutil.rmtree")
    @patch("aieng_bot.utils.repo_workspace.subprocess.run")
    @patch("aieng_bot.utils.repo_workspace.tempfile.mkdtemp")
    def test_signal_handler_raises_keyboard_interrupt_on_sigint(
        self, mock_mkdtemp, mock_run, mock_rmtree, mock_exists
    ):
        """Test that signal handler raises KeyboardInterrupt on SIGINT."""
        mock_mkdtemp.return_value = "/tmp/workspace"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        workspace = RepoWorkspace(
            repo="owner/repo",
            pr_number=123,
            head_ref="feature",
            base_ref="main",
        )

        with workspace, pytest.raises(KeyboardInterrupt):
            # Calling the signal handler directly should raise KeyboardInterrupt
            workspace._signal_handler(signal.SIGINT, None)


class TestRepoWorkspaceGetEnv:
    """Tests for RepoWorkspace _get_env method."""

    def test_get_env_includes_github_token(self):
        """Test that _get_env includes GH_TOKEN when github_token is set."""
        workspace = RepoWorkspace(
            repo="owner/repo",
            pr_number=123,
            head_ref="feature",
            base_ref="main",
            github_token="test-token-123",
        )

        env = workspace._get_env()

        assert env["GH_TOKEN"] == "test-token-123"

    def test_get_env_without_github_token(self):
        """Test that _get_env works without github_token."""
        workspace = RepoWorkspace(
            repo="owner/repo",
            pr_number=123,
            head_ref="feature",
            base_ref="main",
            github_token=None,
        )

        env = workspace._get_env()

        # Should not have GH_TOKEN if not explicitly set in environment
        if "GH_TOKEN" not in os.environ:
            assert "GH_TOKEN" not in env or env.get("GH_TOKEN") != "test-token-123"

    def test_get_env_preserves_existing_environment(self):
        """Test that _get_env preserves existing environment variables."""
        workspace = RepoWorkspace(
            repo="owner/repo",
            pr_number=123,
            head_ref="feature",
            base_ref="main",
        )

        env = workspace._get_env()

        # Should include PATH and other standard env vars
        assert "PATH" in env


class TestRepoWorkspaceIntegration:
    """Integration-style tests for RepoWorkspace."""

    @patch("aieng_bot.utils.repo_workspace.subprocess.run")
    def test_full_workflow_without_conflicts(self, mock_run):
        """Test full workspace workflow without merge conflicts."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with (
            tempfile.TemporaryDirectory() as actual_temp,
            patch(
                "aieng_bot.utils.repo_workspace.tempfile.mkdtemp",
                return_value=actual_temp,
            ),
        ):
            workspace = RepoWorkspace(
                repo="owner/repo",
                pr_number=123,
                head_ref="feature",
                base_ref="main",
                has_merge_conflicts=False,
            )

            with workspace as working_dir:
                assert working_dir == actual_temp
                # Can create files in the workspace
                test_file = Path(working_dir) / "test.txt"
                test_file.write_text("test content")
                assert test_file.exists()

    @patch("aieng_bot.utils.repo_workspace.subprocess.run")
    def test_full_workflow_with_conflicts(self, mock_run):
        """Test full workspace workflow with merge conflicts."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with (
            tempfile.TemporaryDirectory() as actual_temp,
            patch(
                "aieng_bot.utils.repo_workspace.tempfile.mkdtemp",
                return_value=actual_temp,
            ),
        ):
            workspace = RepoWorkspace(
                repo="owner/repo",
                pr_number=123,
                head_ref="feature",
                base_ref="main",
                has_merge_conflicts=True,
            )

            with workspace:
                # Verify merge was attempted
                merge_calls = [
                    call
                    for call in mock_run.call_args_list
                    if "merge" in str(call[0][0])
                ]
                assert len(merge_calls) == 1
