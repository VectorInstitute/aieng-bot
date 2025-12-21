"""Tests for agent fixer module."""

import os
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from aieng_bot_maintain.agent_fixer import AgentFixer, AgentFixRequest, AgentFixResult


class TestAgentFixRequest:
    """Test AgentFixRequest dataclass."""

    def test_create_request(self):
        """Test creating a fix request with all required fields."""
        request = AgentFixRequest(
            repo="VectorInstitute/test-repo",
            pr_number=123,
            pr_title="Bump dependency",
            pr_author="app/dependabot",
            pr_url="https://github.com/VectorInstitute/test-repo/pull/123",
            failure_type="test",
            failed_check_names="Run Tests,Lint",
            prompt_file=".github/prompts/fix-test-failures.md",
            failure_logs_file=".failure-logs.txt",
            workflow_run_id="1234567890",
            github_run_url="https://github.com/runs/123",
            cwd="/path/to/repo",
        )

        assert request.repo == "VectorInstitute/test-repo"
        assert request.pr_number == 123
        assert request.failure_type == "test"
        assert request.cwd == "/path/to/repo"

    def test_request_immutable_fields(self):
        """Test that request fields are properly typed."""
        request = AgentFixRequest(
            repo="test/repo",
            pr_number=456,
            pr_title="Fix bug",
            pr_author="user",
            pr_url="https://github.com/test/repo/pull/456",
            failure_type="lint",
            failed_check_names="ESLint",
            prompt_file="prompts/lint.md",
            failure_logs_file="logs.txt",
            workflow_run_id="999",
            github_run_url="https://url",
            cwd="/cwd",
        )

        # Verify types
        assert isinstance(request.repo, str)
        assert isinstance(request.pr_number, int)
        assert isinstance(request.failure_type, str)


class TestAgentFixResult:
    """Test AgentFixResult dataclass."""

    def test_create_success_result(self):
        """Test creating a successful fix result."""
        result = AgentFixResult(
            status="SUCCESS",
            trace_file="/tmp/trace.json",
            summary_file="/tmp/summary.txt",
        )

        assert result.status == "SUCCESS"
        assert result.trace_file == "/tmp/trace.json"
        assert result.summary_file == "/tmp/summary.txt"
        assert result.error_message is None

    def test_create_failed_result(self):
        """Test creating a failed fix result with error message."""
        result = AgentFixResult(
            status="FAILED",
            trace_file="",
            summary_file="",
            error_message="Agent execution failed",
        )

        assert result.status == "FAILED"
        assert result.error_message == "Agent execution failed"

    def test_result_default_error_message(self):
        """Test that error_message defaults to None."""
        result = AgentFixResult(
            status="SUCCESS",
            trace_file="/tmp/trace.json",
            summary_file="/tmp/summary.txt",
        )

        assert result.error_message is None


