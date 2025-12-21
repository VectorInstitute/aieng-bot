"""Agent fixer implementation using Claude Agent SDK."""

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
        """Apply fixes to a PR using the Claude Agent SDK.

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
        FileNotFoundError
            If prompt template or failure logs file not found.
        RuntimeError
            If agent execution fails.

        """
        log_info(
            f"Applying fixes for {request.repo}#{request.pr_number} "
            f"({request.failure_type} failure)"
        )

        try:
            # Load prompt template
            prompt_content = self._load_prompt_template(request)

            # Build final prompt with task instructions
            full_prompt = self._build_final_prompt(prompt_content)

            log_info("Starting Claude Agent SDK...")
            # Initialize tracer with environment variables
            tracer = self._create_tracer(request)

            # Configure agent options
            options = ClaudeAgentOptions(
                allowed_tools=["Read", "Edit", "Bash", "Glob", "Grep"],
                permission_mode="acceptEdits",
                cwd=request.cwd,
            )

            # Run agent with tracing
            agent_stream = query(prompt=full_prompt, options=options)
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

    def _load_prompt_template(self, request: AgentFixRequest) -> str:
        """Load and populate prompt template.

        Parameters
        ----------
        request : AgentFixRequest
            The fix request containing template substitution values.

        Returns
        -------
        str
            Populated prompt content.

        Raises
        ------
        FileNotFoundError
            If prompt template file not found.

        """
        prompt_path = Path(request.prompt_file)
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {request.prompt_file}")

        log_info(f"Loading prompt template: {request.prompt_file}")
        template_content = prompt_path.read_text()

        # Replace placeholders
        prompt_content = template_content.replace("{{REPO_NAME}}", request.repo)
        prompt_content = prompt_content.replace("{{PR_NUMBER}}", str(request.pr_number))
        prompt_content = prompt_content.replace("{{PR_TITLE}}", request.pr_title)
        prompt_content = prompt_content.replace("{{PR_AUTHOR}}", request.pr_author)
        prompt_content = prompt_content.replace(
            "{{FAILED_CHECK_NAME}}", request.failed_check_names
        )

        # Add failure logs reference
        if Path(request.failure_logs_file).exists():
            logs_reference = (
                f"The failure logs have been saved to {request.failure_logs_file} "
                f"in the repository root. Please read this file to understand the errors."
            )
            prompt_content = prompt_content.replace(
                "{{FAILURE_DETAILS}}", logs_reference
            )
        else:
            log_error(f"Failure logs file not found: {request.failure_logs_file}")
            prompt_content = prompt_content.replace(
                "{{FAILURE_DETAILS}}", "No failure logs available"
            )

        return prompt_content

    def _build_final_prompt(self, prompt_content: str) -> str:
        """Add task instructions to the prompt.

        Parameters
        ----------
        prompt_content : str
            The base prompt content.

        Returns
        -------
        str
            Final prompt with task instructions appended.

        """
        task_instructions = """

## Your Task
Analyze the failures and fix the code directly. Make minimal, targeted changes to resolve the issues.

Important:
- Read all relevant files first
- Apply fixes directly to the code
- Don't skip tests or add ignore comments
- Follow existing code patterns
- Make changes that will make the tests pass"""

        return prompt_content + task_instructions

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
