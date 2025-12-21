"""Agent execution tracer for Claude Agent SDK.

This module provides comprehensive observability for Claude Agent SDK executions.
It captures tool calls, reasoning, actions, and errors in a structured format
similar to LangSmith/Langfuse for later analysis and dashboard display.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any


class AgentExecutionTracer:
    """Capture and structure agent execution traces from Claude Agent SDK.

    Features:
    - Full message content capture (no truncation)
    - Event classification (REASONING, TOOL_CALL, ACTION, ERROR)
    - Tool invocation parsing from message content
    - Structured JSON output with comprehensive schema
    - GCS upload support

    Parameters
    ----------
    pr_info : dict[str, Any]
        PR context dict with keys: repo, number, title, author, url.
    failure_info : dict[str, Any]
        Failure context dict with keys: type, checks, logs_truncated.
    workflow_run_id : str
        GitHub Actions run ID.
    github_run_url : str
        URL to GitHub Actions run.

    Attributes
    ----------
    pr_info : dict[str, Any]
        PR context information.
    failure_info : dict[str, Any]
        Failure context information.
    workflow_run_id : str
        GitHub Actions run ID.
    github_run_url : str
        URL to GitHub Actions run.
    trace : dict[str, Any]
        Complete trace data structure.
    event_sequence : int
        Sequential counter for events.
    start_time : datetime
        Trace start timestamp.
    tool_patterns : dict[str, str]
        Regex patterns for tool call extraction.

    """

    def __init__(
        self,
        pr_info: dict[str, Any],
        failure_info: dict[str, Any],
        workflow_run_id: str,
        github_run_url: str,
    ):
        """Initialize tracer with PR and workflow context.

        Parameters
        ----------
        pr_info : dict[str, Any]
            PR context dict with keys: repo, number, title, author, url.
        failure_info : dict[str, Any]
            Failure context dict with keys: type, checks, logs_truncated.
        workflow_run_id : str
            GitHub Actions run ID.
        github_run_url : str
            URL to GitHub Actions run.

        """
        self.pr_info = pr_info
        self.failure_info = failure_info
        self.workflow_run_id = workflow_run_id
        self.github_run_url = github_run_url

        self.trace: dict[str, Any] = {
            "metadata": {
                "workflow_run_id": workflow_run_id,
                "github_run_url": github_run_url,
                "timestamp": datetime.now(UTC).isoformat(),
                "pr": pr_info,
                "failure": failure_info,
            },
            "execution": {
                "start_time": datetime.now(UTC).isoformat(),
                "end_time": None,
                "duration_seconds": None,
                "model": "claude-sonnet-4.5",
                "tools_allowed": ["Read", "Edit", "Bash", "Glob", "Grep", "Skill"],
                "metrics": None,  # Will be populated from ResultMessage
            },
            "events": [],
            "result": {
                "status": "IN_PROGRESS",
                "changes_made": 0,
                "files_modified": [],
                "commit_sha": None,
                "commit_url": None,
            },
        }

        self.event_sequence = 0
        self.start_time = datetime.now(UTC)

        # Tool call patterns for parsing
        self.tool_patterns = {
            "Read": r"(?:Reading|Read)\s+(?:file\s+)?[`'\"]?(.+?)[`'\"]?",
            "Edit": r"(?:Editing|Edit)\s+[`'\"]?(.+?)[`'\"]?",
            "Bash": r"(?:Running|Execute|Executing)\s+[`'\"]?(.+?)[`'\"]?",
            "Glob": r"(?:Searching|Search|Finding|Glob)\s+(?:for\s+)?[`'\"]?(.+?)[`'\"]?",
            "Grep": r"(?:Grepping|Grep|Searching)\s+(?:for\s+)?[`'\"]?(.+?)[`'\"]?",
            "Skill": r"(?:Launching\s+skill|Skill):\s+([a-zA-Z0-9_-]+)",
        }

    def classify_message(self, content: str) -> str:
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

        # Error detection
        if any(
            keyword in content_lower
            for keyword in [
                "error",
                "failed",
                "exception",
                "cannot",
                "unable to",
                "failed to",
            ]
        ):
            return "ERROR"

        # Tool call detection
        tool_keywords = [
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
        if any(keyword in content_lower for keyword in tool_keywords) and any(
            tool.lower() in content_lower for tool in self.tool_patterns
        ):
            return "TOOL_CALL"

        # Reasoning/analysis detection
        reasoning_keywords = [
            "analyzing",
            "checking",
            "examining",
            "investigating",
            "looking at",
            "reviewing",
            "understanding",
            "considering",
        ]
        if any(keyword in content_lower for keyword in reasoning_keywords):
            return "REASONING"

        # Finding/result detection
        finding_keywords = [
            "found",
            "detected",
            "identified",
            "discovered",
            "located",
            "see that",
            "notice",
        ]
        if any(keyword in content_lower for keyword in finding_keywords):
            return "REASONING"

        # Action detection
        action_keywords = [
            "applying",
            "fixing",
            "updating",
            "modifying",
            "changing",
            "adding",
            "removing",
            "committing",
        ]
        if any(keyword in content_lower for keyword in action_keywords):
            return "ACTION"

        # Default to INFO
        return "INFO"

    def extract_tool_info(self, content: str, event_type: str) -> dict[str, Any] | None:
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
                        "result_summary": None,  # Will be filled by next message
                    }

        return None

    def _extract_tool_use_content(self, block: Any) -> str:
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

        if tool_input.get("command"):
            return f"$ {tool_input['command']}"

        if tool_input.get("file_path"):
            if tool_input.get("old_string"):
                return f"Edit file: {tool_input['file_path']}"
            return f"Read: {tool_input['file_path']}"

        return f"{tool_name}: {json.dumps(tool_input)}"

    def _extract_tool_result_content(self, block: Any) -> str:
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

    def _extract_text_block_content(self, block: Any) -> str:
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

        # Fallback to parsing from string
        text_match = re.search(r'text=["\'](.+)["\']', str(block), re.DOTALL)
        if text_match:
            return text_match.group(1).replace("\\n", "\n").replace("\\'", "'")
        return str(block)

    def _extract_display_content(self, block: Any, block_class: str) -> str:
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
            return self._extract_tool_use_content(block)

        if block_class.endswith("ToolResultBlock"):
            return self._extract_tool_result_content(block)

        if block_class.endswith("TextBlock"):
            return self._extract_text_block_content(block)

        return str(block)

    def _extract_message_content(self, message: Any) -> str:
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

    def _determine_event_type_from_string(self, msg_str: str, content: str) -> str:
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

        # Special handling for ToolResultBlock and ResultMessage (can be ERROR or success)
        if msg_str.startswith("ToolResultBlock("):
            return "ERROR" if "is_error=True" in msg_str else "TOOL_RESULT"

        if msg_str.startswith("ResultMessage("):
            return "ERROR" if "is_error=True" in msg_str else "INFO"

        # Fallback: avoid false positives from "is_error=False"
        if "is_error=False" in msg_str or "subtype='success'" in msg_str:
            return "INFO"

        return self.classify_message(content if content else msg_str)

    def _determine_event_type(self, message: Any, msg_class: str, content: str) -> str:
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
        # (e.g., "ToolUseBlock" or "claude_agent_sdk.ToolUseBlock")
        if msg_class.endswith("ToolResultBlock"):
            # For ToolResultBlock, always parse from string representation
            # since is_error attribute access is unreliable
            msg_str = str(message)
            return "ERROR" if "is_error=True" in msg_str else "TOOL_RESULT"

        if msg_class.endswith("ToolUseBlock"):
            return "TOOL_CALL"

        if msg_class.endswith("TextBlock"):
            # TextBlock is always reasoning/explanation from the assistant
            return "REASONING"

        # Check string representation for SDK message types
        msg_str = str(message)
        return self._determine_event_type_from_string(msg_str, content)

    def _process_tool_use_block(self, message: Any, event: dict[str, Any]) -> None:
        """Process ToolUseBlock message and extract tool information.

        Parameters
        ----------
        message : Any
            ToolUseBlock message.
        event : dict[str, Any]
            Event dictionary to populate.

        """
        tool_name = getattr(message, "name", None)
        tool_input = getattr(message, "input", {})
        tool_id = getattr(message, "id", None)

        # If tool_name is None, try extracting from string representation
        if not tool_name:
            msg_str = str(message)
            # Try multiple regex patterns to extract tool name
            name_match = re.search(r"name=['\"](\w+)['\"]", msg_str)
            if not name_match:
                # Try without quotes (e.g., name=Bash)
                name_match = re.search(r"name=(\w+)", msg_str)
            if name_match:
                tool_name = name_match.group(1)

        # Extract tool_input from string representation if empty
        if not tool_input or (isinstance(tool_input, dict) and not tool_input):
            msg_str = str(message)
            # Try to extract input dict from string representation
            input_match = re.search(r"input=(\{[^}]+\})", msg_str)
            if input_match:
                try:
                    # Convert Python dict string to JSON-like format
                    input_str = input_match.group(1)
                    input_str = input_str.replace("'", '"')
                    tool_input = json.loads(input_str)
                except (json.JSONDecodeError, ValueError):
                    # If parsing fails, store as string
                    tool_input = {"raw": input_match.group(1)}

        # Extract tool_id from string representation if None
        if not tool_id:
            msg_str = str(message)
            id_match = re.search(r"id=['\"]([^'\"]+)['\"]", msg_str)
            if id_match:
                tool_id = id_match.group(1)

        # Always set tool name (default to "Unknown" if all else fails)
        event["tool"] = tool_name if tool_name else "Unknown"
        event["parameters"] = tool_input if tool_input else {}
        if tool_id:
            event["tool_use_id"] = tool_id

    def _process_tool_result_block(self, message: Any, event: dict[str, Any]) -> None:
        """Process ToolResultBlock message and link to original tool call.

        Parameters
        ----------
        message : Any
            ToolResultBlock message.
        event : dict[str, Any]
            Event dictionary to populate.

        """
        tool_use_id = getattr(message, "tool_use_id", None)
        if tool_use_id:
            event["tool_use_id"] = tool_use_id

        # Find the original tool call to set tool name on result
        if tool_use_id:
            for prev_event in reversed(self.trace["events"]):
                if (
                    prev_event.get("tool_use_id") == tool_use_id
                    and prev_event.get("type") == "TOOL_CALL"
                ):
                    event["tool"] = prev_event.get("tool", "Unknown")
                    break

        # Check if this is an error result
        is_error = getattr(message, "is_error", None)
        if is_error is True or (is_error is None and "is_error=True" in str(message)):
            event["is_error"] = True
            # Override type to ERROR for better visibility
            event["type"] = "ERROR"

    def _process_content_block(self, block: Any) -> dict[str, Any] | None:
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
        display_content = self._extract_display_content(block, block_class)

        # Determine event type
        event_type = self._determine_event_type(block, block_class, display_content)

        if not display_content:
            return None

        event: dict[str, Any] = {
            "seq": 0,  # Will be set by caller
            "timestamp": datetime.now(UTC).isoformat(),
            "type": event_type,
            "content": display_content,
        }

        # Extract tool info based on block class
        if block_class.endswith("ToolUseBlock") or event_type == "TOOL_CALL":
            self._process_tool_use_block(block, event)
        elif (
            block_class.endswith("ToolResultBlock")
            or event_type == "TOOL_RESULT"
            or (event_type == "ERROR" and "ToolResultBlock" in str(block))
        ):
            self._process_tool_result_block(block, event)

        return event

    def _extract_scalar_fields_from_result(self, msg_str: str) -> dict[str, Any]:
        """Extract scalar fields from ResultMessage string.

        Parameters
        ----------
        msg_str : str
            String representation of ResultMessage.

        Returns
        -------
        dict[str, Any]
            Dictionary of extracted scalar fields.

        """
        metrics: dict[str, Any] = {}
        for field in [
            "subtype",
            "duration_ms",
            "duration_api_ms",
            "is_error",
            "num_turns",
            "session_id",
            "total_cost_usd",
        ]:
            pattern = rf"{field}=([^,\)]+)"
            match = re.search(pattern, msg_str)
            if match:
                value_str = match.group(1).strip("'\"")
                # Convert to appropriate type
                if field in ["duration_ms", "duration_api_ms", "num_turns"]:
                    metrics[field] = int(value_str) if value_str.isdigit() else None
                elif field == "total_cost_usd":
                    try:
                        metrics[field] = float(value_str)
                    except ValueError:
                        metrics[field] = None
                elif field == "is_error":
                    metrics[field] = value_str == "True"
                else:
                    metrics[field] = value_str
        return metrics

    def _extract_usage_from_result(self, msg_str: str) -> dict[str, Any]:
        """Extract usage dict (tokens) from ResultMessage string.

        Parameters
        ----------
        msg_str : str
            String representation of ResultMessage.

        Returns
        -------
        dict[str, Any]
            Dictionary containing token usage metrics.

        """
        usage_start = msg_str.find("usage={")
        if usage_start == -1:
            return {}

        # Extract content with balanced braces
        brace_count = 0
        start_pos = usage_start + 6  # Skip "usage="
        usage_str = None
        for i in range(start_pos, len(msg_str)):
            if msg_str[i] == "{":
                brace_count += 1
            elif msg_str[i] == "}":
                brace_count -= 1
                if brace_count == 0:
                    usage_str = msg_str[start_pos : i + 1]
                    break

        if not usage_str:
            return {}

        try:
            # Use ast.literal_eval for safe Python dict evaluation
            return ast.literal_eval(usage_str)
        except (ValueError, SyntaxError):
            # Fallback: try to extract just the key metrics manually
            usage = {}
            for token_field in [
                "input_tokens",
                "output_tokens",
                "cache_read_input_tokens",
                "cache_creation_input_tokens",
            ]:
                token_match = re.search(rf"'{token_field}':\s*(\d+)", usage_str)
                if token_match:
                    usage[token_field] = int(token_match.group(1))
            return usage

    def _extract_result_text(self, msg_str: str) -> str:
        """Extract result text from ResultMessage string.

        Parameters
        ----------
        msg_str : str
            String representation of ResultMessage.

        Returns
        -------
        str
            Extracted and unescaped result text.

        """
        result_match = re.search(r"result='([^']*(?:''[^']*)*)'", msg_str, re.DOTALL)
        if not result_match:
            result_match = re.search(
                r'result="([^"]*(?:""[^"]*)*)"', msg_str, re.DOTALL
            )

        if not result_match:
            return ""

        result_text = result_match.group(1)
        # Unescape escaped quotes and newlines
        result_text = result_text.replace("\\'", "'").replace('\\"', '"')
        return result_text.replace("\\n", "\n")

    def _format_result_metrics(self, metrics: dict[str, Any], result_text: str) -> str:
        """Format result metrics into human-readable content.

        Parameters
        ----------
        metrics : dict[str, Any]
            Extracted metrics dictionary.
        result_text : str
            Result text to append.

        Returns
        -------
        str
            Formatted content string.

        """
        status_emoji = "✓" if metrics.get("subtype") == "success" else "✗"
        formatted_parts = [
            f"{status_emoji} Agent Execution Complete",
            f"Duration: {metrics.get('duration_ms', 0) / 1000:.1f}s",
            f"API Time: {metrics.get('duration_api_ms', 0) / 1000:.1f}s",
            f"Turns: {metrics.get('num_turns', 0)}",
            f"Cost: ${metrics.get('total_cost_usd', 0):.4f}",
        ]

        # Add token usage summary if available
        usage = metrics.get("usage", {})
        if usage:
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cache_read = usage.get("cache_read_input_tokens", 0)
            formatted_parts.append(
                f"Tokens: {input_tokens:,} in / {output_tokens:,} out / {cache_read:,} cached"
            )

        formatted_content = "\n".join(formatted_parts)

        # Add result summary if available and not too long
        if result_text:
            truncated_text = (
                f"{result_text[:500]}..." if len(result_text) > 500 else result_text
            )
            formatted_content += f"\n\nResult: {truncated_text}"

        return formatted_content

    def _parse_result_message(self, message: Any) -> tuple[str, dict[str, Any] | None]:
        """Parse ResultMessage and extract execution metrics.

        Parameters
        ----------
        message : Any
            ResultMessage from Agent SDK.

        Returns
        -------
        tuple[str, dict[str, Any] | None]
            Tuple of (formatted_content, metrics_dict).
            formatted_content is human-readable summary.
            metrics_dict contains extracted performance metrics.

        """
        msg_str = str(message)

        # Extract structured fields from ResultMessage string representation
        metrics = self._extract_scalar_fields_from_result(msg_str)
        metrics["usage"] = self._extract_usage_from_result(msg_str)
        result_text = self._extract_result_text(msg_str)

        # Create formatted content for display
        formatted_content = self._format_result_metrics(metrics, result_text)

        return formatted_content, metrics if metrics else None

    async def capture_agent_stream(
        self, agent_stream: AsyncIterator[Any]
    ) -> AsyncIterator[Any]:
        """Wrap agent stream to capture messages while passing them through.

        Parameters
        ----------
        agent_stream : AsyncIterator[Any]
            Async iterator from Claude Agent SDK query().

        Yields
        ------
        Any
            Original messages from agent stream.

        """
        async for message in agent_stream:
            msg_class = message.__class__.__name__

            # Check if message has content blocks (AssistantMessage, UserMessage)
            if hasattr(message, "content") and isinstance(message.content, list):
                # Process each block in the content list
                for block in message.content:
                    event = self._process_content_block(block)
                    if event:
                        self.event_sequence += 1
                        event["seq"] = self.event_sequence
                        self.trace["events"].append(event)

                        # Print for workflow logs - only show first 200 chars
                        log_content = event["content"]
                        truncated = (
                            log_content[:200] + "..."
                            if len(log_content) > 200
                            else log_content
                        )
                        print(f"[Agent][{event['type']}] {truncated}")
            else:
                # Fallback for messages without content blocks (SystemMessage, etc.)
                content = self._extract_message_content(message)
                event_type = self._determine_event_type(message, msg_class, content)

                # Special handling for ResultMessage
                if msg_class == "ResultMessage":
                    formatted_content, metrics = self._parse_result_message(message)
                    if metrics:
                        # Store metrics in trace execution section
                        self.trace["execution"]["metrics"] = metrics
                    content = formatted_content

                if content or str(message):
                    self.event_sequence += 1

                    msg_event: dict[str, Any] = {
                        "seq": self.event_sequence,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "type": event_type,
                        "content": content if content else str(message),
                    }

                    # Extract tool info based on message class or event type
                    if msg_class.endswith("ToolUseBlock") or event_type == "TOOL_CALL":
                        self._process_tool_use_block(message, msg_event)
                    elif (
                        msg_class.endswith("ToolResultBlock")
                        or event_type == "TOOL_RESULT"
                        or (event_type == "ERROR" and "ToolResultBlock" in str(message))
                    ):
                        self._process_tool_result_block(message, msg_event)

                    self.trace["events"].append(msg_event)

                    # Print for workflow logs - only show first 200 chars
                    log_content = content if content else str(message)
                    truncated = (
                        log_content[:200] + "..."
                        if len(log_content) > 200
                        else log_content
                    )
                    print(f"[Agent][{event_type}] {truncated}")

            # Pass through original message
            yield message

    def finalize(
        self,
        status: str = "SUCCESS",
        changes_made: int = 0,
        files_modified: list[str] | None = None,
        commit_sha: str | None = None,
        commit_url: str | None = None,
    ) -> None:
        """Finalize trace with execution results.

        Parameters
        ----------
        status : str, optional
            Execution status: "SUCCESS", "FAILED", or "PARTIAL" (default="SUCCESS").
        changes_made : int, optional
            Number of changes applied (default=0).
        files_modified : list[str] or None, optional
            List of file paths modified (default=None).
        commit_sha : str or None, optional
            Git commit SHA if committed (default=None).
        commit_url : str or None, optional
            URL to commit on GitHub (default=None).

        """
        end_time = datetime.now(UTC)
        duration = (end_time - self.start_time).total_seconds()

        self.trace["execution"]["end_time"] = end_time.isoformat()
        self.trace["execution"]["duration_seconds"] = int(duration)

        self.trace["result"].update(
            {
                "status": status,
                "changes_made": changes_made,
                "files_modified": files_modified or [],
                "commit_sha": commit_sha,
                "commit_url": commit_url,
            }
        )

    def save_trace(self, filepath: str) -> None:
        """Save trace to JSON file.

        Parameters
        ----------
        filepath : str
            Path to save trace JSON.

        Notes
        -----
        Creates parent directories if they don't exist.

        """
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, "w") as f:
            json.dump(self.trace, f, indent=2)

        print(f"✓ Trace saved to {filepath}")

    def upload_to_gcs(
        self, bucket_name: str, trace_filepath: str, destination_blob_name: str
    ) -> bool:
        """Upload trace JSON to Google Cloud Storage.

        Parameters
        ----------
        bucket_name : str
            GCS bucket name (without gs:// prefix).
        trace_filepath : str
            Local path to trace JSON file.
        destination_blob_name : str
            Target path in GCS bucket.

        Returns
        -------
        bool
            True if upload succeeded, False otherwise.

        Notes
        -----
        Uses gcloud CLI (must be authenticated in workflow).
        Prints status messages to stdout.

        """
        try:
            # Use gcloud CLI for simplicity (already authenticated in workflow)
            cmd = [
                "gcloud",
                "storage",
                "cp",
                trace_filepath,
                f"gs://{bucket_name}/{destination_blob_name}",
            ]

            subprocess.run(cmd, capture_output=True, text=True, check=True)

            print(f"✓ Trace uploaded to gs://{bucket_name}/{destination_blob_name}")
            return True

        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to upload trace to GCS: {e.stderr}")
            return False
        except Exception as e:
            print(f"✗ Unexpected error uploading to GCS: {e}")
            return False

    def get_summary(self) -> str:
        """Generate human-readable summary of execution.

        Returns
        -------
        str
            Summary string for PR comments with execution statistics.

        """
        event_counts: dict[str, int] = {}
        for event in self.trace["events"]:
            event_type = event["type"]
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        summary_parts = []

        if self.trace["result"]["status"] == "SUCCESS":
            summary_parts.append(
                f"✓ Successfully fixed {self.failure_info['type']} failures"
            )
        elif self.trace["result"]["status"] == "FAILED":
            summary_parts.append(
                f"✗ Could not automatically fix {self.failure_info['type']} failures"
            )
        else:
            summary_parts.append(
                f"⚠ Partially fixed {self.failure_info['type']} failures"
            )

        summary_parts.append(
            f"Modified {len(self.trace['result']['files_modified'])} files"
        )
        summary_parts.append(f"Executed {sum(event_counts.values())} agent actions")

        if event_counts:
            summary_parts.append(
                f"({', '.join(f'{count} {event_type.lower()}' for event_type, count in event_counts.items())})"
            )

        return " - ".join(summary_parts)


def create_tracer_from_env() -> AgentExecutionTracer:
    """Create tracer from environment variables set by GitHub Actions workflow.

    Expected environment variables:
    - TARGET_REPO: Repository name (owner/repo)
    - PR_NUMBER: Pull request number
    - PR_TITLE: Pull request title
    - PR_AUTHOR: Pull request author
    - PR_URL: Pull request URL
    - FAILURE_TYPE: Failure type classification
    - FAILED_CHECK_NAMES: Comma-separated list of failed check names
    - FAILURE_LOGS: Truncated failure logs
    - GITHUB_RUN_ID: GitHub Actions run ID
    - GITHUB_SERVER_URL: GitHub server URL
    - GITHUB_REPOSITORY: Repository name for URL construction

    Returns
    -------
    AgentExecutionTracer
        Configured tracer instance ready to capture agent execution.

    """
    pr_info = {
        "repo": os.getenv("TARGET_REPO", "unknown/repo"),
        "number": int(os.getenv("PR_NUMBER", "0")),
        "title": os.getenv("PR_TITLE", ""),
        "author": os.getenv("PR_AUTHOR", ""),
        "url": os.getenv("PR_URL", ""),
    }

    failure_info = {
        "type": os.getenv("FAILURE_TYPE", "unknown"),
        "checks": os.getenv("FAILED_CHECK_NAMES", "").split(","),
        "logs_truncated": os.getenv("FAILURE_LOGS", "")[:5000],  # Limit log size
    }

    workflow_run_id = os.getenv("GITHUB_RUN_ID", "unknown")
    github_run_url = (
        f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/"
        f"{os.getenv('GITHUB_REPOSITORY', '')}/"
        f"actions/runs/{workflow_run_id}"
    )

    return AgentExecutionTracer(
        pr_info=pr_info,
        failure_info=failure_info,
        workflow_run_id=workflow_run_id,
        github_run_url=github_run_url,
    )
