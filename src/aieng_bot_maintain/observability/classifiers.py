"""Message classification logic for agent execution traces.

This module provides utilities for classifying agent messages into
event types (REASONING, TOOL_CALL, ACTION, ERROR, INFO) based on
content patterns and message class types.
"""

from __future__ import annotations

from typing import Any


class MessageClassifier:
    """Classify agent messages into event types.

    This class provides methods to determine the type of an agent message
    based on its content, class name, and string representation.
    """

    # Keyword mappings for content-based classification
    ERROR_KEYWORDS = [
        "error",
        "failed",
        "exception",
        "cannot",
        "unable to",
        "failed to",
    ]

    TOOL_KEYWORDS = [
        "reading",
        "read",
        "editing",
        "edit",
        "running",
        "execute",
        "searching",
        "search",
        "grepping",
        "grep",
        "finding",
        "glob",
        "launching skill",
        "invoking skill",
    ]

    REASONING_KEYWORDS = [
        "analyzing",
        "checking",
        "examining",
        "investigating",
        "looking at",
        "reviewing",
        "understanding",
        "considering",
    ]

    FINDING_KEYWORDS = [
        "found",
        "detected",
        "identified",
        "discovered",
        "located",
        "see that",
        "notice",
    ]

    ACTION_KEYWORDS = [
        "applying",
        "fixing",
        "updating",
        "modifying",
        "changing",
        "adding",
        "removing",
        "committing",
    ]

    def __init__(self, tool_patterns: dict[str, str]) -> None:
        """Initialize classifier with tool patterns.

        Parameters
        ----------
        tool_patterns : dict[str, str]
            Dictionary mapping tool names to regex patterns.

        """
        self.tool_patterns = tool_patterns

    def classify_by_content(self, content: str) -> str:
        """Classify message type based on content patterns.

        Parameters
        ----------
        content : str
            Message content to classify.

        Returns
        -------
        str
            One of: "REASONING", "TOOL_CALL", "ACTION", "ERROR", "INFO".

        """
        content_lower = content.lower()

        # Error detection (highest priority)
        if any(keyword in content_lower for keyword in self.ERROR_KEYWORDS):
            return "ERROR"

        # Tool call detection
        if self._is_tool_call_content(content_lower):
            return "TOOL_CALL"

        # Reasoning/analysis detection
        if any(keyword in content_lower for keyword in self.REASONING_KEYWORDS):
            return "REASONING"

        # Finding/result detection
        if any(keyword in content_lower for keyword in self.FINDING_KEYWORDS):
            return "REASONING"

        # Action detection
        if any(keyword in content_lower for keyword in self.ACTION_KEYWORDS):
            return "ACTION"

        # Default to INFO
        return "INFO"

    def _is_tool_call_content(self, content_lower: str) -> bool:
        """Check if content indicates a tool call.

        Parameters
        ----------
        content_lower : str
            Lowercased content string.

        Returns
        -------
        bool
            True if content appears to be a tool call.

        """
        has_tool_keyword = any(
            keyword in content_lower for keyword in self.TOOL_KEYWORDS
        )
        has_tool_name = any(
            tool.lower() in content_lower for tool in self.tool_patterns
        )
        return has_tool_keyword and has_tool_name

    def classify_by_class(self, message: Any, msg_class: str, content: str) -> str:
        """Determine event type based on message class and content.

        Parameters
        ----------
        message : Any
            Agent SDK message object.
        msg_class : str
            Class name of message.
        content : str
            Extracted content string.

        Returns
        -------
        str
            Event type (ERROR, TOOL_RESULT, TOOL_CALL, etc.).

        """
        # Handle both short class names and namespaced class names
        if msg_class.endswith("ToolResultBlock"):
            return self._classify_tool_result(message)

        if msg_class.endswith("ToolUseBlock"):
            return "TOOL_CALL"

        if msg_class.endswith("TextBlock"):
            # TextBlock is always reasoning/explanation from the assistant
            return "REASONING"

        # Check string representation for SDK message types
        msg_str = str(message)
        return self._classify_by_string_repr(msg_str, content)

    def _classify_tool_result(self, message: Any) -> str:
        """Classify a ToolResultBlock message.

        Parameters
        ----------
        message : Any
            ToolResultBlock message.

        Returns
        -------
        str
            "ERROR" if is_error=True, otherwise "TOOL_RESULT".

        """
        msg_str = str(message)
        return "ERROR" if "is_error=True" in msg_str else "TOOL_RESULT"

    def _classify_by_string_repr(self, msg_str: str, content: str) -> str:
        """Determine event type from message string representation.

        Parameters
        ----------
        msg_str : str
            String representation of message.
        content : str
            Extracted content string for fallback classification.

        Returns
        -------
        str
            Event type (ERROR, TOOL_RESULT, TOOL_CALL, etc.).

        """
        # Map message type prefixes to event types
        type_mapping = {
            "ToolUseBlock(": "TOOL_CALL",
            "TextBlock(": "REASONING",
            "SystemMessage(": "INFO",
        }

        for prefix, event_type in type_mapping.items():
            if msg_str.startswith(prefix):
                return event_type

        # Special handling for ToolResultBlock and ResultMessage
        if msg_str.startswith("ToolResultBlock("):
            return "ERROR" if "is_error=True" in msg_str else "TOOL_RESULT"

        if msg_str.startswith("ResultMessage("):
            return "ERROR" if "is_error=True" in msg_str else "INFO"

        # Fallback: avoid false positives from "is_error=False"
        if "is_error=False" in msg_str or "subtype='success'" in msg_str:
            return "INFO"

        return self.classify_by_content(content if content else msg_str)
