"""Tests for agent fixer module."""

import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from aieng_bot.agent_fixer import (
    AgentFixer,
    AgentFixResult,
    AgenticLoopRequest,
)
from aieng_bot.agent_fixer.fixer import AGENTIC_LOOP_TOOLS


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


class TestAgentFixerInit:
    """Test AgentFixer initialization."""

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


class TestAgenticLoopRequest:
    """Test AgenticLoopRequest dataclass."""

    def test_create_request(self):
        """Test creating an agentic loop request with all required fields."""
        request = AgenticLoopRequest(
            repo="VectorInstitute/test-repo",
            pr_number=123,
            pr_title="Bump dependency",
            pr_author="app/dependabot",
            pr_url="https://github.com/VectorInstitute/test-repo/pull/123",
            head_ref="dependabot/pytest-8.0.0",
            base_ref="main",
            failure_types=["lint"],
            failed_check_names=["lint-check"],
            failure_logs_file=".failure-logs.txt",
            max_retries=3,
            timeout_minutes=330,
            workflow_run_id="1234567890",
            github_run_url="https://github.com/runs/123",
            cwd="/path/to/repo",
        )

        assert request.repo == "VectorInstitute/test-repo"
        assert request.pr_number == 123
        assert request.failure_type == "lint"
        assert request.max_retries == 3
        assert request.timeout_minutes == 330
        assert request.cwd == "/path/to/repo"

    def test_failure_type_empty_list(self):
        """Test that the failure_type property guards against empty lists."""
        request = AgenticLoopRequest(
            repo="test/repo",
            pr_number=1,
            pr_title="t",
            pr_author="a",
            pr_url="u",
            head_ref="h",
            base_ref="main",
            failure_types=[],
            failed_check_names=[],
            failure_logs_file="logs.txt",
            max_retries=1,
            timeout_minutes=1,
            workflow_run_id="1",
            github_run_url="u",
            cwd="/cwd",
        )

        assert request.failure_type == "unknown"
        assert request.failure_types_str == ""

    def test_request_fields(self):
        """Test that request fields are properly typed."""
        request = AgenticLoopRequest(
            repo="test/repo",
            pr_number=456,
            pr_title="Fix bug",
            pr_author="user",
            pr_url="https://github.com/test/repo/pull/456",
            head_ref="feature/fix",
            base_ref="main",
            failure_types=["test"],
            failed_check_names=["unit-tests"],
            failure_logs_file="logs.txt",
            max_retries=5,
            timeout_minutes=180,
            workflow_run_id="999",
            github_run_url="https://url",
            cwd="/cwd",
        )

        assert isinstance(request.repo, str)
        assert isinstance(request.pr_number, int)
        assert isinstance(request.failure_type, str)
        assert isinstance(request.max_retries, int)
        assert isinstance(request.timeout_minutes, int)


