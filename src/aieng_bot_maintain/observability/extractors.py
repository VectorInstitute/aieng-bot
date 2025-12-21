"""Content extraction utilities for agent execution traces.

This module provides utilities for extracting displayable content
from different types of agent message blocks (ToolUseBlock, ToolResultBlock,
TextBlock) and extracting tool information from message content.
"""

from __future__ import annotations

import json
import re
from typing import Any


class ContentExtractor:
    """Extract displayable content from agent message blocks."""

    @staticmethod
    def extract_from_tool_use(block: Any) -> str:
        """Extract content from ToolUseBlock.

        Parameters
        ----------
        block : Any
            ToolUseBlock instance.

        Returns
        -------
        str
            Formatted tool use description.

        """
        tool_name = getattr(block, "name", None)
        tool_input = getattr(block, "input", {})

        if not tool_name or not tool_input:
            return str(block)

        # Handle common tool input patterns
        if tool_input.get("command"):
            return f"$ {tool_input['command']}"

        if tool_input.get("file_path"):
            if tool_input.get("old_string"):
                return f"Edit file: {tool_input['file_path']}"
            return f"Read: {tool_input['file_path']}"

        return f"{tool_name}: {json.dumps(tool_input)}"

    @staticmethod
    def extract_from_tool_result(block: Any) -> str:
        """Extract content from ToolResultBlock.

        Parameters
        ----------
        block : Any
            ToolResultBlock instance.

        Returns
        -------
        str
            Tool result content.

        """
        if hasattr(block, "content"):
            result_content = block.content
            return (
                result_content
                if isinstance(result_content, str)
                else str(result_content)
            )
        return str(block)

    @staticmethod
    def extract_from_text_block(block: Any) -> str:
        """Extract content from TextBlock.

        Parameters
        ----------
        block : Any
            TextBlock instance.

        Returns
        -------
        str
            Text content.

        """
        if hasattr(block, "text"):
            return block.text

        # Fallback to parsing from string representation
        text_match = re.search(r'text=["\'](.+)["\']', str(block), re.DOTALL)
        if text_match:
            return text_match.group(1).replace("\\n", "\n").replace("\\'", "'")
        return str(block)

    @staticmethod
    def extract_display_content(block: Any, block_class: str) -> str:
        """Extract displayable content from a block based on its type.

        Parameters
        ----------
        block : Any
            Content block.
        block_class : str
            Class name of the block.

        Returns
        -------
        str
            Human-readable display content.

        """
        if block_class.endswith("ToolUseBlock"):
            return ContentExtractor.extract_from_tool_use(block)

        if block_class.endswith("ToolResultBlock"):
            return ContentExtractor.extract_from_tool_result(block)

        if block_class.endswith("TextBlock"):
            return ContentExtractor.extract_from_text_block(block)

        return str(block)

    @staticmethod
    def extract_message_content(message: Any) -> str:
        """Extract content string from message object.

        Parameters
        ----------
        message : Any
            Agent SDK message object.

        Returns
        -------
        str
            Extracted content string.

        """
        if not hasattr(message, "content"):
            return ""

        if isinstance(message.content, str):
            return message.content

        if isinstance(message.content, list):
            # Handle content blocks
            return " ".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in message.content
            )

        return str(message.content)


class ToolInfoExtractor:
    """Extract tool information from messages."""

    def __init__(self, tool_patterns: dict[str, str]) -> None:
        """Initialize extractor with tool patterns.

        Parameters
        ----------
        tool_patterns : dict[str, str]
            Dictionary mapping tool names to regex patterns.

        """
        self.tool_patterns = tool_patterns

    def extract_from_content(
        self, content: str, event_type: str
    ) -> dict[str, Any] | None:
        """Extract tool name and parameters from message content.

        Parameters
        ----------
        content : str
            Message content to parse.
        event_type : str
            Event type (must be "TOOL_CALL" for extraction).

        Returns
        -------
        dict[str, Any] or None
            Dict with tool, parameters, and result_summary fields,
            or None if not a tool call.

        """
        if event_type != "TOOL_CALL":
            return None

        for tool_name, pattern in self.tool_patterns.items():
            if tool_name.lower() in content.lower():
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    param_value = match.group(1).strip()
                    return {
                        "tool": tool_name,
                        "parameters": {"target": param_value},
                        "result_summary": None,
                    }

        return None

    def extract_from_tool_use_block(self, block: Any) -> dict[str, Any]:
        """Extract tool information from ToolUseBlock.

        Parameters
        ----------
        block : Any
            ToolUseBlock message.

        Returns
        -------
        dict[str, Any]
            Dictionary with tool, parameters, and tool_use_id.

        """
        tool_name = getattr(block, "name", None)
        tool_input = getattr(block, "input", {})
        tool_id = getattr(block, "id", None)

        # Fallback to string parsing if attributes are not available
        if not tool_name:
            tool_name = self._extract_tool_name_from_string(block)

        if not tool_input or (isinstance(tool_input, dict) and not tool_input):
            tool_input = self._extract_tool_input_from_string(block)

        if not tool_id:
            tool_id = self._extract_tool_id_from_string(block)

        return {
            "tool": tool_name if tool_name else "Unknown",
            "parameters": tool_input if tool_input else {},
            "tool_use_id": tool_id,
        }

    @staticmethod
    def _extract_tool_name_from_string(block: Any) -> str | None:
        """Extract tool name from string representation.

        Parameters
        ----------
        block : Any
            Message block.

        Returns
        -------
        str or None
            Extracted tool name.

        """
        msg_str = str(block)
        # Try multiple regex patterns to extract tool name
        name_match = re.search(r"name=['\"](\w+)['\"]", msg_str)
        if not name_match:
            # Try without quotes (e.g., name=Bash)
            name_match = re.search(r"name=(\w+)", msg_str)
        return name_match.group(1) if name_match else None

    @staticmethod
    def _extract_tool_input_from_string(block: Any) -> dict[str, Any]:
        """Extract tool input from string representation.

        Parameters
        ----------
        block : Any
            Message block.

        Returns
        -------
        dict[str, Any]
            Extracted tool input dictionary.

        """
        msg_str = str(block)
        input_match = re.search(r"input=(\{[^}]+\})", msg_str)
        if input_match:
            try:
                # Convert Python dict string to JSON-like format
                input_str = input_match.group(1).replace("'", '"')
                return json.loads(input_str)
            except (json.JSONDecodeError, ValueError):
                # If parsing fails, store as string
                return {"raw": input_match.group(1)}
        return {}

    @staticmethod
    def _extract_tool_id_from_string(block: Any) -> str | None:
        """Extract tool_use_id from string representation.

        Parameters
        ----------
        block : Any
            Message block.

        Returns
        -------
        str or None
            Extracted tool_use_id.

        """
        msg_str = str(block)
        id_match = re.search(r"id=['\"]([^'\"]+)['\"]", msg_str)
        return id_match.group(1) if id_match else None

    @staticmethod
    def extract_tool_use_id(block: Any) -> str | None:
        """Extract tool_use_id from ToolResultBlock.

        Parameters
        ----------
        block : Any
            ToolResultBlock message.

        Returns
        -------
        str or None
            Extracted tool_use_id.

        """
        return getattr(block, "tool_use_id", None)

    @staticmethod
    def is_error_result(block: Any) -> bool:
        """Check if ToolResultBlock represents an error.

        Parameters
        ----------
        block : Any
            ToolResultBlock message.

        Returns
        -------
        bool
            True if the result is an error.

        """
        is_error = getattr(block, "is_error", None)
        return is_error is True or (is_error is None and "is_error=True" in str(block))
