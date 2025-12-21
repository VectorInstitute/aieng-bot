"""Agent fixer implementation using Claude Agent SDK with Skills."""

import json
import os
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query

from ..observability import AgentExecutionTracer
from ..utils.logging import log_error, log_info, log_success
from .models import AgentFixRequest, AgentFixResult


class AgentFixer:
    """Fix PR failures using Claude Agent SDK.

    This class wraps the Claude Agent SDK to provide a clean interface
    for applying automated fixes to PR failures.

    """

    def __init__(self) -> None:
        """Initialize the agent fixer."""
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    async def apply_fixes(self, request: AgentFixRequest) -> AgentFixResult:
        """Apply fixes to a PR using Claude Agent SDK with Skills.

        Parameters
        ----------
        request : AgentFixRequest
            The fix request containing PR context and failure information.

        Returns
        -------
        AgentFixResult
            Result of the fix attempt including trace and summary files.

        Raises
        ------
        RuntimeError
            If agent execution fails.

        """
        log_info(
            f"Applying fixes for {request.repo}#{request.pr_number} "
            f"({request.failure_type} failure)"
        )

        try:
            # Write PR context to file for skills to read
            self._write_pr_context(request)

            # Build simple prompt that directs Claude to use skills
            prompt = self._build_prompt(request)

            log_info("Starting Claude Agent SDK with skills...")
            # Initialize tracer
            tracer = self._create_tracer(request)

            # Configure agent options with skills support
            options = ClaudeAgentOptions(
                allowed_tools=["Read", "Edit", "Bash", "Glob", "Grep", "Skill"],
                permission_mode="acceptEdits",
                cwd=request.cwd,
                setting_sources=["project"],  # Load .claude/skills/
            )

            # Run agent with tracing
            agent_stream = query(prompt=prompt, options=options)
            traced_stream = tracer.capture_agent_stream(agent_stream)

            # Consume the traced stream
            async for _ in traced_stream:
                pass  # Tracer handles logging

            log_success("Agent completed fixes")

            # Finalize trace
            tracer.finalize(status="SUCCESS")

            # Save trace and summary
            trace_file = "/tmp/agent-execution-trace.json"
            summary_file = "/tmp/fix-summary.txt"

            tracer.save_trace(trace_file)

            with open(summary_file, "w") as f:
                f.write(tracer.get_summary())

            log_success(f"Trace saved to {trace_file}")
            log_success(f"Summary saved to {summary_file}")

            return AgentFixResult(
                status="SUCCESS",
                trace_file=trace_file,
                summary_file=summary_file,
            )

        except Exception as e:
            log_error(f"Agent execution failed: {e}")
            return AgentFixResult(
                status="FAILED",
                trace_file="",
                summary_file="",
                error_message=str(e),
            )

    def _write_pr_context(self, request: AgentFixRequest) -> None:
        """Write PR context to file for skills to read.

        Parameters
        ----------
        request : AgentFixRequest
            The fix request containing PR metadata.

        """
        context_file = Path(request.cwd) / ".pr-context.json"

        context = {
            "repo": request.repo,
            "pr_number": request.pr_number,
            "pr_title": request.pr_title,
            "pr_author": request.pr_author,
            "pr_url": request.pr_url,
            "failure_type": request.failure_type,
            "failed_checks": request.failed_check_names.split(","),
            "failure_logs_file": request.failure_logs_file,
        }

        log_info(f"Writing PR context to {context_file}")
        with open(context_file, "w") as f:
            json.dump(context, f, indent=2)

    def _build_prompt(self, request: AgentFixRequest) -> str:
        """Build a simple prompt that directs Claude to use skills.

        Parameters
        ----------
        request : AgentFixRequest
            The fix request containing failure information.

        Returns
        -------
        str
            Prompt for Claude Agent SDK.

        """
        # Verify failure logs exist
        logs_info = "detailed error logs"
        if not Path(request.failure_logs_file).exists():
            log_error(f"Failure logs file not found: {request.failure_logs_file}")
            logs_info = "no failure logs (file not found)"

        return f"""You are the AI Engineering Maintenance Bot for Vector Institute.

A Dependabot or pre-commit-ci PR has {request.failure_type} check failures.

## Context Files
- `.pr-context.json` - PR metadata (repo, number, title, etc.)
- `{request.failure_logs_file}` - {logs_info}

## Your Task
Fix this PR's {request.failure_type} failures using the appropriate skill.

Read the context and failure logs, then apply the fix-{request.failure_type}-failures skill to resolve the issues.

Make minimal, targeted changes following the skill's guidance.
"""

    def _create_tracer(self, request: AgentFixRequest) -> AgentExecutionTracer:
        """Create and configure an execution tracer.

        Parameters
        ----------
        request : AgentFixRequest
            The fix request containing metadata for the tracer.

        Returns
        -------
        AgentExecutionTracer
            Configured tracer instance.

        """
        pr_info = {
            "repo": request.repo,
            "number": request.pr_number,
            "title": request.pr_title,
            "author": request.pr_author,
            "url": request.pr_url,
        }

        failure_info = {
            "type": request.failure_type,
            "checks": request.failed_check_names.split(","),
            "logs_truncated": "",  # Logs are read from file, not embedded
        }

        return AgentExecutionTracer(
            pr_info=pr_info,
            failure_info=failure_info,
            workflow_run_id=request.workflow_run_id,
            github_run_url=request.github_run_url,
        )
