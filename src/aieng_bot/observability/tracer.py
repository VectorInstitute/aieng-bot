"""Agent execution tracer for Claude Agent SDK.

This module provides comprehensive observability for Claude Agent SDK executions.
It captures tool calls, reasoning, actions, and errors in a structured format
similar to LangSmith/Langfuse for later analysis and dashboard display.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from .classifiers import MessageClassifier
from .extractors import ContentExtractor, ToolInfoExtractor
from .parsers import ResultMessageParser
from .processors import EventLogger, EventProcessor, SummaryGenerator
from .storage import TraceStorage


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
        Failure context dict with keys: type, checks.
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

    """

    # Tool call patterns for parsing
    TOOL_PATTERNS = {
        "Read": r"(?:Reading|Read)\s+(?:file\s+)?[`'\"]?(.+?)[`'\"]?",
        "Edit": r"(?:Editing|Edit)\s+[`'\"]?(.+?)[`'\"]?",
        "Bash": r"(?:Running|Execute|Executing)\s+[`'\"]?(.+?)[`'\"]?",
        "Glob": r"(?:Searching|Search|Finding|Glob)\s+(?:for\s+)?[`'\"]?(.+?)[`'\"]?",
        "Grep": r"(?:Grepping|Grep|Searching)\s+(?:for\s+)?[`'\"]?(.+?)[`'\"]?",
        "Skill": r"(?:Launching\s+skill|Skill):\s+([a-zA-Z0-9_-]+)",
        "WebSearch": r"(?:Searching web|WebSearch|Web search)\s+(?:for\s+)?[`'\"]?(.+?)[`'\"]?",
    }

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
            Failure context dict with keys: type, checks.
        workflow_run_id : str
            GitHub Actions run ID.
        github_run_url : str
            URL to GitHub Actions run.

        """
        self.pr_info = pr_info
        self.failure_info = failure_info
        self.workflow_run_id = workflow_run_id
        self.github_run_url = github_run_url

        self.trace: dict[str, Any] = self._initialize_trace()
        self.event_sequence = 0
        self.start_time = datetime.now(UTC)

        # Initialize helper components
        self.classifier = MessageClassifier(self.TOOL_PATTERNS)
        self.tool_extractor = ToolInfoExtractor(self.TOOL_PATTERNS)
        self.event_processor = EventProcessor(self.classifier, self.tool_extractor)
        self.event_logger = EventLogger()

    def _initialize_trace(self) -> dict[str, Any]:
        """Initialize trace data structure.

        Returns
        -------
        dict[str, Any]
            Initial trace structure with metadata and empty events.

        """
        return {
            "metadata": {
                "workflow_run_id": self.workflow_run_id,
                "github_run_url": self.github_run_url,
                "timestamp": datetime.now(UTC).isoformat(),
                "pr": self.pr_info,
                "failure": self.failure_info,
            },
            "execution": {
                "start_time": datetime.now(UTC).isoformat(),
                "end_time": None,
                "duration_seconds": None,
                "model": "claude-sonnet-4.5",
                "tools_allowed": [
                    "Read",
                    "Edit",
                    "Bash",
                    "Glob",
                    "Grep",
                    "Skill",
                    "WebSearch",
                ],
                "metrics": None,
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
                self._process_message_with_blocks(message)
            else:
                self._process_message_without_blocks(message, msg_class)

            # Pass through original message
            yield message

    def _process_message_with_blocks(self, message: Any) -> None:
        """Process message with content blocks.

        Parameters
        ----------
        message : Any
            Message with content blocks list.

        """
        for block in message.content:
            event = self.event_processor.process_content_block(block)
            if event:
                self._add_event_to_trace(event)

    def _process_message_without_blocks(self, message: Any, msg_class: str) -> None:
        """Process message without content blocks.

        Parameters
        ----------
        message : Any
            Message object.
        msg_class : str
            Class name of the message.

        """
        content = ContentExtractor.extract_message_content(message)
        event_type = self.classifier.classify_by_class(message, msg_class, content)

        # Special handling for ResultMessage
        if msg_class == "ResultMessage":
            formatted_content, metrics = ResultMessageParser.parse(message)
            if metrics:
                self.trace["execution"]["metrics"] = metrics
            content = formatted_content

        if content or str(message):
            event: dict[str, Any] = {
                "seq": 0,  # Will be set by _add_event_to_trace
                "timestamp": datetime.now(UTC).isoformat(),
                "type": event_type,
                "content": content if content else str(message),
            }

            # Extract tool info if applicable
            if msg_class.endswith("ToolUseBlock") or event_type == "TOOL_CALL":
                self.event_processor._process_tool_use(message, event)
            elif (
                msg_class.endswith("ToolResultBlock")
                or event_type == "TOOL_RESULT"
                or (event_type == "ERROR" and "ToolResultBlock" in str(message))
            ):
                self.event_processor._process_tool_result(message, event)
                self.event_processor.link_tool_result_to_call(
                    event, self.trace["events"]
                )

            self._add_event_to_trace(event)

    def _add_event_to_trace(self, event: dict[str, Any]) -> None:
        """Add event to trace with sequence number and logging.

        Parameters
        ----------
        event : dict[str, Any]
            Event dictionary to add.

        """
        self.event_sequence += 1
        event["seq"] = self.event_sequence
        self.trace["events"].append(event)
        self.event_logger.log_event(event)

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
        TraceStorage.save_to_file(self.trace, filepath)

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
        return TraceStorage.upload_to_gcs(
            trace_filepath, bucket_name, destination_blob_name
        )

    def get_summary(self) -> str:
        """Generate human-readable summary of execution.

        Returns
        -------
        str
            Summary string for PR comments with execution statistics.

        """
        return SummaryGenerator.generate(self.trace, self.failure_info["type"])


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
