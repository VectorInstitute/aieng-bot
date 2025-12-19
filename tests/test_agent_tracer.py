"""Tests for agent execution tracer module."""

import os
import subprocess
from typing import Any
from unittest.mock import MagicMock, mock_open, patch

import pytest

from aieng_bot_maintain.observability import (
    AgentExecutionTracer,
    create_tracer_from_env,
)


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
        "logs_truncated": "Test failed on line 42",
    }
    return AgentExecutionTracer(
        pr_info=pr_info,
        failure_info=failure_info,
        workflow_run_id="12345",
        github_run_url="https://github.com/VectorInstitute/aieng-bot-maintain/actions/runs/12345",
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
        assert tracer.classify_message("Error: test failed") == "ERROR"
        assert tracer.classify_message("Failed to process") == "ERROR"
        assert tracer.classify_message("Exception occurred") == "ERROR"

    def test_classify_message_tool_call(self, tracer):
        """Test message classification for tool calls."""
        assert tracer.classify_message("Reading file test.py") == "TOOL_CALL"
        assert tracer.classify_message("Editing src/main.py") == "TOOL_CALL"
        assert tracer.classify_message("Running bash command") == "TOOL_CALL"

    def test_classify_message_reasoning(self, tracer):
        """Test message classification for reasoning."""
        assert tracer.classify_message("Analyzing the test failure") == "REASONING"
        assert tracer.classify_message("Checking the configuration") == "REASONING"
        assert tracer.classify_message("Found an issue in the code") == "REASONING"

    def test_classify_message_action(self, tracer):
        """Test message classification for actions."""
        assert tracer.classify_message("Applying the fix") == "ACTION"
        assert tracer.classify_message("Fixing the test") == "ACTION"
        assert tracer.classify_message("Updating the code") == "ACTION"

    def test_classify_message_info(self, tracer):
        """Test message classification for info."""
        assert tracer.classify_message("Processing complete") == "INFO"

    def test_extract_tool_info_read(self, tracer):
        """Test tool info extraction for Read tool."""
        info = tracer.extract_tool_info("Reading file src/test.py", "TOOL_CALL")
        assert info is not None
        assert info["tool"] == "Read"
        # Basic extraction works (exact format depends on regex)
        assert info["parameters"]["target"] is not None

    def test_extract_tool_info_not_tool_call(self, tracer):
        """Test tool info extraction for non-tool-call."""
        info = tracer.extract_tool_info("Some message", "INFO")
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
        assert "Trace saved" in captured.out

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
        assert "Trace uploaded" in captured.out

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
        assert "Failed to upload trace to GCS" in captured.out

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
            "GITHUB_REPOSITORY": "VectorInstitute/aieng-bot-maintain",
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
            failure_info={"type": "test", "checks": [], "logs_truncated": ""},
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
