"""Tests for agent fixer module."""

import os
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
from claude_agent_sdk import ResultMessage

from aieng_bot.agent_fixer import (
    AgentFixer,
    AgentFixResult,
    AgenticLoopRequest,
)
from aieng_bot.agent_fixer.fixer import AGENTIC_LOOP_TOOLS
from aieng_bot.utils.github_client import PRStatus


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

    @pytest.fixture
    def github_status(self):
        """Patch the fixer's GitHub client; tests set get_pr_status results."""
        client = MagicMock()
        client.get_pr_status.return_value = PRStatus(
            state="MERGED", passed=["unit-tests"]
        )
        with (
            patch("aieng_bot.agent_fixer.fixer.GitHubClient", return_value=client),
            patch("aieng_bot.agent_fixer.fixer.asyncio.sleep", new=AsyncMock()),
        ):
            yield client.get_pr_status

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
    async def test_run_agentic_loop_success(
        self, agentic_request, mock_tracer, github_status
    ):
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
        self, agentic_request, mock_tracer, github_status
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
            # Long commands must not be backgrounded: nothing resumes the
            # session when a background job finishes
            assert options.env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == "1"
            assert int(options.env["BASH_DEFAULT_TIMEOUT_MS"]) >= 30 * 60 * 1000

    @pytest.mark.asyncio
    async def test_run_agentic_loop_failure_saves_trace(
        self, agentic_request, mock_tracer, github_status
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
        self, agentic_request, mock_tracer, github_status
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

    @staticmethod
    def _session_stream(session_id, result_text="Done"):
        """Build a query() side effect yielding one ResultMessage per call."""

        def mock_query(*args, **kwargs):
            async def stream():
                result = MagicMock(spec=ResultMessage)
                result.session_id = session_id
                result.result = result_text
                yield result

            return stream()

        return mock_query

    @pytest.mark.asyncio
    async def test_run_agentic_loop_resumes_after_ci_wait(
        self, agentic_request, mock_tracer, github_status
    ):
        """Test the harness waits for CI and resumes the same session."""
        github_status.side_effect = [
            PRStatus(state="OPEN", pending=["docker-build"]),
            PRStatus(state="OPEN", failed=["docker-build"]),
            PRStatus(state="MERGED", passed=["docker-build"]),
        ]
        mock_query_func = MagicMock(side_effect=self._session_stream("sess-1"))

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
            result = await fixer.run_agentic_loop(agentic_request)

        assert result.status == "SUCCESS"
        assert mock_query_func.call_count == 2
        first, second = mock_query_func.call_args_list
        assert first.kwargs["options"].resume is None
        assert second.kwargs["options"].resume == "sess-1"
        assert "CI has finished for PR #123" in second.kwargs["prompt"]
        assert "failed: docker-build" in second.kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_run_agentic_loop_fails_when_pr_not_merged(
        self, agentic_request, mock_tracer, github_status
    ):
        """Test a clean agent exit is FAILED when GitHub shows the PR unmerged."""
        github_status.side_effect = [
            PRStatus(state="OPEN", pending=["docker-build"]),
            PRStatus(state="OPEN", failed=["docker-build"], passed=["unit-tests"]),
            PRStatus(state="OPEN", pending=["docker-build"]),
            PRStatus(state="OPEN", failed=["docker-build"], passed=["unit-tests"]),
        ]
        mock_query_func = MagicMock(side_effect=self._session_stream("sess-1"))

        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch(
                "aieng_bot.agent_fixer.fixer.claude_agent_sdk.query", mock_query_func
            ),
            patch("aieng_bot.agent_fixer.fixer.MAX_AGENT_SESSIONS", 2),
            patch.object(
                AgentFixer, "_create_agentic_tracer", return_value=mock_tracer
            ),
            patch("builtins.open", mock_open()),
        ):
            fixer = AgentFixer()
            result = await fixer.run_agentic_loop(agentic_request)

        assert result.status == "FAILED"
        assert mock_query_func.call_count == 2
        assert result.error_message is not None
        assert "failed: docker-build" in result.error_message
        mock_tracer.finalize.assert_called_once_with(
            status="FAILED",
            changes_made=3,
            files_modified=["/src/app.py", "/tests/test_app.py"],
        )

    @pytest.mark.asyncio
    async def test_run_agentic_loop_fails_when_pr_closed(
        self, agentic_request, mock_tracer, github_status
    ):
        """Test a PR closed without merging is reported as FAILED."""
        github_status.return_value = PRStatus(state="CLOSED")

        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch(
                "aieng_bot.agent_fixer.fixer.claude_agent_sdk.query",
                side_effect=self._session_stream("sess-1"),
            ),
            patch.object(
                AgentFixer, "_create_agentic_tracer", return_value=mock_tracer
            ),
            patch("builtins.open", mock_open()),
        ):
            fixer = AgentFixer()
            result = await fixer.run_agentic_loop(agentic_request)

        assert result.status == "FAILED"
        assert result.error_message == "PR is CLOSED but was not merged by the bot"

    @pytest.mark.asyncio
    async def test_run_agentic_loop_no_merge_succeeds_on_green_ci(
        self, agentic_request, mock_tracer, github_status
    ):
        """Test --no-merge runs succeed once every check passes."""
        agentic_request.merge_pr = False
        github_status.return_value = PRStatus(state="OPEN", passed=["unit-tests"])
        mock_query_func = MagicMock(side_effect=self._session_stream("sess-1"))

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
            result = await fixer.run_agentic_loop(agentic_request)

        assert result.status == "SUCCESS"
        mock_query_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_for_checks_waits_for_checks_to_register(
        self, agentic_request, github_status
    ):
        """Test an empty check list right after a push is not read as a pass."""
        github_status.side_effect = [
            PRStatus(state="OPEN"),
            PRStatus(state="OPEN", pending=["unit-tests"]),
            PRStatus(state="OPEN", passed=["unit-tests"]),
        ]

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            fixer = AgentFixer()
            client = MagicMock(get_pr_status=github_status)
            status, waited = await fixer._wait_for_checks(
                client, agentic_request, deadline=float("inf")
            )

        assert status.passed == ["unit-tests"]
        assert waited
        assert github_status.call_count == 3

    @pytest.mark.asyncio
    async def test_run_agentic_loop_stops_when_agent_declines(
        self, agentic_request, mock_tracer, github_status
    ):
        """Test the agent is not resumed when CI had already failed at stop."""
        github_status.return_value = PRStatus(
            state="OPEN", failed=["docker-build"], passed=["unit-tests"]
        )
        mock_query_func = MagicMock(
            side_effect=self._session_stream(
                "sess-1", "Not merging: docker-build also fails on main."
            )
        )

        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch(
                "aieng_bot.agent_fixer.fixer.claude_agent_sdk.query", mock_query_func
            ),
            patch.object(
                AgentFixer, "_create_agentic_tracer", return_value=mock_tracer
            ),
            patch("builtins.open", mock_open()) as mock_file,
        ):
            fixer = AgentFixer()
            result = await fixer.run_agentic_loop(agentic_request)

        assert result.status == "FAILED"
        mock_query_func.assert_called_once()
        # The reason is saved for the workflow's failure comment
        mock_file.assert_any_call("/tmp/fix-error.txt", "w")
        mock_file().write.assert_any_call(result.error_message)
        assert result.error_message is not None
        assert "failed: docker-build" in result.error_message
        assert "also fails on main" in result.error_message

    @pytest.mark.asyncio
    async def test_run_agentic_loop_resumes_green_unmerged_pr(
        self, agentic_request, mock_tracer, github_status
    ):
        """Test a green but unmerged PR resumes the agent to merge it."""
        github_status.side_effect = [
            PRStatus(state="OPEN", passed=["unit-tests"]),
            PRStatus(state="MERGED", passed=["unit-tests"]),
        ]
        mock_query_func = MagicMock(side_effect=self._session_stream("sess-1"))

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
            result = await fixer.run_agentic_loop(agentic_request)

        assert result.status == "SUCCESS"
        assert mock_query_func.call_count == 2

    @pytest.mark.asyncio
    async def test_run_agentic_loop_resumes_green_unmerged_pr_once(
        self, agentic_request, mock_tracer, github_status
    ):
        """Test a green PR the agent keeps declining to merge is resumed once."""
        github_status.return_value = PRStatus(state="OPEN", passed=["unit-tests"])
        mock_query_func = MagicMock(
            side_effect=self._session_stream("sess-1", "Merge rejected by ruleset.")
        )

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
            result = await fixer.run_agentic_loop(agentic_request)

        assert result.status == "FAILED"
        assert mock_query_func.call_count == 2
        assert result.error_message is not None
        assert "CI passed but the agent did not merge" in result.error_message
        assert "Merge rejected by ruleset." in result.error_message

    @pytest.mark.asyncio
    @pytest.mark.parametrize("waited", [False, True])
    async def test_run_agentic_loop_stops_when_review_required(
        self, agentic_request, mock_tracer, github_status, waited
    ):
        """Test a green PR held for a required review is not resumed."""
        green = PRStatus(
            state="OPEN", passed=["unit-tests"], review_decision="REVIEW_REQUIRED"
        )
        github_status.side_effect = (
            [PRStatus(state="OPEN", pending=["unit-tests"]), green]
            if waited
            else [green]
        )
        mock_query_func = MagicMock(side_effect=self._session_stream("sess-1"))

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
            result = await fixer.run_agentic_loop(agentic_request)

        assert result.status == "FAILED"
        mock_query_func.assert_called_once()
        assert result.error_message is not None
        assert "requires an approving review" in result.error_message
        assert "review=REVIEW_REQUIRED" in result.error_message

    @pytest.mark.asyncio
    async def test_run_agentic_loop_no_merge_ignores_review_requirement(
        self, agentic_request, mock_tracer, github_status
    ):
        """Test a required review does not fail a run that is not merging."""
        agentic_request.merge_pr = False
        github_status.return_value = PRStatus(
            state="OPEN", passed=["unit-tests"], review_decision="REVIEW_REQUIRED"
        )
        mock_query_func = MagicMock(side_effect=self._session_stream("sess-1"))

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
            result = await fixer.run_agentic_loop(agentic_request)

        assert result.status == "SUCCESS"
        mock_query_func.assert_called_once()
