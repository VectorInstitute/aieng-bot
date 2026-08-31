"""Agent fixer implementation using Claude Agent SDK with Skills."""

import json
import os
from contextlib import nullcontext
from pathlib import Path

import claude_agent_sdk
from claude_agent_sdk import ClaudeAgentOptions
from langfuse import propagate_attributes

from ..config import get_model_name
from ..observability import AgentExecutionTracer, instrument_claude_agent_sdk
from ..utils.logging import log_error, log_info, log_success
from .models import AgentFixResult, AgenticLoopRequest
from .prompts import AGENTIC_LOOP_PROMPT

TRACE_FILE = "/tmp/agent-execution-trace.json"
SUMMARY_FILE = "/tmp/fix-summary.txt"

# Tools available to the agentic fix loop
AGENTIC_LOOP_TOOLS = [
    "Read",
    "Edit",
    "Write",
    "Bash",
    "Glob",
    "Grep",
    "Skill",
    "WebSearch",
    "TodoWrite",
    "Task",  # Enables built-in Explore/Plan agents
]


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

        self.langfuse = instrument_claude_agent_sdk()

    async def run_agentic_loop(self, request: AgenticLoopRequest) -> AgentFixResult:
        """Run the full agentic fix loop for a PR.

        This method runs Claude in an autonomous loop to fix a PR, wait for CI,
        retry if needed, and merge when ready.

        Parameters
        ----------
        request : AgenticLoopRequest
            The agentic loop request containing PR context and configuration.

        Returns
        -------
        AgentFixResult
            Result of the fix attempt including trace and summary files.
            The trace is saved even when the agent run fails, so failed
            executions remain debuggable.

        """
        log_info(
            f"Starting agentic fix loop for {request.repo}#{request.pr_number} "
            f"(max {request.max_retries} retries, {request.timeout_minutes} min timeout)"
        )

        tracer = self._create_agentic_tracer(request)
        error_message: str | None = None

        try:
            # Write PR context to file for Claude to read
            self._write_agentic_context(request)

            # Build the agentic loop prompt
            prompt = self._build_agentic_prompt(request)

            log_info("Starting Claude Agent SDK for agentic loop...")

            # Configure agent options - agentic loop needs the full tool set
            options = ClaudeAgentOptions(
                allowed_tools=AGENTIC_LOOP_TOOLS,
                permission_mode="acceptEdits",
                cwd=request.cwd,
                setting_sources=["project"],  # Load .claude/skills/
                model=get_model_name(),
            )

            observation = (
                self.langfuse.start_as_current_observation(
                    as_type="agent",
                    name="fix-pr",
                    input={
                        "repo": request.repo,
                        "pr_number": request.pr_number,
                        "pr_title": request.pr_title,
                        "failure_types": request.failure_types,
                    },
                    metadata={
                        "pr_url": request.pr_url,
                        "pr_author": request.pr_author,
                        "workflow_run_id": request.workflow_run_id,
                        "github_run_url": request.github_run_url,
                        "max_retries": request.max_retries,
                    },
                )
                if self.langfuse
                else nullcontext()
            )
            attributes = (
                propagate_attributes(
                    session_id=f"{request.repo}#{request.pr_number}",
                    tags=["fixer", request.repo, *request.failure_types],
                )
                if self.langfuse
                else nullcontext()
            )

            # Run agent with tracing (local summary/file-metrics tracer +
            # Langfuse via the OpenInference Claude Agent SDK instrumentor).
            # Call via the claude_agent_sdk module (not a `from ... import query`
            # bound at module load) so this always resolves the instrumented
            # query() - instrument_claude_agent_sdk() above patches the module
            # attribute at runtime, after this module's own imports have run.
            with observation, attributes:
                agent_stream = claude_agent_sdk.query(prompt=prompt, options=options)
                traced_stream = tracer.capture_agent_stream(agent_stream)

                # Consume the traced stream
                async for _ in traced_stream:
                    pass  # Tracer handles logging

            log_success("Agentic loop completed")
        except Exception as e:
            log_error(f"Agentic loop failed: {e}")
            error_message = str(e)

        status = "FAILED" if error_message else "SUCCESS"
        trace_file, summary_file = self._finalize_and_save(tracer, status)

        return AgentFixResult(
            status=status,
            trace_file=trace_file,
            summary_file=summary_file,
            error_message=error_message,
        )

    def _finalize_and_save(
        self, tracer: AgentExecutionTracer, status: str
    ) -> tuple[str, str]:
        """Finalize the trace and persist trace and summary files.

        Parameters
        ----------
        tracer : AgentExecutionTracer
            Tracer holding the captured execution events.
        status : str
            Final execution status ("SUCCESS" or "FAILED").

        Returns
        -------
        tuple[str, str]
            (trace_file, summary_file) paths, empty strings if saving failed.

        """
        try:
            changes_made, files_modified = tracer.extract_file_metrics()
            tracer.finalize(
                status=status,
                changes_made=changes_made,
                files_modified=files_modified,
            )

            tracer.save_trace(TRACE_FILE)
            with open(SUMMARY_FILE, "w") as f:
                f.write(tracer.get_summary())

            log_success(f"Trace saved to {TRACE_FILE}")
            log_success(f"Summary saved to {SUMMARY_FILE}")
        except Exception as e:
            log_error(f"Failed to save execution trace: {e}")
            return "", ""

        return TRACE_FILE, SUMMARY_FILE

    def _write_agentic_context(self, request: AgenticLoopRequest) -> None:
        """Write PR context to file for the agentic loop.

        Parameters
        ----------
        request : AgenticLoopRequest
            The agentic loop request containing PR metadata.

        """
        context_file = Path(request.cwd) / ".pr-context.json"

        context = {
            "repo": request.repo,
            "pr_number": request.pr_number,
            "pr_title": request.pr_title,
            "pr_author": request.pr_author,
            "pr_url": request.pr_url,
            "head_ref": request.head_ref,
            "base_ref": request.base_ref,
            "failure_types": request.failure_types,
            "failure_type": request.failure_type,  # Backward compatibility
            "failure_logs_file": request.failure_logs_file,
            "max_retries": request.max_retries,
            "timeout_minutes": request.timeout_minutes,
        }

        log_info(f"Writing PR context to {context_file}")
        with open(context_file, "w") as f:
            json.dump(context, f, indent=2)

    def _build_agentic_prompt(self, request: AgenticLoopRequest) -> str:
        """Build the prompt for the agentic fix loop.

        Parameters
        ----------
        request : AgenticLoopRequest
            The agentic loop request containing configuration.

        Returns
        -------
        str
            Formatted prompt for Claude Agent SDK.

        """
        # Format failure types as a readable list
        failure_types_display: list[str] | str = (
            request.failure_types
            if len(request.failure_types) > 1
            else request.failure_type
        )

        # Build mission and CI pass instructions based on merge_pr flag
        if request.merge_pr:
            mission = (
                "Fix this PR and merge it. "
                "**Your job is not done until the PR is merged or max retries exhausted.**"
            )
            on_ci_pass = f"""**If CI passes:**
```bash
gh pr merge {request.pr_number} --repo {request.repo} --squash --delete-branch
```
A zero exit code means the PR was merged successfully. Exit with success.
Note: `gh pr view` does not have a `merged` JSON field — use `state` and `mergedAt` if you need to verify."""
            critical_rule_suffix = ", then merge or fix"
        else:
            mission = (
                "Fix this PR and ensure CI passes. "
                "**Your job is not done until CI passes or max retries exhausted.** "
                "Do NOT merge the PR - only fix and push."
            )
            on_ci_pass = """**If CI passes:**
Exit with success. Do NOT merge the PR."""
            critical_rule_suffix = ", then exit or fix"

        return AGENTIC_LOOP_PROMPT.format(
            repo=request.repo,
            pr_number=request.pr_number,
            head_ref=request.head_ref,
            base_ref=request.base_ref,
            failure_types=failure_types_display,
            max_retries=request.max_retries,
            timeout_minutes=request.timeout_minutes,
            mission=mission,
            on_ci_pass=on_ci_pass,
            critical_rule_suffix=critical_rule_suffix,
        )

    def _create_agentic_tracer(
        self, request: AgenticLoopRequest
    ) -> AgentExecutionTracer:
        """Create and configure an execution tracer for agentic loop.

        Parameters
        ----------
        request : AgenticLoopRequest
            The agentic loop request containing metadata for the tracer.

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
            "type": request.failure_type,  # Primary type for backward compatibility
            "types": request.failure_types,  # Full list of failure types
            "checks": request.failed_check_names,
        }

        return AgentExecutionTracer(
            pr_info=pr_info,
            failure_info=failure_info,
            workflow_run_id=request.workflow_run_id,
            github_run_url=request.github_run_url,
            model=get_model_name(),
            allowed_tools=AGENTIC_LOOP_TOOLS,
        )
