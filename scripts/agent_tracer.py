"""Agent Execution Tracer for Claude Agent SDK.

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
    """Captures and structures agent execution traces from Claude Agent SDK.

    Features:
    - Full message content capture (no truncation)
    - Event classification (REASONING, TOOL_CALL, ACTION, ERROR)
    - Tool invocation parsing from message content
    - Structured JSON output with comprehensive schema
    - GCS upload support
    """

    def __init__(
        self,
        pr_info: dict[str, Any],
        failure_info: dict[str, Any],
        workflow_run_id: str,
        github_run_url: str,
    ):
        """Initialize tracer with PR and workflow context.

        Args:
            pr_info: Dict with keys: repo, number, title, author, url
            failure_info: Dict with keys: type, checks, logs_truncated
            workflow_run_id: GitHub Actions run ID
            github_run_url: URL to GitHub Actions run

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

        Returns:
            One of: REASONING, TOOL_CALL, ACTION, ERROR, INFO

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

        Returns:
            Dict with tool, parameters, and other info, or None if not a tool call

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

        Args:
            message: Agent SDK message object

        Returns:
            Extracted content string

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

        Args:
            message: Agent SDK message object
            msg_class: Class name of message
            content: Extracted content string

        Returns:
            Event type string (ERROR, TOOL_RESULT, TOOL_CALL, etc.)

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

    async def capture_agent_stream(
        self, agent_stream: AsyncIterator[Any]
    ) -> AsyncIterator[Any]:
        """Wrap agent stream to capture messages while passing them through.

        Args:
            agent_stream: Async iterator from Claude Agent SDK query()

        Yields:
            Original messages from agent stream

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

                # Extract tool info for ToolUseBlock messages
                if msg_class == "ToolUseBlock":
                    # Extract directly from message attributes
                    tool_name = getattr(message, "name", None)
                    tool_input = getattr(message, "input", {})
                    tool_id = getattr(message, "id", None)
                    if tool_name:
                        event["tool"] = tool_name
                        event["parameters"] = tool_input
                        if tool_id:
                            event["tool_use_id"] = tool_id
                elif msg_class == "ToolResultBlock":
                    # Extract tool_use_id to link result to tool call
                    tool_use_id = getattr(message, "tool_use_id", None)
                    if tool_use_id:
                        event["tool_use_id"] = tool_use_id
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

        Args:
            status: SUCCESS, FAILED, or PARTIAL
            changes_made: Number of changes applied
            files_modified: List of file paths modified
            commit_sha: Git commit SHA if committed
            commit_url: URL to commit on GitHub

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

        Args:
            filepath: Path to save trace JSON

        """
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, "w") as f:
            json.dump(self.trace, f, indent=2)

        print(f"✓ Trace saved to {filepath}")

    def upload_to_gcs(
        self, bucket_name: str, trace_filepath: str, destination_blob_name: str
    ) -> bool:
        """Upload trace JSON to Google Cloud Storage.

        Args:
            bucket_name: GCS bucket name (without gs:// prefix)
            trace_filepath: Local path to trace JSON file
            destination_blob_name: Target path in GCS bucket

        Returns:
            True if upload succeeded, False otherwise

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

        Returns:
            Summary string for PR comments

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

    Expected env vars:
    - TARGET_REPO
    - PR_NUMBER
    - PR_TITLE
    - PR_AUTHOR
    - PR_URL
    - FAILURE_TYPE
    - FAILED_CHECK_NAMES
    - FAILURE_LOGS (truncated)
    - GITHUB_RUN_ID
    - GITHUB_SERVER_URL
    - GITHUB_REPOSITORY
    - GITHUB_RUN_ID (for URL construction)

    Returns:
        Configured AgentExecutionTracer instance

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
