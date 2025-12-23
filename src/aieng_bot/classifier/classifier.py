"""PR failure classifier using Claude AI."""

import json
import os
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

import anthropic
from anthropic.types import (
    MessageParam,
    ToolBash20250124Param,
    ToolResultBlockParam,
)

from ..utils.logging import log_error, log_info, log_warning
from .models import (
    CheckFailure,
    ClassificationResult,
    FailureType,
    PRContext,
)
from .prompts import CLASSIFICATION_PROMPT_WITH_TOOLS


class PRFailureClassifier:
    """Classifies PR failures using Claude Haiku 4.5.

    This classifier uses Claude Haiku 4.5 for cost-effective classification
    while maintaining high accuracy (67% cost savings vs Sonnet 4).

    Attributes
    ----------
    MIN_CONFIDENCE : float
        Minimum confidence threshold (0.7). Classifications below this
        are treated as unknown.
    api_key : str
        Anthropic API key for authentication.
    client : anthropic.Anthropic
        Anthropic API client instance.

    """

    MIN_CONFIDENCE = 0.7  # Minimum confidence threshold

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize classifier with Anthropic API key.

        Parameters
        ----------
        api_key : str, optional
            Anthropic API key. If None, reads from ANTHROPIC_API_KEY
            environment variable.

        Raises
        ------
        ValueError
            If API key is not provided and not found in environment.

        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def _verify_log_file(
        self, failure_logs_file: str, failed_checks: list[CheckFailure]
    ) -> ClassificationResult | None:
        """Verify log file exists, return error result if not."""
        if not Path(failure_logs_file).exists():
            log_error(f"Failure logs file not found: {failure_logs_file}")
            return ClassificationResult(
                failure_type=FailureType.UNKNOWN,
                confidence=0.0,
                reasoning="Failure logs file not found",
                failed_check_names=[check.name for check in failed_checks],
                recommended_action="Manually investigate - no logs available",
            )
        return None

    def _execute_tool_use(self, tool_use: Any) -> dict[str, Any]:
        """Execute a single bash tool use and return the result."""
        try:
            # Get command from tool_use input (properly typed)
            command_input = tool_use.input
            if isinstance(command_input, dict) and "command" in command_input:
                command = str(command_input["command"])
            else:
                raise ValueError("Invalid tool_use input format")

            # Log the actual command being run
            log_info(f"  bash: {command[:200]}{'...' if len(command) > 200 else ''}")

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            output = result.stdout if result.returncode == 0 else result.stderr

            # Log output summary
            output_lines = output.split("\n") if output else []
            line_count = len(output_lines)
            log_info(f"  → output: {line_count} lines, exit code {result.returncode}")

            return {
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": output[:10000],  # Limit output size
            }
        except Exception as e:
            log_error(f"  → error executing command: {e}")
            return {
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": f"Error: {str(e)}",
                "is_error": True,
            }

    def _parse_json_response(self, response_text: str) -> dict[str, Any]:
        """Parse JSON response, handling markdown code blocks and embedded JSON."""
        # Strategy 1: Try direct parse (pure JSON response)
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # Strategy 2: Extract from markdown code block
        if "```" in response_text:
            lines = response_text.split("\n")
            json_lines = []
            in_code_block = False
            for line in lines:
                if line.startswith("```"):
                    in_code_block = not in_code_block
                    continue
                if in_code_block:
                    json_lines.append(line)

            if json_lines:
                try:
                    return json.loads("\n".join(json_lines))
                except json.JSONDecodeError:
                    pass

        # Strategy 3: Find JSON object in text (look for { ... })
        # Claude might return explanatory text followed by JSON
        start_idx = response_text.find("{")
        end_idx = response_text.rfind("}")

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            potential_json = response_text[start_idx : end_idx + 1]
            try:
                return json.loads(potential_json)
            except json.JSONDecodeError:
                pass

        # All strategies failed
        log_error(f"Failed to parse JSON from response (length: {len(response_text)})")
        log_error(f"Response preview: {response_text[:500]}")
        raise json.JSONDecodeError(
            "Could not extract valid JSON from Claude's response", response_text, 0
        )

    def _run_agentic_loop(
        self, messages: list[MessageParam], bash_tool: ToolBash20250124Param
    ) -> str:
        """Run the agentic loop for tool use and return final response text."""
        max_turns = 15  # Allow more turns for complex log analysis
        response_text = ""

        for turn in range(max_turns):
            response = self.client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=8192,
                temperature=0.0,
                tools=[bash_tool],
                messages=messages,
            )

            # Check if response has tool uses
            tool_uses = [
                block for block in response.content if block.type == "tool_use"
            ]

            if not tool_uses:
                # No more tool uses - extract final text
                for block in response.content:
                    if hasattr(block, "text"):
                        response_text += block.text

                if not response_text:
                    raise ValueError("No text content in final Claude response")

                response_text = response_text.strip()
                log_info(
                    f"Claude classification (turn {turn + 1}): {response_text[:500]}"
                )
                break

            # Build assistant message with response content blocks
            assistant_content: list[Any] = []
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )
            messages.append({"role": "assistant", "content": assistant_content})

            # Execute tool uses
            tool_result_blocks: list[ToolResultBlockParam] = []
            for tool_use in tool_uses:
                tool_result = self._execute_tool_use(tool_use)
                tool_result_blocks.append(tool_result)  # type: ignore[arg-type]

            messages.append({"role": "user", "content": tool_result_blocks})
        else:
            raise ValueError(f"Max tool use turns ({max_turns}) exceeded")

        return response_text

    def _validate_and_build_result(
        self, result_data: dict[str, Any], failed_checks: list[CheckFailure]
    ) -> ClassificationResult:
        """Validate result data and build ClassificationResult."""
        # Validate required fields
        required_fields = [
            "failure_type",
            "confidence",
            "reasoning",
            "recommended_action",
        ]
        missing_fields = [f for f in required_fields if f not in result_data]
        if missing_fields:
            raise ValueError(
                f"Response missing required fields: {', '.join(missing_fields)}"
            )

        # Extract and validate confidence
        confidence = float(result_data["confidence"])
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(
                f"Invalid confidence value: {confidence} (must be between 0.0 and 1.0)"
            )

        failure_type_str = result_data["failure_type"]

        # Validate failure type
        valid_types = [ft.value for ft in FailureType]
        if failure_type_str not in valid_types:
            raise ValueError(
                f"Invalid failure_type: {failure_type_str}. "
                f"Must be one of: {', '.join(valid_types)}"
            )

        # Apply confidence threshold - if too uncertain, treat as unknown
        if failure_type_str != "unknown" and confidence < self.MIN_CONFIDENCE:
            log_warning(
                f"Low confidence ({confidence:.2f}) "
                f"for classification '{failure_type_str}'. "
                f"Treating as unknown (threshold: {self.MIN_CONFIDENCE})"
            )
            failure_type_str = "unknown"
            result_data["reasoning"] += (
                f" [Note: Original classification had confidence {confidence:.2f}, "
                f"below threshold {self.MIN_CONFIDENCE}]"
            )

        # Validate and construct result
        return ClassificationResult(
            failure_type=FailureType(failure_type_str),
            confidence=confidence,
            reasoning=result_data["reasoning"],
            failed_check_names=[check.name for check in failed_checks],
            recommended_action=result_data["recommended_action"],
        )

    def classify(
        self,
        pr_context: PRContext,
        failed_checks: list[CheckFailure],
        failure_logs_file: str,
    ) -> ClassificationResult:
        """Classify the type of PR failure using Claude API with tools.

        Claude will use bash tool to search through the log file intelligently
        rather than having logs embedded in the prompt.

        Parameters
        ----------
        pr_context : PRContext
            Context about the PR (repo, number, title, author).
        failed_checks : list[CheckFailure]
            List of failed CI checks.
        failure_logs_file : str
            Path to the failure logs file.

        Returns
        -------
        ClassificationResult
            Classification with failure type, confidence, and reasoning.

        """
        # Verify log file exists
        error_result = self._verify_log_file(failure_logs_file, failed_checks)
        if error_result:
            return error_result
        # Format PR context
        pr_info = f"""
Repository: {pr_context.repo}
PR: #{pr_context.pr_number}
Title: {pr_context.pr_title}
Author: {pr_context.pr_author}
Branch: {pr_context.head_ref} → {pr_context.base_ref}
"""

        # Format failed checks
        checks_info = json.dumps([asdict(check) for check in failed_checks], indent=2)

        # Build prompt with file path (not embedded logs)
        prompt = CLASSIFICATION_PROMPT_WITH_TOOLS.format(
            pr_context=pr_info.strip(),
            failed_checks=checks_info,
            failure_logs_file=failure_logs_file,
        )

        # Call Claude API with tools to search log file
        # Using Haiku 4.5 for cost-effective classification with tools
        try:
            log_info(f"Calling Claude API with tools (log file: {failure_logs_file})")
            log_info(f"Prompt length: {len(prompt)} chars")

            # Run agentic loop
            messages: list[MessageParam] = [{"role": "user", "content": prompt}]
            bash_tool: ToolBash20250124Param = {
                "type": "bash_20250124",
                "name": "bash",
            }
            response_text = self._run_agentic_loop(messages, bash_tool)

            # Parse JSON response and validate
            result_data = self._parse_json_response(response_text)
            return self._validate_and_build_result(result_data, failed_checks)

        except anthropic.APIError as e:
            log_error(f"Error calling Claude API: {e}")
            # Fallback to unknown with low confidence
            return ClassificationResult(
                failure_type=FailureType.UNKNOWN,
                confidence=0.0,
                reasoning=f"API error: {str(e)}",
                failed_check_names=[check.name for check in failed_checks],
                recommended_action="Manual investigation required",
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            log_error(f"Error parsing classification result: {e}")
            return ClassificationResult(
                failure_type=FailureType.UNKNOWN,
                confidence=0.0,
                reasoning=f"Parse error: {str(e)}",
                failed_check_names=[check.name for check in failed_checks],
                recommended_action="Manual investigation required",
            )
