"""Tests for workflow client."""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from aieng_bot_maintain.auto_merger.models import PRQueueItem, PRStatus
from aieng_bot_maintain.auto_merger.workflow_client import WorkflowClient


@pytest.fixture
def workflow_client():
    """Create a WorkflowClient instance."""
    return WorkflowClient(gh_token="test-token")


@pytest.fixture
def sample_pr():
    """Sample PR for testing."""
    return PRQueueItem(
        repo="VectorInstitute/test-repo",
        pr_number=123,
        pr_title="Bump dependency",
        pr_author="dependabot[bot]",
        pr_url="https://github.com/VectorInstitute/test-repo/pull/123",
        status=PRStatus.PENDING,
        queued_at="2025-01-15T10:00:00Z",
        last_updated="2025-01-15T10:00:00Z",
    )


class TestWorkflowClient:
    """Test suite for WorkflowClient."""

    def test_init(self):
        """Test WorkflowClient initialization."""
        client = WorkflowClient(gh_token="token", bot_repo="VectorInstitute/bot")
        assert client.gh_token == "token"
        assert client.bot_repo == "VectorInstitute/bot"

    @patch("subprocess.run")
    def test_check_latest_comment_success(self, mock_run, workflow_client, sample_pr):
        """Test checking latest comment from dependabot."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Looks like this PR is already up-to-date with main!\n",
        )

        result = workflow_client.check_latest_comment(sample_pr)

        assert "already up-to-date" in result
        mock_run.assert_called_once()
        # Verify the gh command structure
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "gh"
        assert call_args[1] == "pr"
        assert call_args[2] == "view"
        assert str(sample_pr.pr_number) in call_args
        assert "--json" in call_args
        assert "comments" in call_args

    @patch("subprocess.run")
    def test_check_latest_comment_no_comments(
        self, mock_run, workflow_client, sample_pr
    ):
        """Test checking comments when none exist."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        result = workflow_client.check_latest_comment(sample_pr)

        assert result == ""

    @patch("subprocess.run")
    def test_check_latest_comment_failure(self, mock_run, workflow_client, sample_pr):
        """Test checking comments when command fails."""
        mock_run.side_effect = subprocess.CalledProcessError(1, ["gh"])

        result = workflow_client.check_latest_comment(sample_pr)

        assert result == ""

    @patch("subprocess.run")
    def test_check_latest_comment_custom_author(
        self, mock_run, workflow_client, sample_pr
    ):
        """Test checking latest comment from custom author."""
        mock_run.return_value = MagicMock(returncode=0, stdout="Some comment\n")

        result = workflow_client.check_latest_comment(sample_pr, author="custom-bot")

        assert result == "Some comment"
        # Verify custom author was used in jq filter
        call_args = mock_run.call_args[0][0]
        jq_filter = call_args[-1]
        assert "custom-bot" in jq_filter

    @patch("subprocess.run")
    def test_trigger_rebase_success(self, mock_run, workflow_client, sample_pr):
        """Test successful rebase triggering."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        result = workflow_client.trigger_rebase(sample_pr)

        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "gh" in call_args
        assert "pr" in call_args
        assert "comment" in call_args
        assert "@dependabot rebase" in call_args

    @patch("subprocess.run")
    def test_trigger_rebase_failure(self, mock_run, workflow_client, sample_pr):
        """Test rebase triggering failure."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "gh")

        result = workflow_client.trigger_rebase(sample_pr)

        assert result is False

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_trigger_fix_workflow_success(
        self, mock_run, mock_sleep, workflow_client, sample_pr
    ):
        """Test successful fix workflow triggering."""
        # First call: trigger workflow
        # Second call: get run list
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=0, stdout=json.dumps([{"databaseId": 789}])),
        ]

        run_id = workflow_client.trigger_fix_workflow(sample_pr)

        assert run_id == "789"
        assert mock_run.call_count == 2

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_trigger_fix_workflow_no_run_id(
        self, mock_run, mock_sleep, workflow_client, sample_pr
    ):
        """Test fix workflow triggering when run ID cannot be retrieved."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=0, stdout="[]"),
        ]

        run_id = workflow_client.trigger_fix_workflow(sample_pr)

        assert run_id is None

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_poll_workflow_status_success(self, mock_run, mock_sleep, workflow_client):
        """Test polling workflow status until success."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"status": "completed", "conclusion": "success"}),
        )

        status = workflow_client.poll_workflow_status("789", timeout_minutes=1)

        assert status == "SUCCESS"

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_poll_workflow_status_failure(self, mock_run, mock_sleep, workflow_client):
        """Test polling workflow status until failure."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"status": "completed", "conclusion": "failure"}),
        )

        status = workflow_client.poll_workflow_status("789", timeout_minutes=1)

        assert status == "FAILURE"

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_poll_workflow_status_timeout(self, mock_run, mock_sleep, workflow_client):
        """Test polling workflow status timeout."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"status": "in_progress", "conclusion": None}),
        )

        status = workflow_client.poll_workflow_status("789", timeout_minutes=1)

        assert status == "RUNNING"

    @patch("subprocess.run")
    def test_auto_merge_pr_success(self, mock_run, workflow_client, sample_pr):
        """Test successful auto-merge."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"reviewDecision": None})),
            MagicMock(returncode=0, stdout=""),  # approve
            MagicMock(returncode=0, stdout=""),  # merge
            MagicMock(returncode=0, stdout=""),  # comment
        ]

        result = workflow_client.auto_merge_pr(sample_pr)

        assert result is True
        assert mock_run.call_count == 4

    @patch("subprocess.run")
    def test_auto_merge_pr_already_approved(self, mock_run, workflow_client, sample_pr):
        """Test auto-merge when PR is already approved."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"reviewDecision": "APPROVED"})),
            MagicMock(returncode=0, stdout=""),  # merge
            MagicMock(returncode=0, stdout=""),  # comment
        ]

        result = workflow_client.auto_merge_pr(sample_pr)

        assert result is True
        assert mock_run.call_count == 3

    @patch("subprocess.run")
    def test_auto_merge_pr_failure(self, mock_run, workflow_client, sample_pr):
        """Test auto-merge failure."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "gh")

        result = workflow_client.auto_merge_pr(sample_pr)

        assert result is False