class TestAgenticLoop:
    """Test agentic loop functionality."""

    @pytest.fixture
    def agentic_request(self, tmp_path):
        """Create a test agentic loop request."""
        logs_file = tmp_path / ".failure-logs.txt"
        logs_file.write_text("Error: test failed\nAssertion error at line 42")

        return AgenticLoopRequest(
            repo="VectorInstitute/test-repo",
            pr_number=123,
            pr_title="Bump pytest",
            pr_author="app/dependabot",
            pr_url="https://github.com/VectorInstitute/test-repo/pull/123",
            head_ref="dependabot/pytest-8.0.0",
            base_ref="main",
            failure_types=["test"],
            failed_check_names=["pytest-tests"],
            failure_logs_file=str(logs_file),
            max_retries=3,
            timeout_minutes=330,
            workflow_run_id="1234567890",
            github_run_url="https://github.com/runs/123",
            cwd=str(tmp_path),
        )

    @pytest.fixture
    def mock_tracer(self):
        """Create a mock tracer whose capture passes the stream through."""

        async def mock_capture_stream(stream):
            async for msg in stream:
                yield msg

        tracer = MagicMock()
        tracer.capture_agent_stream = mock_capture_stream
        tracer.get_summary.return_value = "Fixed and merged PR"
        tracer.save_trace = MagicMock()
        tracer.extract_file_metrics.return_value = (
            3,
            ["/src/app.py", "/tests/test_app.py"],
        )
        return tracer

    def test_write_agentic_context(self, agentic_request, tmp_path):
        """Test writing agentic loop context to JSON file."""
        import json  # noqa: PLC0415 - Import after test setup

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()
            fixer._write_agentic_context(agentic_request)

            context_file = tmp_path / ".pr-context.json"
            assert context_file.exists()

            with open(context_file) as f:
                context = json.load(f)

            assert context["repo"] == "VectorInstitute/test-repo"
            assert context["pr_number"] == 123
            assert context["pr_title"] == "Bump pytest"
            assert context["head_ref"] == "dependabot/pytest-8.0.0"
            assert context["max_retries"] == 3
            assert context["timeout_minutes"] == 330

    def test_build_agentic_prompt(self, agentic_request):
        """Test building agentic loop prompt."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()
            prompt = fixer._build_agentic_prompt(agentic_request)

            assert "aieng-bot" in prompt
            assert "Your job is not done until the PR is merged" in prompt
            assert "Skills (Context Only)" in prompt
            assert "/python-conventions" in prompt
            assert "/merge-resolution" in prompt
            assert "/fix-security-failures" in prompt
            assert ".pr-context.json" in prompt
            assert ".failure-logs.txt" in prompt
            assert "gh pr checks" in prompt
            assert "gh pr merge" in prompt
            assert "max retries (3)" in prompt

    def test_build_agentic_prompt_no_merge(self, agentic_request):
        """Test building agentic loop prompt with merge disabled."""
        agentic_request.merge_pr = False

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()
            prompt = fixer._build_agentic_prompt(agentic_request)

            assert "aieng-bot" in prompt
            assert "Do NOT merge the PR" in prompt
            assert "gh pr merge" not in prompt
            assert "Your job is not done until CI passes" in prompt
            assert "gh pr checks" in prompt
            assert "max retries (3)" in prompt

    def test_build_agentic_prompt_empty_failure_types(self, agentic_request):
        """Test that an empty failure_types list does not crash prompt building."""
        agentic_request.failure_types = []

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()
            prompt = fixer._build_agentic_prompt(agentic_request)

            assert "unknown" in prompt

    def test_create_agentic_tracer(self, agentic_request):
        """Test creating an execution tracer for agentic loop."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()
            tracer = fixer._create_agentic_tracer(agentic_request)

            assert tracer.trace["metadata"]["pr"]["repo"] == "VectorInstitute/test-repo"
            assert tracer.trace["metadata"]["pr"]["number"] == 123
            # Failure type is now pre-classified before the agent runs
            assert tracer.trace["metadata"]["failure"]["type"] == "test"
            assert tracer.trace["metadata"]["workflow_run_id"] == "1234567890"
            # Trace metadata records the actual tool set and configured model
            assert tracer.trace["execution"]["tools_allowed"] == AGENTIC_LOOP_TOOLS
            assert tracer.trace["execution"]["model"]

    @pytest.mark.asyncio
    async def test_run_agentic_loop_success(self, agentic_request, mock_tracer):
        """Test successful agentic loop execution."""

        async def mock_stream():
            yield MagicMock()

        def mock_query(*args, **kwargs):
            return mock_stream()

        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch(
                "aieng_bot.agent_fixer.fixer.claude_agent_sdk.query",
                side_effect=mock_query,
            ),
            patch.object(
                AgentFixer, "_create_agentic_tracer", return_value=mock_tracer
            ),
            patch("builtins.open", mock_open()),
        ):
            fixer = AgentFixer()
            result = await fixer.run_agentic_loop(agentic_request)

            assert result.status == "SUCCESS"
            assert result.trace_file == "/tmp/agent-execution-trace.json"
            assert result.summary_file == "/tmp/fix-summary.txt"
            assert result.error_message is None

            mock_tracer.finalize.assert_called_once_with(
                status="SUCCESS",
                changes_made=3,
                files_modified=["/src/app.py", "/tests/test_app.py"],
            )
            mock_tracer.save_trace.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_agentic_loop_uses_correct_options(
        self, agentic_request, mock_tracer
    ):
        """Test that the agent is invoked with the full agentic tool set."""

        async def mock_stream():
            yield MagicMock()

        mock_query_func = MagicMock(side_effect=lambda *args, **kwargs: mock_stream())

        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch(
                "aieng_bot.agent_fixer.fixer.claude_agent_sdk.query", mock_query_func
            ),
            patch.object(
                AgentFixer, "_create_agentic_tracer", return_value=mock_tracer
            ),
            patch("builtins.open", mock_open()),
        ):
            fixer = AgentFixer()
            await fixer.run_agentic_loop(agentic_request)

            mock_query_func.assert_called_once()
            options = mock_query_func.call_args.kwargs["options"]
            assert options.allowed_tools == AGENTIC_LOOP_TOOLS
            assert options.permission_mode == "acceptEdits"
            assert options.cwd == agentic_request.cwd
            assert options.setting_sources == ["project"]

    @pytest.mark.asyncio
    async def test_run_agentic_loop_failure_saves_trace(
        self, agentic_request, mock_tracer
    ):
        """Test that a failed run still finalizes and saves the trace."""
        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch(
                "aieng_bot.agent_fixer.fixer.claude_agent_sdk.query",
                side_effect=RuntimeError("Agent failed"),
            ),
            patch.object(
                AgentFixer, "_create_agentic_tracer", return_value=mock_tracer
            ),
            patch("builtins.open", mock_open()),
        ):
            fixer = AgentFixer()
            result = await fixer.run_agentic_loop(agentic_request)

            assert result.status == "FAILED"
            assert result.error_message == "Agent failed"
            # The trace captured up to the failure is preserved for debugging
            assert result.trace_file == "/tmp/agent-execution-trace.json"
            assert result.summary_file == "/tmp/fix-summary.txt"
            mock_tracer.finalize.assert_called_once_with(
                status="FAILED",
                changes_made=3,
                files_modified=["/src/app.py", "/tests/test_app.py"],
            )
            mock_tracer.save_trace.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_agentic_loop_trace_save_failure(
        self, agentic_request, mock_tracer
    ):
        """Test that a trace-save failure yields empty file paths."""

        async def mock_stream():
            yield MagicMock()

        mock_tracer.save_trace.side_effect = OSError("disk full")

        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch(
                "aieng_bot.agent_fixer.fixer.claude_agent_sdk.query",
                side_effect=lambda *args, **kwargs: mock_stream(),
            ),
            patch.object(
                AgentFixer, "_create_agentic_tracer", return_value=mock_tracer
            ),
        ):
            fixer = AgentFixer()
            result = await fixer.run_agentic_loop(agentic_request)

            assert result.status == "SUCCESS"
            assert result.trace_file == ""
            assert result.summary_file == ""
