#!/usr/bin/env python3
"""Intelligent PR failure classifier using Claude API.

This script analyzes PR check failures and classifies them into categories
by examining the actual failure logs and context, not just pattern matching.
"""

import json
import os
import sys
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Optional

import anthropic


class FailureType(str, Enum):
    """Supported failure types that the bot can fix."""

    MERGE_CONFLICT = "merge_conflict"
    LINT = "lint"
    SECURITY = "security"
    TEST = "test"
    BUILD = "build"
    UNKNOWN = "unknown"


@dataclass
class CheckFailure:
    """Represents a failed CI check."""

    name: str
    conclusion: str
    workflow_name: str
    details_url: str
    started_at: str
    completed_at: str


@dataclass
class PRContext:
    """Context about the PR being analyzed."""

    repo: str
    pr_number: int
    pr_title: str
    pr_author: str
    base_ref: str
    head_ref: str


@dataclass
class ClassificationResult:
    """Result of failure classification."""

    failure_type: FailureType
    confidence: float  # 0.0 to 1.0
    reasoning: str
    failed_check_names: list[str]
    recommended_action: str


class PRFailureClassifier:
    """Classifies PR failures using Claude API."""

    CLASSIFICATION_PROMPT = """You are an expert at analyzing CI/CD failures in GitHub pull requests. Your task is to classify the type of failure based on the provided information.

## Available Failure Categories

1. **merge_conflict**: Git merge conflicts that need manual resolution
2. **security**: Security vulnerabilities (pip-audit, npm audit, Snyk, CVEs)
3. **lint**: Linting/formatting issues (ESLint, Black, Prettier, Ruff, pre-commit hooks)
4. **test**: Test failures (Jest, pytest, unittest, integration tests)
5. **build**: Build/compilation errors (TypeScript, webpack, tsc, compilation)
6. **unknown**: Cannot be confidently classified into above categories

## Your Analysis Process

1. **Examine check names** for hints about what they do
2. **Read failure logs carefully** to identify the actual error
3. **Look for key indicators**:
   - Security: CVE numbers, vulnerability reports, audit tool output
   - Lint: Formatting violations, style rules, code quality checks
   - Test: Test assertion failures, test suite output, spec failures
   - Build: Compilation errors, module resolution, TypeScript errors
   - Merge: Conflict markers, unmerged paths

4. **Consider the PR context**: What is being updated? (dependencies, code, config)

## Output Format

Return ONLY a valid JSON object with this exact structure:
{{
  "failure_type": "security|lint|test|build|merge_conflict|unknown",
  "confidence": 0.95,
  "reasoning": "Brief explanation of why you chose this classification",
  "recommended_action": "Specific next step the bot should take"
}}

## Example Classifications

**Example 1: Security**
Check: "run-code-check"
Log: "Found 1 known vulnerability in 1 package\\nfilelock | 3.20.0 | GHSA-w853-jp5j-5j7f"
→ Classification: security (confidence: 0.98) - pip-audit found CVE

**Example 2: Test**
Check: "unit-tests"
Log: "AssertionError: Expected 5 but got 3\\n  at test_calculation (test.py:42)"
→ Classification: test (confidence: 1.0) - Test assertion failure

**Example 3: Lint**
Check: "pre-commit"
Log: "Black formatting check failed: 3 files would be reformatted"
→ Classification: lint (confidence: 0.95) - Auto-fixable formatting

**Example 4: Ambiguous**
Check: "CI"
Log: "Process completed with exit code 1"
→ Classification: unknown (confidence: 0.3) - Insufficient information

---

# PR Details

{pr_context}

# Failed Checks

{failed_checks}

# Failure Logs (last 5000 lines)

{failure_logs}

---

Analyze the above information and return your classification as a JSON object."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize classifier with Anthropic API key."""
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

        Args:
            pr_context: Context about the PR
            failed_checks: List of failed checks
            failure_logs: Failure logs (last 5000 lines)

        Returns:
            ClassificationResult with classification and reasoning

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

        # Build prompt
        prompt = self.CLASSIFICATION_PROMPT.format(
            pr_context=pr_info.strip(),
            failed_checks=checks_info,
            failure_logs=failure_logs[:5000].strip(),  # Limit log size
        )

        # Call Claude API
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1024,
                temperature=0.0,  # Deterministic for classification
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract JSON from response (handle union type)
            first_block = response.content[0]
            if hasattr(first_block, "text"):
                response_text = first_block.text.strip()
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

            # Validate and construct result
            return ClassificationResult(
                failure_type=FailureType(result_data["failure_type"]),
                confidence=float(result_data["confidence"]),
                reasoning=result_data["reasoning"],
                failed_check_names=[check.name for check in failed_checks],
                recommended_action=result_data["recommended_action"],
            )

        except anthropic.APIError as e:
            print(f"Error calling Claude API: {e}", file=sys.stderr)
            # Fallback to unknown with low confidence
            return ClassificationResult(
                failure_type=FailureType.UNKNOWN,
                confidence=0.0,
                reasoning=f"API error: {str(e)}",
                failed_check_names=[check.name for check in failed_checks],
                recommended_action="Manual investigation required",
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Error parsing classification result: {e}", file=sys.stderr)
            print(f"Raw response: {response_text}", file=sys.stderr)
            return ClassificationResult(
                failure_type=FailureType.UNKNOWN,
                confidence=0.0,
                reasoning=f"Parse error: {str(e)}",
                failed_check_names=[check.name for check in failed_checks],
                recommended_action="Manual investigation required",
            )


def main() -> None:
    """CLI entry point for classification."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Classify PR failure type using Claude API"
    )
    parser.add_argument("--pr-info", required=True, help="PR info JSON string")
    parser.add_argument(
        "--failed-checks", required=True, help="Failed checks JSON array"
    )
    parser.add_argument(
        "--failure-logs", required=True, help="Failure logs (truncated)"
    )
    parser.add_argument(
        "--output-format",
        choices=["json", "github"],
        default="github",
        help="Output format",
    )

    args = parser.parse_args()

    # Parse inputs
    pr_data = json.loads(args.pr_info)
    checks_data = json.loads(args.failed_checks)

    pr_context = PRContext(
        repo=pr_data["repo"],
        pr_number=int(pr_data["pr_number"]),
        pr_title=pr_data["pr_title"],
        pr_author=pr_data["pr_author"],
        base_ref=pr_data["base_ref"],
        head_ref=pr_data["head_ref"],
    )

    failed_checks = [
        CheckFailure(
            name=check["name"],
            conclusion=check["conclusion"],
            workflow_name=check.get("workflowName", ""),
            details_url=check.get("detailsUrl", ""),
            started_at=check.get("startedAt", ""),
            completed_at=check.get("completedAt", ""),
        )
        for check in checks_data
    ]

    # Run classification
    classifier = PRFailureClassifier()
    result = classifier.classify(pr_context, failed_checks, args.failure_logs)

    # Output results
    if args.output_format == "json":
        print(json.dumps(asdict(result), indent=2))
    else:  # github format - output for GITHUB_OUTPUT
        print(f"failure-type={result.failure_type.value}")
        print(f"confidence={result.confidence}")
        print(f"reasoning={result.reasoning}")
        print(f"failed-check-names={','.join(result.failed_check_names)}")
        print(f"recommended-action={result.recommended_action}")


if __name__ == "__main__":
    main()
