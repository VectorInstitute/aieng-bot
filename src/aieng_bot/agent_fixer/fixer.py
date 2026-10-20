"""Agent fixer implementation using Claude Agent SDK with Skills."""

import asyncio
import json
import os
import subprocess
import time
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path

import claude_agent_sdk
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from langfuse import propagate_attributes

from ..config import get_model_name
from ..observability import AgentExecutionTracer, instrument_claude_agent_sdk
from ..utils.github_client import GitHubClient, PRStatus
from ..utils.logging import log_error, log_info, log_success, log_warning
from .models import AgentFixResult, AgenticLoopRequest
from .prompts import AGENTIC_LOOP_PROMPT, CI_STATUS_PROMPT

TRACE_FILE = "/tmp/agent-execution-trace.json"
SUMMARY_FILE = "/tmp/fix-summary.txt"
ERROR_FILE = "/tmp/fix-error.txt"

# Upper bound on agent sessions (initial run plus resumes after CI waits)
MAX_AGENT_SESSIONS = 10
# Seconds between GitHub check-status polls while CI is running
CI_POLL_SECONDS = 60
# Seconds to wait for checks to register on a fresh push before treating an
# empty check list as "no CI configured"
CHECKS_REGISTER_GRACE_SECONDS = 180
# Characters of the agent's final message kept in a failure reason
MAX_AGENT_REASON_CHARS = 500

