"""Tests for agent execution tracer module."""

import os
import subprocess
from typing import Any
from unittest.mock import MagicMock, mock_open, patch

import pytest

from aieng_bot.observability import (
    AgentExecutionTracer,
    create_tracer_from_env,
)
from aieng_bot.observability.parsers import ResultMessageParser


class MockMessage:
    """Mock agent SDK message."""

    def __init__(self, content: str, class_name: str = "TextBlock"):
        """Initialize mock message.

        Parameters
        ----------
        content : str
            Message content.
        class_name : str, optional
            Class name for mock (default="TextBlock").

        """
        self.content = content
        self._class_name = class_name

    def __class__(self):
        """Mock class name."""
        return type(self._class_name, (), {})

    @property
    def __class__(self):  # noqa: F811
        """Mock class property."""

        class MockClass:
            def __init__(self, name: str):
                self.__name__ = name

        return MockClass(self._class_name)


class MockToolUseBlock:
    """Mock ToolUseBlock message."""

    def __init__(self, tool_name: str, tool_input: dict[str, Any], tool_id: str):
        """Initialize mock ToolUseBlock.

        Parameters
        ----------
        tool_name : str
            Tool name.
        tool_input : dict[str, Any]
            Tool input parameters.
        tool_id : str
            Tool use ID.

        """
        self.content = ""
        self.name = tool_name
        self.input = tool_input
        self.id = tool_id

    @property
    def __class__(self):
        """Mock class property."""

        class MockClass:
            __name__ = "ToolUseBlock"

        return MockClass()


class MockToolResultBlock:
    """Mock ToolResultBlock message."""

    def __init__(self, tool_use_id: str, is_error: bool = False):
        """Initialize mock ToolResultBlock.

        Parameters
        ----------
        tool_use_id : str
            Tool use ID.
        is_error : bool, optional
            Whether result is an error (default=False).

        """
        self.content = "Result content"
        self.tool_use_id = tool_use_id
        self.is_error = is_error

    @property
    def __class__(self):
        """Mock class property."""

        class MockClass:
            __name__ = "ToolResultBlock"

        return MockClass()

    def __str__(self):
        """Return string representation."""
        return f"ToolResultBlock(tool_use_id='{self.tool_use_id}', is_error={self.is_error})"


@pytest.fixture
def tracer():
    """Create an AgentExecutionTracer instance."""
    pr_info = {
        "repo": "VectorInstitute/test-repo",
        "number": 123,
        "title": "Fix test failures",
        "author": "dependabot[bot]",
        "url": "https://github.com/VectorInstitute/test-repo/pull/123",
    }
    failure_info = {
        "type": "test",
        "checks": ["pytest"],
    }
    return AgentExecutionTracer(
        pr_info=pr_info,
        failure_info=failure_info,
        workflow_run_id="12345",
        github_run_url="https://github.com/VectorInstitute/aieng-bot/actions/runs/12345",
    )


