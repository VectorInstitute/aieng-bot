"""Event processing logic for agent execution traces.

This module provides utilities for processing agent message blocks
into structured events, linking tool results to tool calls, and
managing event sequences.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .classifiers import MessageClassifier
from .extractors import ContentExtractor, ToolInfoExtractor


class EventProcessor:
    """Process agent messages into structured trace events."""

    def __init__(
        self,
        classifier: MessageClassifier,
        tool_extractor: ToolInfoExtractor,
    ) -> None:
        """Initialize event processor.

        Parameters
        ----------
        classifier : MessageClassifier
            Message classifier instance.
        tool_extractor : ToolInfoExtractor
            Tool information extractor instance.

        """
        self.classifier = classifier
        self.tool_extractor = tool_extractor

    def process_content_block(self, block: Any) -> dict[str, Any] | None:
        """Process a single content block from a message.

        Parameters
        ----------
        block : Any
            Content block (TextBlock, ToolUseBlock, or ToolResultBlock).

        Returns
        -------
        dict[str, Any] or None
            Event dictionary or None if block should be skipped.

        """
        block_class = block.__class__.__name__

        # Extract displayable content based on block type
        display_content = ContentExtractor.extract_display_content(block, block_class)

        if not display_content:
            return None

        # Determine event type
        event_type = self.classifier.classify_by_class(
            block, block_class, display_content
        )

        event: dict[str, Any] = {
            "seq": 0,  # Will be set by caller
            "timestamp": datetime.now(UTC).isoformat(),
            "type": event_type,
            "content": display_content,
        }

        # Extract tool info based on block class
        if block_class.endswith("ToolUseBlock") or event_type == "TOOL_CALL":
            self._process_tool_use(block, event)
        elif (
            block_class.endswith("ToolResultBlock")
            or event_type == "TOOL_RESULT"
            or (event_type == "ERROR" and "ToolResultBlock" in str(block))
        ):
            self._process_tool_result(block, event)

        return event

    def _process_tool_use(self, block: Any, event: dict[str, Any]) -> None:
        """Process ToolUseBlock and populate event with tool information.

        Parameters
        ----------
        block : Any
            ToolUseBlock message.
        event : dict[str, Any]
            Event dictionary to populate.

        """
        tool_info = self.tool_extractor.extract_from_tool_use_block(block)
        event["tool"] = tool_info["tool"]
        event["parameters"] = tool_info["parameters"]
        if tool_info["tool_use_id"]:
            event["tool_use_id"] = tool_info["tool_use_id"]

    def _process_tool_result(self, block: Any, event: dict[str, Any]) -> None:
        """Process ToolResultBlock and link to original tool call.

        Parameters
        ----------
        block : Any
            ToolResultBlock message.
        event : dict[str, Any]
            Event dictionary to populate.

        """
        tool_use_id = ToolInfoExtractor.extract_tool_use_id(block)
        if tool_use_id:
            event["tool_use_id"] = tool_use_id

        # Check if this is an error result
        if ToolInfoExtractor.is_error_result(block):
            event["is_error"] = True
            event["type"] = "ERROR"

    def link_tool_result_to_call(
        self, event: dict[str, Any], events: list[dict[str, Any]]
    ) -> None:
        """Link tool result event to its original tool call.

        Parameters
        ----------
        event : dict[str, Any]
            Tool result event to link.
        events : list[dict[str, Any]]
            List of all events processed so far.

        """
        tool_use_id = event.get("tool_use_id")
        if not tool_use_id:
            return

        # Find the original tool call to set tool name on result
        for prev_event in reversed(events):
            if (
                prev_event.get("tool_use_id") == tool_use_id
                and prev_event.get("type") == "TOOL_CALL"
            ):
                event["tool"] = prev_event.get("tool", "Unknown")
                break


class EventLogger:
    """Log events to console for workflow visibility."""

    @staticmethod
    def log_event(event: dict[str, Any], max_length: int = 200) -> None:
        """Log event to console with truncation.

        Parameters
        ----------
        event : dict[str, Any]
            Event to log.
        max_length : int, optional
            Maximum length of content to display (default=200).

        """
        log_content = event["content"]
        truncated = (
            log_content[:max_length] + "..."
            if len(log_content) > max_length
            else log_content
        )
        print(f"[Agent][{event['type']}] {truncated}")


class SummaryGenerator:
    """Generate human-readable summaries from trace data."""

    @staticmethod
    def generate(trace: dict[str, Any], failure_type: str) -> str:
        """Generate human-readable summary of execution.

        Parameters
        ----------
        trace : dict[str, Any]
            Complete trace data structure.
        failure_type : str
            Type of failure being fixed.

        Returns
        -------
        str
            Summary string for PR comments with execution statistics.

        """
        event_counts: dict[str, int] = {}
        for event in trace["events"]:
            event_type = event["type"]
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        summary_parts = []

        # Status line
        status = trace["result"]["status"]
        if status == "SUCCESS":
            summary_parts.append(f"✓ Successfully fixed {failure_type} failures")
        elif status == "FAILED":
            summary_parts.append(
                f"✗ Could not automatically fix {failure_type} failures"
            )
        else:
            summary_parts.append(f"⚠ Partially fixed {failure_type} failures")

        # File modifications
        files_modified = trace["result"]["files_modified"]
        summary_parts.append(f"Modified {len(files_modified)} files")

        # Total actions
        total_actions = sum(event_counts.values())
        summary_parts.append(f"Executed {total_actions} agent actions")

        # Action breakdown
        if event_counts:
            breakdown = ", ".join(
                f"{count} {event_type.lower()}"
                for event_type, count in event_counts.items()
            )
            summary_parts.append(f"({breakdown})")

        return " - ".join(summary_parts)
