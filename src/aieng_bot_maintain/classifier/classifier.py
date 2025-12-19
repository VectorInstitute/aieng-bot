"""PR failure classifier using Claude AI."""

import json
import os
from dataclasses import asdict

import anthropic

from ..utils.logging import log_error, log_warning
from .models import (
    CheckFailure,
    ClassificationResult,
    FailureType,
    PRContext,
)
from .prompts import CLASSIFICATION_PROMPT


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

    def classify(
        self,
        pr_context: PRContext,
        failed_checks: list[CheckFailure],
        failure_logs: str,
    ) -> ClassificationResult:
        """Classify the type of PR failure using Claude API.

        Parameters
        ----------
        pr_context : PRContext
            Context about the PR (repo, number, title, author).
        failed_checks : list[CheckFailure]
            List of failed CI checks.
        failure_logs : str
            Failure logs (grep-extracted, up to 5000 chars).

        Returns
        -------
        ClassificationResult
            Classification with failure type, confidence, and reasoning.

        """
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

        # Build prompt (take FIRST 5000 chars since grep extracts relevant errors to the beginning)
        # The workflow grep command extracts error lines first, then adds last 1000 lines
        # So the actual error messages are at the BEGINNING of the extracted logs
        log_sample = (
            failure_logs[:5000].strip()
            if len(failure_logs) > 5000
            else failure_logs.strip()
        )

        prompt = CLASSIFICATION_PROMPT.format(
            pr_context=pr_info.strip(),
            failed_checks=checks_info,
            failure_logs=log_sample,
        )

        # Call Claude API with Haiku 4.5 for cost-effective classification
        # Haiku 4.5: $1/$5 per million tokens (67% cheaper than Sonnet)
        # Matches Sonnet 4 performance on coding tasks
        try:
            log_warning(f"Calling Claude API with prompt length: {len(prompt)} chars")
            response = self.client.messages.create(
                model="claude-haiku-4-5",  # Haiku 4.5: fast, cheap, accurate
                max_tokens=512,  # Reduced - only need JSON response
                temperature=0.0,  # Deterministic for classification
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract JSON from response (handle union type)
            first_block = response.content[0]
            if hasattr(first_block, "text"):
                response_text = first_block.text.strip()
                log_warning(f"Claude response: {response_text[:500]}")
            else:
                raise ValueError(
                    f"Expected TextBlock in response, got {type(first_block).__name__}"
                )

            # Try to parse JSON (handle markdown code blocks if present)
            if response_text.startswith("```"):
                # Extract JSON from markdown code block
                lines = response_text.split("\n")
                json_lines = []
                in_code_block = False
                for line in lines:
                    if line.startswith("```"):
                        in_code_block = not in_code_block
                        continue
                    if in_code_block:
                        json_lines.append(line)
                response_text = "\n".join(json_lines)

            result_data = json.loads(response_text)

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
                    f"Invalid confidence value: {confidence} "
                    f"(must be between 0.0 and 1.0)"
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