class TestAgentExecutionTracer:
    """Test suite for AgentExecutionTracer class."""

    def test_initialization(self, tracer):
        """Test tracer initialization."""
        assert tracer.pr_info["repo"] == "VectorInstitute/test-repo"
        assert tracer.failure_info["type"] == "test"
        assert tracer.workflow_run_id == "12345"
        assert tracer.event_sequence == 0
        assert len(tracer.trace["events"]) == 0
        assert tracer.trace["result"]["status"] == "IN_PROGRESS"

    def test_classify_message_error(self, tracer):
        """Test message classification for errors."""
        assert tracer.classifier.classify_by_content("Error: test failed") == "ERROR"
        assert tracer.classifier.classify_by_content("Failed to process") == "ERROR"
        assert tracer.classifier.classify_by_content("Exception occurred") == "ERROR"

    def test_classify_message_tool_call(self, tracer):
        """Test message classification for tool calls."""
        assert (
            tracer.classifier.classify_by_content("Reading file test.py") == "TOOL_CALL"
        )
        assert (
            tracer.classifier.classify_by_content("Editing src/main.py") == "TOOL_CALL"
        )
        assert (
            tracer.classifier.classify_by_content("Running bash command") == "TOOL_CALL"
        )

    def test_classify_message_reasoning(self, tracer):
        """Test message classification for reasoning."""
        assert (
            tracer.classifier.classify_by_content("Analyzing the test failure")
            == "REASONING"
        )
        assert (
            tracer.classifier.classify_by_content("Checking the configuration")
            == "REASONING"
        )
        assert (
            tracer.classifier.classify_by_content("Found an issue in the code")
            == "REASONING"
        )

    def test_classify_message_action(self, tracer):
        """Test message classification for actions."""
        assert tracer.classifier.classify_by_content("Applying the fix") == "ACTION"
        assert tracer.classifier.classify_by_content("Fixing the test") == "ACTION"
        assert tracer.classifier.classify_by_content("Updating the code") == "ACTION"

    def test_classify_message_info(self, tracer):
        """Test message classification for info."""
        assert tracer.classifier.classify_by_content("Processing complete") == "INFO"

    def test_extract_tool_info_read(self, tracer):
        """Test tool info extraction for Read tool."""
        info = tracer.tool_extractor.extract_from_content(
            "Reading file src/test.py", "TOOL_CALL"
        )
        assert info is not None
        assert info["tool"] == "Read"
        # Basic extraction works (exact format depends on regex)
        assert info["parameters"]["target"] is not None

    def test_extract_tool_info_not_tool_call(self, tracer):
        """Test tool info extraction for non-tool-call."""
        info = tracer.tool_extractor.extract_from_content("Some message", "INFO")
        assert info is None

    @pytest.mark.asyncio
    async def test_capture_agent_stream(self, tracer, capsys):
        """Test capturing agent stream."""

        async def mock_stream():
            yield MockMessage("Analyzing the code", "TextBlock")
            yield MockToolUseBlock("Read", {"file_path": "test.py"}, "tool_123")
            yield MockToolResultBlock("tool_123", is_error=False)

        captured_messages = []
        async for message in tracer.capture_agent_stream(mock_stream()):
            captured_messages.append(message)

        assert len(captured_messages) == 3
        assert len(tracer.trace["events"]) == 3
        assert tracer.trace["events"][0]["type"] == "REASONING"
        assert tracer.trace["events"][1]["type"] == "TOOL_CALL"
        assert tracer.trace["events"][1]["tool"] == "Read"
        assert tracer.trace["events"][2]["type"] == "TOOL_RESULT"

    @pytest.mark.asyncio
    async def test_capture_agent_stream_error(self, tracer):
        """Test capturing agent stream with error."""

        async def mock_stream():
            yield MockMessage("Processing...", "TextBlock")
            yield MockToolResultBlock("tool_456", is_error=True)

        async for _ in tracer.capture_agent_stream(mock_stream()):
            pass

        assert len(tracer.trace["events"]) == 2
        assert tracer.trace["events"][1]["type"] == "ERROR"

    def test_finalize(self, tracer):
        """Test finalizing trace."""
        tracer.finalize(
            status="SUCCESS",
            changes_made=3,
            files_modified=["src/test.py", "src/main.py"],
            commit_sha="abc123",
            commit_url="https://github.com/repo/commit/abc123",
        )

        assert tracer.trace["result"]["status"] == "SUCCESS"
        assert tracer.trace["result"]["changes_made"] == 3
        assert len(tracer.trace["result"]["files_modified"]) == 2
        assert tracer.trace["result"]["commit_sha"] == "abc123"
        assert tracer.trace["execution"]["end_time"] is not None
        assert tracer.trace["execution"]["duration_seconds"] is not None

    @patch("builtins.open", new_callable=mock_open)
    @patch("os.makedirs")
    def test_save_trace(self, mock_makedirs, mock_file, tracer, capsys):
        """Test saving trace to file."""
        tracer.save_trace("/tmp/trace.json")

        mock_makedirs.assert_called_once()
        mock_file.assert_called()
        captured = capsys.readouterr()
        assert "Trace saved" in captured.err

    @patch("subprocess.run")
    def test_upload_to_gcs_success(self, mock_run, tracer, capsys):
        """Test successful GCS upload."""
        mock_run.return_value = MagicMock()

        result = tracer.upload_to_gcs(
            "test-bucket", "/tmp/trace.json", "traces/2025/01/01/trace.json"
        )

        assert result is True
        mock_run.assert_called_once()
        captured = capsys.readouterr()
        assert "Trace uploaded" in captured.err

    @patch("subprocess.run")
    def test_upload_to_gcs_failure(self, mock_run, tracer, capsys):
        """Test failed GCS upload."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "gcloud", stderr="Upload failed"
        )

        result = tracer.upload_to_gcs(
            "test-bucket", "/tmp/trace.json", "traces/2025/01/01/trace.json"
        )

        assert result is False
        captured = capsys.readouterr()
        assert "Failed to upload trace to GCS" in captured.err

    def test_get_summary_success(self, tracer):
        """Test get_summary for successful execution."""
        tracer.trace["events"] = [
            {"type": "REASONING", "content": "..."},
            {"type": "TOOL_CALL", "content": "..."},
            {"type": "ACTION", "content": "..."},
        ]
        tracer.trace["result"]["status"] = "SUCCESS"
        tracer.trace["result"]["files_modified"] = ["test.py"]

        summary = tracer.get_summary()

        assert "Successfully fixed test failures" in summary
        assert "Modified 1 files" in summary
        assert "Executed 3 agent actions" in summary

    def test_get_summary_failed(self, tracer):
        """Test get_summary for failed execution."""
        tracer.trace["result"]["status"] = "FAILED"
        tracer.trace["result"]["files_modified"] = []

        summary = tracer.get_summary()

        assert "Could not automatically fix" in summary

    def test_get_summary_partial(self, tracer):
        """Test get_summary for partial execution."""
        tracer.trace["result"]["status"] = "PARTIAL"
        tracer.trace["result"]["files_modified"] = ["test.py"]

        summary = tracer.get_summary()

        assert "Partially fixed" in summary


class TestCreateTracerFromEnv:
    """Test suite for create_tracer_from_env factory function."""

    @patch.dict(
        os.environ,
        {
            "TARGET_REPO": "VectorInstitute/test-repo",
            "PR_NUMBER": "123",
            "PR_TITLE": "Fix tests",
            "PR_AUTHOR": "dependabot[bot]",
            "PR_URL": "https://github.com/VectorInstitute/test-repo/pull/123",
            "FAILURE_TYPE": "test",
            "FAILED_CHECK_NAMES": "pytest,unittest",
            "FAILURE_LOGS": "Test failed",
            "GITHUB_RUN_ID": "12345",
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "VectorInstitute/aieng-bot",
        },
    )
    def test_create_tracer_from_env(self):
        """Test creating tracer from environment variables."""
        tracer = create_tracer_from_env()

        assert tracer.pr_info["repo"] == "VectorInstitute/test-repo"
        assert tracer.pr_info["number"] == 123
        assert tracer.failure_info["type"] == "test"
        assert tracer.failure_info["checks"] == ["pytest", "unittest"]
        assert tracer.workflow_run_id == "12345"
        assert "actions/runs/12345" in tracer.github_run_url

    @patch.dict(os.environ, {}, clear=True)
    def test_create_tracer_from_env_defaults(self):
        """Test creating tracer with missing env vars (uses defaults)."""
        tracer = create_tracer_from_env()

        assert tracer.pr_info["repo"] == "unknown/repo"
        assert tracer.pr_info["number"] == 0


class TestRefactoredHelperMethods:
    """Test suite for refactored helper methods."""

    @pytest.fixture
    def tracer(self):
        """Create tracer for tests."""
        return AgentExecutionTracer(
            pr_info={
                "repo": "test/repo",
                "number": 1,
                "title": "Test PR",
                "author": "bot",
                "url": "https://test",
            },
            failure_info={"type": "test", "checks": []},
            workflow_run_id="12345",
            github_run_url="https://test/run/12345",
        )

    def test_determine_event_type_from_string_tool_result_success(self, tracer):
        """Test event type determination from string for successful tool result."""
        msg_str = "ToolResultBlock(tool_use_id='tool_123', is_error=False)"
        result = tracer.classifier._classify_by_string_repr(msg_str, "")
        assert result == "TOOL_RESULT"

    def test_determine_event_type_from_string_tool_result_error(self, tracer):
        """Test event type determination from string for error tool result."""
        msg_str = "ToolResultBlock(tool_use_id='tool_123', is_error=True)"
        result = tracer.classifier._classify_by_string_repr(msg_str, "")
        assert result == "ERROR"

    def test_determine_event_type_from_string_tool_use_block(self, tracer):
        """Test event type determination from string for tool use."""
        msg_str = "ToolUseBlock(name='Read', input={'file_path': 'test.py'})"
        result = tracer.classifier._classify_by_string_repr(msg_str, "")
        assert result == "TOOL_CALL"

    def test_determine_event_type_from_string_text_block(self, tracer):
        """Test event type determination from string for text block."""
        msg_str = "TextBlock(text='Analyzing the code')"
        result = tracer.classifier._classify_by_string_repr(msg_str, "")
        assert result == "REASONING"

    def test_determine_event_type_from_string_system_message(self, tracer):
        """Test event type determination from string for system message."""
        msg_str = "SystemMessage(content='System info')"
        result = tracer.classifier._classify_by_string_repr(msg_str, "")
        assert result == "INFO"

    def test_determine_event_type_from_string_result_message_success(self, tracer):
        """Test event type determination from string for successful result message."""
        msg_str = "ResultMessage(result='Success', is_error=False, subtype='success')"
        result = tracer.classifier._classify_by_string_repr(msg_str, "")
        assert result == "INFO"

    def test_determine_event_type_from_string_result_message_error(self, tracer):
        """Test event type determination from string for error result message."""
        msg_str = "ResultMessage(result='Failed', is_error=True)"
        result = tracer.classifier._classify_by_string_repr(msg_str, "")
        assert result == "ERROR"

    def test_determine_event_type_from_string_fallback_to_classification(self, tracer):
        """Test event type determination falls back to content classification."""
        msg_str = "UnknownMessage(content='Error occurred')"
        result = tracer.classifier._classify_by_string_repr(msg_str, "Error occurred")
        assert result == "ERROR"

    def test_extract_scalar_fields_from_result(self, tracer):
        """Test extraction of scalar fields from ResultMessage string."""
        msg_str = (
            "ResultMessage(subtype='success', duration_ms=1500, "
            "duration_api_ms=1200, is_error=False, num_turns=3, "
            "session_id='abc123', total_cost_usd=0.0042)"
        )
        metrics = ResultMessageParser._extract_scalar_fields(msg_str)

        assert metrics["subtype"] == "success"
        assert metrics["duration_ms"] == 1500
        assert metrics["duration_api_ms"] == 1200
        assert metrics["is_error"] is False
        assert metrics["num_turns"] == 3
        assert metrics["session_id"] == "abc123"
        assert metrics["total_cost_usd"] == 0.0042

    def test_extract_scalar_fields_handles_invalid_numbers(self, tracer):
        """Test scalar field extraction handles invalid number formats."""
        msg_str = "ResultMessage(duration_ms='invalid', total_cost_usd='bad')"
        metrics = ResultMessageParser._extract_scalar_fields(msg_str)

        assert metrics["duration_ms"] is None
        assert metrics["total_cost_usd"] is None

    def test_extract_usage_from_result_with_valid_dict(self, tracer):
        """Test usage extraction from ResultMessage with valid dict."""
        msg_str = (
            "ResultMessage(usage={'input_tokens': 1000, 'output_tokens': 500, "
            "'cache_read_input_tokens': 200, 'cache_creation_input_tokens': 100})"
        )
        usage = ResultMessageParser._extract_usage(msg_str)

        assert usage["input_tokens"] == 1000
        assert usage["output_tokens"] == 500
        assert usage["cache_read_input_tokens"] == 200
        assert usage["cache_creation_input_tokens"] == 100

    def test_extract_usage_from_result_no_usage(self, tracer):
        """Test usage extraction when usage field is missing."""
        msg_str = "ResultMessage(subtype='success', duration_ms=1500)"
        usage = ResultMessageParser._extract_usage(msg_str)

        assert usage == {}

    def test_extract_usage_from_result_malformed_dict(self, tracer):
        """Test usage extraction handles malformed dict gracefully."""
        msg_str = "ResultMessage(usage={'input_tokens': 1000, 'output_tokens': 500})"
        usage = ResultMessageParser._extract_usage(msg_str)

        # Should still extract available fields
        assert "input_tokens" in usage
        assert "output_tokens" in usage

    def test_extract_result_text_single_quotes(self, tracer):
        """Test result text extraction with single quotes."""
        msg_str = "ResultMessage(result='Successfully fixed the issue')"
        result_text = ResultMessageParser._extract_result_text(msg_str)

        assert result_text == "Successfully fixed the issue"

    def test_extract_result_text_double_quotes(self, tracer):
        """Test result text extraction with double quotes."""
        msg_str = 'ResultMessage(result="Successfully fixed the issue")'
        result_text = ResultMessageParser._extract_result_text(msg_str)

        assert result_text == "Successfully fixed the issue"

    def test_extract_result_text_with_escaped_characters(self, tracer):
        """Test result text extraction handles escaped characters."""
        msg_str = "ResultMessage(result='Line 1\\nLine 2 text')"
        result_text = ResultMessageParser._extract_result_text(msg_str)

        assert "Line 1\nLine 2" in result_text
        assert "text" in result_text

    def test_extract_result_text_empty(self, tracer):
        """Test result text extraction when result is missing."""
        msg_str = "ResultMessage(subtype='success')"
        result_text = ResultMessageParser._extract_result_text(msg_str)

        assert result_text == ""

    def test_format_result_metrics_success(self, tracer):
        """Test formatting result metrics for successful execution."""
        metrics = {
            "subtype": "success",
            "duration_ms": 1500,
            "duration_api_ms": 1200,
            "num_turns": 3,
            "total_cost_usd": 0.0042,
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 500,
                "cache_read_input_tokens": 200,
            },
        }
        result_text = "Fixed the test failures"

        formatted = ResultMessageParser._format_metrics(metrics, result_text)

        assert "✓ Agent Execution Complete" in formatted
        assert "Duration: 1.5s" in formatted
        assert "API Time: 1.2s" in formatted
        assert "Turns: 3" in formatted
        assert "Cost: $0.0042" in formatted
        assert "1,000 in" in formatted
        assert "500 out" in formatted
        assert "200 cached" in formatted
        assert "Result: Fixed the test failures" in formatted

    def test_format_result_metrics_failure(self, tracer):
        """Test formatting result metrics for failed execution."""
        metrics = {
            "subtype": "error",
            "duration_ms": 800,
            "duration_api_ms": 600,
            "num_turns": 2,
            "total_cost_usd": 0.002,
            "usage": {},
        }
        result_text = "Could not fix the issue"

        formatted = ResultMessageParser._format_metrics(metrics, result_text)

        assert "✗ Agent Execution Complete" in formatted
        assert "Duration: 0.8s" in formatted

    def test_format_result_metrics_truncates_long_result(self, tracer):
        """Test that long result text is truncated."""
        metrics = {
            "subtype": "success",
            "duration_ms": 1000,
            "duration_api_ms": 800,
            "num_turns": 1,
            "total_cost_usd": 0.001,
            "usage": {},
        }
        result_text = "x" * 600  # Long text

        formatted = ResultMessageParser._format_metrics(metrics, result_text)

        assert "..." in formatted
        assert len(formatted.split("Result: ")[1]) < 600

    def test_parse_result_message_integration(self, tracer):
        """Test _parse_result_message integrates all helper methods."""

        class MockResultMessage:
            def __str__(self):
                return (
                    "ResultMessage(subtype='success', duration_ms=1500, "
                    "duration_api_ms=1200, is_error=False, num_turns=3, "
                    "total_cost_usd=0.0042, "
                    "usage={'input_tokens': 1000, 'output_tokens': 500}, "
                    "result='Fixed all issues')"
                )

        message = MockResultMessage()
        formatted_content, metrics = ResultMessageParser.parse(message)

        assert metrics is not None
        assert metrics["subtype"] == "success"
        assert metrics["duration_ms"] == 1500
        assert metrics["usage"]["input_tokens"] == 1000
        assert "✓ Agent Execution Complete" in formatted_content
        assert "Fixed all issues" in formatted_content


class TestToolExtractionImprovements:
    """Test suite for improved tool name extraction and error handling."""

    @pytest.fixture
    def tracer(self):
        """Create tracer for tests."""
        return AgentExecutionTracer(
            pr_info={
                "repo": "test/repo",
                "number": 1,
                "title": "Test PR",
                "author": "bot",
                "url": "https://test",
            },
            failure_info={"type": "test", "checks": []},
            workflow_run_id="12345",
            github_run_url="https://test/run/12345",
        )

    @pytest.mark.asyncio
    async def test_tool_name_extraction_fallback(self, tracer):
        """Test tool name extraction falls back to string parsing."""

        class ToolUseWithoutName:
            """Mock ToolUseBlock without name attribute."""

            def __init__(self):
                self.input = {"command": "ls"}
                self.id = "tool_123"

            def __str__(self):
                return (
                    "ToolUseBlock(id='tool_123', name='Bash', input={'command': 'ls'})"
                )

            @property
            def __class__(self):
                class MockClass:
                    __name__ = "ToolUseBlock"

                return MockClass()

        msg = ToolUseWithoutName()

        async def mock_stream():
            yield msg

        captured_events = []
        async for _ in tracer.capture_agent_stream(mock_stream()):
            pass

        captured_events = tracer.trace["events"]

        # Should extract "Bash" from string representation
        assert len(captured_events) == 1
        assert captured_events[0]["tool"] == "Bash"

    @pytest.mark.asyncio
    async def test_tool_result_links_to_tool_call(self, tracer):
        """Test that ToolResultBlock events get tool name from TOOL_CALL."""
        tool_call = MockToolUseBlock("Read", {"file_path": "test.py"}, "tool_123")
        tool_result = MockToolResultBlock("tool_123", is_error=False)

        async def mock_stream():
            yield tool_call
            yield tool_result

        async for _ in tracer.capture_agent_stream(mock_stream()):
            pass

        events = tracer.trace["events"]

        assert len(events) == 2
        # First event is TOOL_CALL with tool name
        assert events[0]["type"] == "TOOL_CALL"
        assert events[0]["tool"] == "Read"
        # Second event is TOOL_RESULT with tool name linked from first event
        assert events[1]["type"] == "TOOL_RESULT"
        assert events[1]["tool"] == "Read"
        assert events[1]["tool_use_id"] == "tool_123"

    @pytest.mark.asyncio
    async def test_error_tool_result_gets_tool_name(self, tracer):
        """Test that error ToolResultBlock events get tool name."""
        tool_call = MockToolUseBlock("Bash", {"command": "invalid"}, "tool_456")
        error_result = MockToolResultBlock("tool_456", is_error=True)

        async def mock_stream():
            yield tool_call
            yield error_result

        async for _ in tracer.capture_agent_stream(mock_stream()):
            pass

        events = tracer.trace["events"]

        assert len(events) == 2
        assert events[0]["tool"] == "Bash"
        # Error result should be marked as ERROR type and have tool name
        assert events[1]["type"] == "ERROR"
        assert events[1]["tool"] == "Bash"
        assert events[1]["is_error"] is True

    @pytest.mark.asyncio
    async def test_unknown_tool_fallback(self, tracer):
        """Test that unknown tools default to 'Unknown'."""

        class UnknownTool:
            def __init__(self):
                self.input = {}
                self.id = "tool_999"
                # name attribute is None

            def __str__(self):
                return "ToolUseBlock(id='tool_999', input={})"

            @property
            def __class__(self):
                class MockClass:
                    __name__ = "ToolUseBlock"

                return MockClass()

        msg = UnknownTool()

        async def mock_stream():
            yield msg

        async for _ in tracer.capture_agent_stream(mock_stream()):
            pass

        events = tracer.trace["events"]

        # Should default to "Unknown" when name can't be extracted
        assert len(events) == 1
        assert events[0]["tool"] == "Unknown"

    @pytest.mark.asyncio
    async def test_skill_tool_capture(self, tracer):
        """Test that Skill tool calls are properly captured."""
        skill_call = MockToolUseBlock(
            "Skill", {"skill": "fix-security-audit"}, "tool_789"
        )
        skill_result = MockToolResultBlock("tool_789", is_error=False)

        async def mock_stream():
            yield skill_call
            yield skill_result

        async for _ in tracer.capture_agent_stream(mock_stream()):
            pass

        events = tracer.trace["events"]

        assert len(events) == 2
        # First event is TOOL_CALL with tool name = Skill
        assert events[0]["type"] == "TOOL_CALL"
        assert events[0]["tool"] == "Skill"
        assert events[0]["parameters"]["skill"] == "fix-security-audit"
        assert events[0]["tool_use_id"] == "tool_789"
        # Second event is TOOL_RESULT linked to the Skill call
        assert events[1]["type"] == "TOOL_RESULT"
        assert events[1]["tool"] == "Skill"
        assert events[1]["tool_use_id"] == "tool_789"

    def test_tools_allowed_includes_skill(self, tracer):
        """Test that tools_allowed list includes Skill tool."""
        tools_allowed = tracer.trace["execution"]["tools_allowed"]
        assert "Skill" in tools_allowed
        assert "Read" in tools_allowed
        assert "Edit" in tools_allowed
        assert "Bash" in tools_allowed
        assert "Glob" in tools_allowed
        assert "Grep" in tools_allowed

    def test_classify_message_skill_tool_call(self, tracer):
        """Test message classification for skill invocations."""
        assert (
            tracer.classifier.classify_by_content("Launching skill: fix-security-audit")
            == "TOOL_CALL"
        )
        assert (
            tracer.classifier.classify_by_content("Invoking skill: fix-test-failures")
            == "TOOL_CALL"
        )

    def test_extract_tool_info_skill(self, tracer):
        """Test tool info extraction for Skill tool."""
        info = tracer.tool_extractor.extract_from_content(
            "Launching skill: fix-security-audit", "TOOL_CALL"
        )
        assert info is not None
        assert info["tool"] == "Skill"
        assert "fix-security-audit" in info["parameters"]["target"]