# Environment for the agent's CLI. Nothing re-invokes a headless session whose
# turn ended on a background job, so background tasks are disabled and long
# commands (uv sync, pytest) run in the foreground with room to finish.
AGENT_ENV = {
    "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
    "BASH_DEFAULT_TIMEOUT_MS": str(30 * 60 * 1000),
    "BASH_MAX_TIMEOUT_MS": str(60 * 60 * 1000),
}

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
                env=AGENT_ENV,
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
                error_message = await self._run_until_resolved(
                    request, prompt, options, tracer
                )

            if error_message:
                log_error(f"Agentic loop did not resolve the PR: {error_message}")
            else:
                log_success("Agentic loop completed")
        except Exception as e:
            log_error(f"Agentic loop failed: {e}")
            error_message = str(e)

        status = "FAILED" if error_message else "SUCCESS"
        trace_file, summary_file = self._finalize_and_save(tracer, status)
        if error_message:
            self._save_error(error_message)

        return AgentFixResult(
            status=status,
            trace_file=trace_file,
            summary_file=summary_file,
            error_message=error_message,
        )

    async def _run_until_resolved(
        self,
        request: AgenticLoopRequest,
        prompt: str,
        options: ClaudeAgentOptions,
        tracer: AgentExecutionTracer,
    ) -> str | None:
        """Run the agent, resuming it until GitHub shows the PR resolved.

        A headless agent session cannot block on a background wait, so it may
        end its turn while CI is still running. The outcome is therefore read
        from GitHub rather than inferred from the agent's stream ending: the
        harness waits for checks to finish and resumes the session with the
        results until the goal is reached or the time budget runs out.

        The session is only resumed when the agent stopped to wait on CI, or
        (once) when it left the PR green but unmerged. If CI had already
        failed when it stopped, the agent chose not to proceed, and its own
        explanation is returned instead of resuming it with the same results.
        A green PR that branch protection holds for an approving review is
        reported without resuming, since the agent cannot approve it.

        Parameters
        ----------
        request : AgenticLoopRequest
            The agentic loop request containing PR context and configuration.
        prompt : str
            Initial prompt for the agent.
        options : ClaudeAgentOptions
            Agent options for the initial session.
        tracer : AgentExecutionTracer
            Tracer capturing every session's messages.

        Returns
        -------
        str | None
            None when the PR reached its goal, otherwise why it did not.

        """
        github = GitHubClient()
        deadline = time.monotonic() + request.timeout_minutes * 60
        session_id: str | None = None
        status: PRStatus | None = None
        merge_resumed = False

        for session in range(1, MAX_AGENT_SESSIONS + 1):
            if session > 1:
                options = (
                    replace(options, resume=session_id)
                    if session_id
                    else replace(options, continue_conversation=True)
                )
            head_before = self._local_head(request.cwd)
            new_session_id, agent_result = await self._run_agent_session(
                prompt, options, tracer
            )
            session_id = new_session_id or session_id
            head_after = self._local_head(request.cwd)
            new_head = head_after if head_after != head_before else None

            status, waited = await self._wait_for_checks(
                github, request, deadline, new_head=new_head
            )
            log_info(f"PR status after agent session {session}: {status.summary()}")

            if self._goal_reached(request, status):
                return None
            stop_reason = self._stop_reason(
                request=request,
                status=status,
                waited=waited,
                agent_result=agent_result,
                deadline=deadline,
                merge_resumed=merge_resumed,
            )
            if stop_reason:
                return stop_reason
            # Without a CI wait, the only way to get here is a green but
            # unmerged PR, which is resumed once to let the agent merge it.
            merge_resumed = merge_resumed or not waited

            prompt = CI_STATUS_PROMPT.format(
                pr_number=request.pr_number, status=status.summary()
            )

        summary = status.summary() if status else "unknown"
        return f"Agent stopped {MAX_AGENT_SESSIONS} times without resolving: {summary}"

    @staticmethod
    def _stop_reason(
        *,
        request: AgenticLoopRequest,
        status: PRStatus,
        waited: bool,
        agent_result: str | None,
        deadline: float,
        merge_resumed: bool,
    ) -> str | None:
        """Return why the loop should stop without resuming, or None to resume.

        Parameters
        ----------
        request : AgenticLoopRequest
            The agentic loop request containing PR context and configuration.
        status : PRStatus
            PR status after the session and any CI wait.
        waited : bool
            Whether CI was still running when the session ended.
        agent_result : str | None
            The agent's final message for the session.
        deadline : float
            Monotonic time at which the run's budget ends.
        merge_resumed : bool
            Whether the agent was already resumed to merge a green PR.

        Returns
        -------
        str | None
            The failure reason, or None when the session should be resumed.

        """
        if status.state != "OPEN":
            return f"PR is {status.state} but was not merged by the bot"
        if time.monotonic() >= deadline:
            return (
                f"Timed out after {request.timeout_minutes} minutes: {status.summary()}"
            )
        green_unmerged = request.merge_pr and status.ci_passed
        if green_unmerged and status.review_blocked:
            return (
                "CI passed but branch protection requires an approving review "
                f"before merging ({status.summary()})"
            )
        if waited or (green_unmerged and not merge_resumed):
            return None
        reason = (agent_result or "").strip()[:MAX_AGENT_REASON_CHARS]
        outcome = (
            "CI passed but the agent did not merge"
            if green_unmerged
            else "Agent stopped with CI unresolved"
        )
        return f"{outcome} ({status.summary()}): {reason or 'no explanation given'}"

    async def _run_agent_session(
        self,
        prompt: str,
        options: ClaudeAgentOptions,
        tracer: AgentExecutionTracer,
    ) -> tuple[str | None, str | None]:
        """Run one agent session to completion.

        Returns
        -------
        tuple[str | None, str | None]
            (session_id, final result text) from the session's ResultMessage.

        """
        session_id: str | None = None
        result_text: str | None = None
        agent_stream = claude_agent_sdk.query(prompt=prompt, options=options)
        async for message in tracer.capture_agent_stream(agent_stream):
            if isinstance(message, ResultMessage):
                session_id = message.session_id
                result_text = message.result
        return session_id, result_text

    @staticmethod
    def _local_head(cwd: str) -> str | None:
        """Return the commit checked out in the agent's working tree."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout.strip() or None

    async def _wait_for_checks(
        self,
        github: GitHubClient,
        request: AgenticLoopRequest,
        deadline: float,
        new_head: str | None = None,
    ) -> tuple[PRStatus, bool]:
        """Poll the PR until no checks are pending, it closes, or time runs out.

        Parameters
        ----------
        github : GitHubClient
            Client used to read the PR status.
        request : AgenticLoopRequest
            The agentic loop request containing PR context and configuration.
        deadline : float
            Monotonic time at which the run's budget ends.
        new_head : str, optional
            Commit the agent created during the session, if any. Its checks
            are waited for even when GitHub still reports finished checks.

        Returns
        -------
        tuple[PRStatus, bool]
            The final status, and whether CI was still unresolved on the
            first poll (i.e. the agent stopped while waiting on CI).

        """
        register_deadline = time.monotonic() + CHECKS_REGISTER_GRACE_SECONDS
        waited = False
        new_head_running = False
        while True:
            try:
                status = await asyncio.to_thread(
                    github.get_pr_status, request.repo, request.pr_number
                )
            except Exception as e:
                log_warning(f"Failed to fetch PR status, retrying: {e}")
            else:
                now = time.monotonic()
                if new_head and status.head_sha == new_head and status.pending:
                    new_head_running = True
                # Right after a push, GitHub can report no checks, the previous
                # commit's checks, or only the checks that registered first.
                # None of those is a result for the pushed commit, so wait
                # until its CI is seen running or the grace period ends.
                awaiting_registration = now < register_deadline and (
                    not (status.pending or status.failed or status.passed)
                    or (new_head is not None and not new_head_running)
                )
                if (
                    status.state != "OPEN"
                    or not (status.pending or awaiting_registration)
                    or now >= deadline
                ):
                    return status, waited
                waited = True
                log_info(f"Waiting for CI: {status.summary()}")
            await asyncio.sleep(CI_POLL_SECONDS)

    @staticmethod
    def _goal_reached(request: AgenticLoopRequest, status: PRStatus) -> bool:
        """Return whether the PR is merged, or green when merging is disabled."""
        if request.merge_pr:
            return status.merged
        return status.merged or (status.state == "OPEN" and status.ci_passed)

    @staticmethod
    def _save_error(error_message: str) -> None:
        """Write the failure reason for the workflow's PR comment."""
        try:
            with open(ERROR_FILE, "w") as f:
                f.write(error_message)
        except OSError as e:
            log_error(f"Failed to save error reason: {e}")

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
