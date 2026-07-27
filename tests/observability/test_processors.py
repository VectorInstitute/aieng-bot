"""Tests for event processing logic."""

from types import SimpleNamespace

from aieng_bot.observability.classifiers import MessageClassifier
from aieng_bot.observability.extractors import ToolInfoExtractor
from aieng_bot.observability.processors import EventProcessor
from aieng_bot.observability.tracer import AgentExecutionTracer


def _make_processor() -> EventProcessor:
    patterns = AgentExecutionTracer.TOOL_PATTERNS
    return EventProcessor(MessageClassifier(patterns), ToolInfoExtractor(patterns))


class ToolUseBlock(SimpleNamespace):
    """Stand-in whose class name ends with ToolUseBlock."""


class ToolResultBlock(SimpleNamespace):
    """Stand-in whose class name ends with ToolResultBlock."""


class TextBlock(SimpleNamespace):
    """Stand-in whose class name ends with TextBlock."""


class TestProcessContentBlock:
    """Tests for EventProcessor.process_content_block."""

    def test_tool_use_block_event(self):
        """ToolUseBlock produces a TOOL_CALL event with tool info."""
        processor = _make_processor()
        block = ToolUseBlock(name="Bash", input={"command": "ls"}, id="tu_1")
        event = processor.process_content_block(block)

        assert event is not None
        assert event["type"] == "TOOL_CALL"
        assert event["tool"] == "Bash"
        assert event["parameters"] == {"command": "ls"}
        assert event["tool_use_id"] == "tu_1"

    def test_tool_result_block_event(self):
        """ToolResultBlock produces an event linked by tool_use_id."""
        processor = _make_processor()
        block = ToolResultBlock(content="output", tool_use_id="tu_1", is_error=False)
        event = processor.process_content_block(block)

        assert event is not None
        assert event["tool_use_id"] == "tu_1"
        assert "is_error" not in event

    def test_error_tool_result_marks_event(self):
        """An error result flips the event type to ERROR."""
        processor = _make_processor()
        block = ToolResultBlock(content="boom", tool_use_id="tu_2", is_error=True)
        event = processor.process_content_block(block)

        assert event is not None
        assert event["type"] == "ERROR"
        assert event["is_error"] is True

    def test_empty_content_returns_none(self):
        """Blocks with no displayable content are skipped."""
        processor = _make_processor()
        block = TextBlock(text="")
        assert processor.process_content_block(block) is None


class TestLinkToolResultToCall:
    """Tests for EventProcessor.link_tool_result_to_call."""

    def test_links_tool_name_from_matching_call(self):
        """A result inherits the tool name from its originating call."""
        processor = _make_processor()
        events = [
            {"type": "TOOL_CALL", "tool": "Bash", "tool_use_id": "tu_9"},
        ]
        result_event = {"type": "TOOL_RESULT", "tool_use_id": "tu_9"}
        processor.link_tool_result_to_call(result_event, events)
        assert result_event["tool"] == "Bash"

    def test_no_tool_use_id_is_noop(self):
        """Events without a tool_use_id are left untouched."""
        processor = _make_processor()
        result_event = {"type": "TOOL_RESULT"}
        processor.link_tool_result_to_call(result_event, [])
        assert "tool" not in result_event

    def test_unmatched_id_is_noop(self):
        """No matching call means no tool name is set."""
        processor = _make_processor()
        result_event = {"type": "TOOL_RESULT", "tool_use_id": "missing"}
        processor.link_tool_result_to_call(result_event, [])
        assert "tool" not in result_event
