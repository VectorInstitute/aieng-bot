"""Agent execution tracer for Claude Agent SDK.

This module provides comprehensive observability for Claude Agent SDK executions.
It captures tool calls, reasoning, actions, and errors in a structured format
similar to LangSmith/Langfuse for later analysis and dashboard display.
"""

from __future__ import annotations

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
                "tools_allowed": ["Read", "Edit", "Bash", "Glob", "Grep"],
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
        if msg_class == "ToolResultBlock":
            # For ToolResultBlock, always parse from string representation
            # since is_error attribute access is unreliable
            msg_str = str(message)
            # Only mark as ERROR if explicitly is_error=True
            if "is_error=True" in msg_str:
                return "ERROR"
            # Otherwise it's a successful tool result
            return "TOOL_RESULT"

        if msg_class == "ToolUseBlock":
            return "TOOL_CALL"

        if msg_class == "TextBlock":
            return self.classify_message(content if content else str(message))

        # Fallback to content-based classification
        return self.classify_message(content if content else str(message))

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
            name_match = re.search(r"name=['\"](\w+)['\"]", msg_str)
            if name_match:
                tool_name = name_match.group(1)

        # Always set tool name (default to "Unknown" if all else fails)
        event["tool"] = tool_name if tool_name else "Unknown"
        event["parameters"] = tool_input
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
            content = self._extract_message_content(message)
            event_type = self._determine_event_type(message, msg_class, content)

            if content or str(message):
                self.event_sequence += 1

                event: dict[str, Any] = {
                    "seq": self.event_sequence,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "type": event_type,
                    "content": content if content else str(message),
                }

                # Extract tool info based on message class
                if msg_class == "ToolUseBlock":
                    self._process_tool_use_block(message, event)
                elif msg_class == "ToolResultBlock":
                    self._process_tool_result_block(message, event)
                elif event_type == "TOOL_CALL":
                    # Fallback: try to extract from content string
                    tool_info = self.extract_tool_info(
                        content if content else str(message), event_type
                    )
                    if tool_info:
                        event.update(tool_info)

                self.trace["events"].append(event)

                # Print for workflow logs - only show first 200 chars
                log_content = content if content else str(message)
                truncated = (
                    log_content[:200] + "..." if len(log_content) > 200 else log_content
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