class TestAgentFixer:
    """Test AgentFixer class."""

    @pytest.fixture
    def fix_request(self, tmp_path):
        """Create a test fix request."""
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text(
            "Fix {{REPO_NAME}} PR #{{PR_NUMBER}}\n"
            "Title: {{PR_TITLE}}\n"
            "Author: {{PR_AUTHOR}}\n"
            "Failed: {{FAILED_CHECK_NAME}}\n"
            "Details: {{FAILURE_DETAILS}}"
        )

        logs_file = tmp_path / ".failure-logs.txt"
        logs_file.write_text("Error: test failed\nAssertion error at line 42")

        return AgentFixRequest(
            repo="VectorInstitute/test-repo",
            pr_number=123,
            pr_title="Bump pytest",
            pr_author="app/dependabot",
            pr_url="https://github.com/VectorInstitute/test-repo/pull/123",
            failure_type="test",
            failed_check_names="Run Tests",
            prompt_file=str(prompt_file),
            failure_logs_file=str(logs_file),
            workflow_run_id="1234567890",
            github_run_url="https://github.com/runs/123",
            cwd=str(tmp_path),
        )

    def test_init_without_api_key(self):
        """Test that fixer raises error if ANTHROPIC_API_KEY not set."""
        with (
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(ValueError, match="ANTHROPIC_API_KEY"),
        ):
            AgentFixer()

    def test_init_with_api_key(self):
        """Test that fixer initializes successfully with API key."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()
            assert fixer.api_key == "test-key"

    def test_load_prompt_template(self, fix_request):
        """Test loading and populating prompt template."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()
            prompt = fixer._load_prompt_template(fix_request)

            assert "VectorInstitute/test-repo" in prompt
            assert "123" in prompt
            assert "Bump pytest" in prompt
            assert "app/dependabot" in prompt
            assert "Run Tests" in prompt
            assert ".failure-logs.txt" in prompt

    def test_load_prompt_template_missing_file(self, fix_request):
        """Test loading prompt template when file doesn't exist."""
        fix_request.prompt_file = "/nonexistent/prompt.md"

        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            pytest.raises(FileNotFoundError, match="Prompt template not found"),
        ):
            fixer = AgentFixer()
            fixer._load_prompt_template(fix_request)

    def test_load_prompt_template_missing_logs(self, fix_request, tmp_path):
        """Test loading prompt template when logs file doesn't exist."""
        fix_request.failure_logs_file = str(tmp_path / "missing-logs.txt")

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()
            prompt = fixer._load_prompt_template(fix_request)

            assert "No failure logs available" in prompt

    def test_build_final_prompt(self):
        """Test building final prompt with task instructions."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()
            base_prompt = "Fix the test failures"
            final_prompt = fixer._build_final_prompt(base_prompt)

            assert "Fix the test failures" in final_prompt
            assert "## Your Task" in final_prompt
            assert "Analyze the failures" in final_prompt
            assert "Make minimal, targeted changes" in final_prompt
            assert "Don't skip tests" in final_prompt

    def test_create_tracer(self, fix_request):
        """Test creating an execution tracer."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()
            tracer = fixer._create_tracer(fix_request)

            assert tracer.trace["metadata"]["pr"]["repo"] == "VectorInstitute/test-repo"
            assert tracer.trace["metadata"]["pr"]["number"] == 123
            assert tracer.trace["metadata"]["failure"]["type"] == "test"
            assert tracer.trace["metadata"]["workflow_run_id"] == "1234567890"

    @pytest.mark.asyncio
    async def test_apply_fixes_success(self, fix_request, tmp_path):
        """Test successful application of fixes."""

        # Mock agent stream
        async def mock_stream():
            yield MagicMock()

        # Create a mock tracer with proper async generator
        async def mock_capture_stream(stream):
            async for msg in mock_stream():
                yield msg

        mock_tracer = MagicMock()
        mock_tracer.capture_agent_stream = mock_capture_stream
        mock_tracer.get_summary.return_value = "Fixed 1 test"
        mock_tracer.save_trace = MagicMock()

        mock_query = AsyncMock(return_value=mock_stream())

        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("aieng_bot_maintain.agent_fixer.fixer.query", mock_query),
            patch.object(AgentFixer, "_create_tracer", return_value=mock_tracer),
            patch("builtins.open", mock_open()),
        ):
            fixer = AgentFixer()
            result = await fixer.apply_fixes(fix_request)

            assert result.status == "SUCCESS"
            assert result.trace_file == "/tmp/agent-execution-trace.json"
            assert result.summary_file == "/tmp/fix-summary.txt"
            assert result.error_message is None

            mock_tracer.finalize.assert_called_once_with(status="SUCCESS")
            mock_tracer.save_trace.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_fixes_failure(self, fix_request):
        """Test handling of agent execution failure."""
        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch(
                "aieng_bot_maintain.agent_fixer.fixer.query",
                side_effect=RuntimeError("Agent failed"),
            ),
        ):
            fixer = AgentFixer()
            result = await fixer.apply_fixes(fix_request)

            assert result.status == "FAILED"
            assert result.error_message == "Agent failed"
            assert result.trace_file == ""
            assert result.summary_file == ""

    @pytest.mark.asyncio
    async def test_apply_fixes_prompt_not_found(self, fix_request):
        """Test handling when prompt file not found."""
        fix_request.prompt_file = "/nonexistent/prompt.md"

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()
            result = await fixer.apply_fixes(fix_request)

            assert result.status == "FAILED"
            assert "Prompt template not found" in result.error_message

    @pytest.mark.asyncio
    async def test_apply_fixes_calls_agent_with_correct_options(
        self, fix_request, tmp_path
    ):
        """Test that agent is called with correct options."""

        async def mock_stream():
            yield MagicMock()

        # Create a mock tracer with proper async generator
        async def mock_capture_stream(stream):
            async for msg in mock_stream():
                yield msg

        mock_tracer = MagicMock()
        mock_tracer.capture_agent_stream = mock_capture_stream
        mock_tracer.get_summary.return_value = "Summary"
        mock_tracer.save_trace = MagicMock()

        mock_query = AsyncMock(return_value=mock_stream())

        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("aieng_bot_maintain.agent_fixer.fixer.query", mock_query),
            patch.object(AgentFixer, "_create_tracer", return_value=mock_tracer),
            patch("builtins.open", mock_open()),
        ):
            fixer = AgentFixer()
            await fixer.apply_fixes(fix_request)

            # Verify query was called
            mock_query.assert_called_once()
            call_args = mock_query.call_args

            # Check prompt argument
            assert "VectorInstitute/test-repo" in call_args.kwargs["prompt"]
            assert "## Your Task" in call_args.kwargs["prompt"]

            # Check options
            options = call_args.kwargs["options"]
            assert options.allowed_tools == ["Read", "Edit", "Bash", "Glob", "Grep"]
            assert options.permission_mode == "acceptEdits"
            assert options.cwd == str(tmp_path)
