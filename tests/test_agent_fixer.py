"""Tests for agent fixer module."""

import os
from unittest.mock import MagicMock, mock_open, patch

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

    def test_write_pr_context(self, fix_request, tmp_path):
        """Test writing PR context to JSON file."""
        import json

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()
            fixer._write_pr_context(fix_request)

            context_file = tmp_path / ".pr-context.json"
            assert context_file.exists()

            with open(context_file) as f:
                context = json.load(f)

            assert context["repo"] == "VectorInstitute/test-repo"
            assert context["pr_number"] == 123
            assert context["pr_title"] == "Bump pytest"
            assert context["pr_author"] == "app/dependabot"
            assert context["failure_type"] == "test"
            assert context["failed_checks"] == ["Run Tests"]

    def test_build_prompt(self, fix_request):
        """Test building simple prompt for skills."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()
            prompt = fixer._build_prompt(fix_request)

            assert "AI Engineering Maintenance Bot" in prompt
            assert "test check failures" in prompt
            assert ".pr-context.json" in prompt
            assert ".failure-logs.txt" in prompt
            assert "fix-test-failures skill" in prompt
            assert "minimal, targeted changes" in prompt

    def test_build_prompt_missing_logs(self, fix_request, tmp_path):
        """Test building prompt when logs file doesn't exist."""
        fix_request.failure_logs_file = str(tmp_path / "missing-logs.txt")

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()
            prompt = fixer._build_prompt(fix_request)

            assert "no failure logs (file not found)" in prompt

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

        # Create a regular mock function that returns the async generator
        def mock_query(*args, **kwargs):
            return mock_stream()

        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("aieng_bot_maintain.agent_fixer.fixer.query", side_effect=mock_query),
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
    async def test_apply_fixes_calls_agent_with_correct_options(
        self, fix_request, tmp_path
    ):
        """Test that agent is called with correct options including skills."""

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

        # Create a regular mock function that returns the async generator
        mock_query_func = MagicMock(side_effect=lambda *args, **kwargs: mock_stream())

        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("aieng_bot_maintain.agent_fixer.fixer.query", mock_query_func),
            patch.object(AgentFixer, "_create_tracer", return_value=mock_tracer),
            patch("builtins.open", mock_open()),
        ):
            fixer = AgentFixer()
            await fixer.apply_fixes(fix_request)

            # Verify query was called
            mock_query_func.assert_called_once()
            call_args = mock_query_func.call_args

            # Check prompt argument
            assert "AI Engineering Maintenance Bot" in call_args.kwargs["prompt"]
            assert "fix-test-failures skill" in call_args.kwargs["prompt"]
            assert ".pr-context.json" in call_args.kwargs["prompt"]

            # Check options
            options = call_args.kwargs["options"]
            assert options.allowed_tools == [
                "Read",
                "Edit",
                "Bash",
                "Glob",
                "Grep",
                "Skill",
            ]
            assert options.permission_mode == "acceptEdits"
            assert options.cwd == str(tmp_path)
            assert options.setting_sources == ["project"]  # Skills enabled!

    def test_pr_context_file_structure(self, fix_request, tmp_path):
        """Test that PR context file has all required fields."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()
            fixer._write_pr_context(fix_request)

            import json

            context_file = tmp_path / ".pr-context.json"
            with open(context_file) as f:
                context = json.load(f)

            # Verify all required fields are present
            assert "repo" in context
            assert "pr_number" in context
            assert "pr_title" in context
            assert "pr_author" in context
            assert "pr_url" in context
            assert "failure_type" in context
            assert "failed_checks" in context
            assert "failure_logs_file" in context

            # Verify types
            assert isinstance(context["pr_number"], int)
            assert isinstance(context["failed_checks"], list)

    def test_build_prompt_references_context_file(self, fix_request):
        """Test that prompt tells agent to read context file."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()
            prompt = fixer._build_prompt(fix_request)

            # Should mention the context file location
            assert ".pr-context.json" in prompt
            assert "PR metadata" in prompt or "context" in prompt.lower()

    def test_build_prompt_references_correct_skill(self, fix_request):
        """Test that prompt mentions the correct skill for failure type."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()

            # Test different failure types
            failure_types = ["test", "lint", "security", "build", "merge_conflict"]
            for failure_type in failure_types:
                fix_request.failure_type = failure_type
                prompt = fixer._build_prompt(fix_request)

                # Should reference the specific skill
                expected_skill = f"fix-{failure_type}-failures"
                assert expected_skill in prompt, (
                    f"Prompt should mention {expected_skill} skill"
                )
