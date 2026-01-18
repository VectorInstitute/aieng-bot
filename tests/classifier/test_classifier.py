"""Tests for the PR failure classifier."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aieng_bot import (
    CheckFailure,
    FailureType,
    PRContext,
    PRFailureClassifier,
)


@pytest.fixture
def mock_anthropic_response():
    """Mock Anthropic API response."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps(
        {
            "failure_type": "security",
            "confidence": 0.95,
            "reasoning": "pip-audit found CVE in filelock package",
            "recommended_action": "Update filelock to 3.20.1",
        }
    )
    # Mock for tool use - no tool_use blocks
    mock_content.type = "text"
    mock_response.content = [mock_content]
    return mock_response


def test_classify_security_failure(mock_anthropic_response):
    """Test classification of security vulnerability."""
    pr_context = PRContext(
        repo="VectorInstitute/test-repo",
        pr_number=42,
        pr_title="Bump dependency",
        pr_author="app/dependabot",
        base_ref="main",
        head_ref="dependabot/bump-version",
    )

    failed_checks = [
        CheckFailure(
            name="run-code-check",
            conclusion="FAILURE",
            workflow_name="code checks",
            details_url="https://github.com/...",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
        )
    ]

    failure_logs = """
Found 1 known vulnerability in 1 package
filelock | 3.20.0 | GHSA-w853-jp5j-5j7f | 3.20.1
"""

    # Create temp file with logs
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write(failure_logs)
        failure_logs_file = f.name

    try:
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_anthropic_response
            mock_anthropic_class.return_value = mock_client

            classifier = PRFailureClassifier(api_key="test-key")
            result = classifier.classify(pr_context, failed_checks, failure_logs_file)

            assert result.failure_type == FailureType.SECURITY
            assert result.confidence == 0.95
            assert "pip-audit" in result.reasoning.lower()
            assert len(result.failed_check_names) == 1
            assert result.failed_check_names[0] == "run-code-check"
    finally:
        Path(failure_logs_file).unlink(missing_ok=True)


def test_classify_unknown_failure(mock_anthropic_response):
    """Test classification when type cannot be determined."""
    mock_content = MagicMock()
    mock_content.text = json.dumps(
        {
            "failure_type": "unknown",
            "confidence": 0.3,
            "reasoning": "Insufficient information in logs",
            "recommended_action": "Manual investigation required",
        }
    )
    mock_content.type = "text"
    mock_anthropic_response.content = [mock_content]

    pr_context = PRContext(
        repo="VectorInstitute/test-repo",
        pr_number=42,
        pr_title="Update deps",
        pr_author="app/dependabot",
        base_ref="main",
        head_ref="update-branch",
    )

    failed_checks = [
        CheckFailure(
            name="CI",
            conclusion="FAILURE",
            workflow_name="CI",
            details_url="https://github.com/...",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
        )
    ]

    failure_logs = "Process completed with exit code 1"

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write(failure_logs)
        failure_logs_file = f.name

    try:
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_anthropic_response
            mock_anthropic_class.return_value = mock_client

            classifier = PRFailureClassifier(api_key="test-key")
            result = classifier.classify(pr_context, failed_checks, failure_logs_file)

            assert result.failure_type == FailureType.UNKNOWN
            assert result.confidence == 0.3
    finally:
        Path(failure_logs_file).unlink(missing_ok=True)


def test_classify_missing_file():
    """Test classification when log file doesn't exist."""
    pr_context = PRContext(
        repo="VectorInstitute/test-repo",
        pr_number=42,
        pr_title="Test",
        pr_author="app/dependabot",
        base_ref="main",
        head_ref="test",
    )

    failed_checks = [
        CheckFailure(
            name="test",
            conclusion="FAILURE",
            workflow_name="CI",
            details_url="https://github.com/...",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
        )
    ]

    classifier = PRFailureClassifier(api_key="test-key")
    result = classifier.classify(pr_context, failed_checks, "/nonexistent/file.txt")

    assert result.failure_type == FailureType.UNKNOWN
    assert result.confidence == 0.0
    assert "not found" in result.reasoning.lower()


def test_failure_type_enum():
    """Test that all failure types are properly defined."""
    assert FailureType.MERGE_CONFLICT.value == "merge_conflict"
    assert FailureType.SECURITY.value == "security"
    assert FailureType.LINT.value == "lint"
    assert FailureType.TEST.value == "test"
    assert FailureType.BUILD.value == "build"
    assert FailureType.UNKNOWN.value == "unknown"


def test_classifier_requires_api_key():
    """Test that classifier requires ANTHROPIC_API_KEY."""
    with (
        patch.dict("os.environ", {}, clear=True),
        pytest.raises(ValueError, match="ANTHROPIC_API_KEY"),
    ):
        PRFailureClassifier()


def test_confidence_threshold_enforcement(mock_anthropic_response):
    """Test that low confidence classifications are rejected."""
    # Configure mock for low confidence security classification
    mock_content = MagicMock()
    mock_content.text = json.dumps(
        {
            "failure_type": "security",
            "confidence": 0.5,  # Below 0.7 threshold
            "reasoning": "Might be security but unsure",
            "recommended_action": "Investigate further",
        }
    )
    mock_content.type = "text"
    mock_anthropic_response.content = [mock_content]

    pr_context = PRContext(
        repo="VectorInstitute/test-repo",
        pr_number=42,
        pr_title="Update deps",
        pr_author="app/dependabot",
        base_ref="main",
        head_ref="update-branch",
    )

    failed_checks = [
        CheckFailure(
            name="security-check",
            conclusion="FAILURE",
            workflow_name="Security",
            details_url="https://github.com/...",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
        )
    ]

    failure_logs = "Some security error"

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write(failure_logs)
        failure_logs_file = f.name

    try:
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_anthropic_response
            mock_anthropic_class.return_value = mock_client

            classifier = PRFailureClassifier(api_key="test-key")
            result = classifier.classify(pr_context, failed_checks, failure_logs_file)

            # Should be downgraded to unknown due to low confidence
            assert result.failure_type == FailureType.UNKNOWN
            assert result.confidence == 0.5  # Original confidence preserved
            assert "below threshold" in result.reasoning.lower()
    finally:
        Path(failure_logs_file).unlink(missing_ok=True)


def test_response_validation_missing_fields(mock_anthropic_response):
    """Test that missing required fields are detected."""
    mock_content = MagicMock()
    mock_content.text = json.dumps(
        {
            "failure_type": "security",
            "confidence": 0.95,
            # Missing reasoning and recommended_action
        }
    )
    mock_content.type = "text"
    mock_anthropic_response.content = [mock_content]

    pr_context = PRContext(
        repo="VectorInstitute/test-repo",
        pr_number=42,
        pr_title="Test PR",
        pr_author="app/dependabot",
        base_ref="main",
        head_ref="test-branch",
    )

    failed_checks = [
        CheckFailure(
            name="test-check",
            conclusion="FAILURE",
            workflow_name="CI",
            details_url="https://github.com/...",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
        )
    ]

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("error logs")
        failure_logs_file = f.name

    try:
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_anthropic_response
            mock_anthropic_class.return_value = mock_client

            classifier = PRFailureClassifier(api_key="test-key")
            result = classifier.classify(pr_context, failed_checks, failure_logs_file)

            # Should fallback to unknown due to validation error
            assert result.failure_type == FailureType.UNKNOWN
            assert result.confidence == 0.0
    finally:
        Path(failure_logs_file).unlink(missing_ok=True)


def test_invalid_confidence_value(mock_anthropic_response):
    """Test that invalid confidence values are detected."""
    mock_content = MagicMock()
    mock_content.text = json.dumps(
        {
            "failure_type": "test",
            "confidence": 1.5,  # Invalid: > 1.0
            "reasoning": "Test failed",
            "recommended_action": "Fix test",
        }
    )
    mock_content.type = "text"
    mock_anthropic_response.content = [mock_content]

    pr_context = PRContext(
        repo="VectorInstitute/test-repo",
        pr_number=42,
        pr_title="Test PR",
        pr_author="app/dependabot",
        base_ref="main",
        head_ref="test-branch",
    )

    failed_checks = [
        CheckFailure(
            name="test-check",
            conclusion="FAILURE",
            workflow_name="CI",
            details_url="https://github.com/...",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
        )
    ]

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("error logs")
        failure_logs_file = f.name

    try:
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_anthropic_response
            mock_anthropic_class.return_value = mock_client

            classifier = PRFailureClassifier(api_key="test-key")
            result = classifier.classify(pr_context, failed_checks, failure_logs_file)

            # Should fallback to unknown due to invalid confidence
            assert result.failure_type == FailureType.UNKNOWN
            assert result.confidence == 0.0
    finally:
        Path(failure_logs_file).unlink(missing_ok=True)


def test_classify_with_markdown_code_block():
    """Test classification when response is wrapped in markdown code block."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = """```json
{
    "failure_type": "lint",
    "confidence": 0.92,
    "reasoning": "ESLint found style violations",
    "recommended_action": "Run eslint --fix"
}
```"""
    mock_content.type = "text"
    mock_response.content = [mock_content]

    pr_context = PRContext(
        repo="VectorInstitute/test-repo",
        pr_number=42,
        pr_title="Update code",
        pr_author="app/dependabot",
        base_ref="main",
        head_ref="lint-fix",
    )

    failed_checks = [
        CheckFailure(
            name="lint-check",
            conclusion="FAILURE",
            workflow_name="CI",
            details_url="https://github.com/...",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
        )
    ]

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("eslint errors")
        failure_logs_file = f.name

    try:
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic_class.return_value = mock_client

            classifier = PRFailureClassifier(api_key="test-key")
            result = classifier.classify(pr_context, failed_checks, failure_logs_file)

            assert result.failure_type == FailureType.LINT
            assert result.confidence == 0.92
            assert "ESLint" in result.reasoning
    finally:
        Path(failure_logs_file).unlink(missing_ok=True)


def test_classify_api_error():
    """Test classification when API returns an error."""
    import anthropic  # noqa: PLC0415 - Import for exception handling in test
    import httpx  # noqa: PLC0415 - Import for exception handling in test

    pr_context = PRContext(
        repo="VectorInstitute/test-repo",
        pr_number=42,
        pr_title="Test PR",
        pr_author="app/dependabot",
        base_ref="main",
        head_ref="test-branch",
    )

    failed_checks = [
        CheckFailure(
            name="test-check",
            conclusion="FAILURE",
            workflow_name="CI",
            details_url="https://github.com/...",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
        )
    ]

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("error logs")
        failure_logs_file = f.name

    try:
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            # Create a mock request for APIError
            mock_request = httpx.Request(
                "POST", "https://api.anthropic.com/v1/messages"
            )
            api_error = anthropic.APIError("API Error", request=mock_request, body=None)

            mock_client = MagicMock()
            mock_client.messages.create.side_effect = api_error
            mock_anthropic_class.return_value = mock_client

            classifier = PRFailureClassifier(api_key="test-key")
            result = classifier.classify(pr_context, failed_checks, failure_logs_file)

            # Should fallback to unknown with API error reasoning
            assert result.failure_type == FailureType.UNKNOWN
            assert result.confidence == 0.0
            assert "API error" in result.reasoning
    finally:
        Path(failure_logs_file).unlink(missing_ok=True)


def test_classify_invalid_json():
    """Test classification when API returns invalid JSON."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = "This is not valid JSON {invalid"
    mock_content.type = "text"
    mock_response.content = [mock_content]

    pr_context = PRContext(
        repo="VectorInstitute/test-repo",
        pr_number=42,
        pr_title="Test PR",
        pr_author="app/dependabot",
        base_ref="main",
        head_ref="test-branch",
    )

    failed_checks = [
        CheckFailure(
            name="test-check",
            conclusion="FAILURE",
            workflow_name="CI",
            details_url="https://github.com/...",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
        )
    ]

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("error logs")
        failure_logs_file = f.name

    try:
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic_class.return_value = mock_client

            classifier = PRFailureClassifier(api_key="test-key")
            result = classifier.classify(pr_context, failed_checks, failure_logs_file)

            # Should fallback to unknown with parse error
            assert result.failure_type == FailureType.UNKNOWN
            assert result.confidence == 0.0
            assert "Parse error" in result.reasoning
    finally:
        Path(failure_logs_file).unlink(missing_ok=True)


# Tests for ClassificationResult validation


def test_classification_result_invalid_confidence():
    """Test that ClassificationResult validates confidence range."""
    from aieng_bot import (  # noqa: PLC0415 - Import after test setup
        ClassificationResult,
    )

    # Test confidence > 1.0
    with pytest.raises(ValueError, match="Confidence must be between 0.0 and 1.0"):
        ClassificationResult(
            failure_type=FailureType.TEST,
            confidence=1.5,
            reasoning="Test",
            failed_check_names=["check1"],
            recommended_action="Fix it",
        )

    # Test confidence < 0.0
    with pytest.raises(ValueError, match="Confidence must be between 0.0 and 1.0"):
        ClassificationResult(
            failure_type=FailureType.TEST,
            confidence=-0.5,
            reasoning="Test",
            failed_check_names=["check1"],
            recommended_action="Fix it",
        )


def test_classification_result_valid_confidence():
    """Test that ClassificationResult accepts valid confidence values."""
    from aieng_bot import (  # noqa: PLC0415 - Import after test setup
        ClassificationResult,
    )

    # Test valid values at boundaries and middle
    valid_confidences = [0.0, 0.5, 1.0]
    for conf in valid_confidences:
        result = ClassificationResult(
            failure_type=FailureType.TEST,
            confidence=conf,
            reasoning="Test",
            failed_check_names=["check1"],
            recommended_action="Fix it",
        )
        assert result.confidence == conf


class TestExecuteToolUse:
    """Tests for _execute_tool_use method."""

    def test_execute_tool_use_success(self):
        """Test successful command execution."""
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_anthropic_class.return_value = MagicMock()
            classifier = PRFailureClassifier(api_key="test-key")

            # Create mock tool_use object
            tool_use = MagicMock()
            tool_use.id = "tool_123"
            tool_use.input = {"command": "echo hello"}

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="hello\n", stderr=""
                )

                result = classifier._execute_tool_use(tool_use)

                assert result["type"] == "tool_result"
                assert result["tool_use_id"] == "tool_123"
                assert "hello" in result["content"]

    def test_execute_tool_use_command_failure(self):
        """Test command execution that returns non-zero exit code."""
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_anthropic_class.return_value = MagicMock()
            classifier = PRFailureClassifier(api_key="test-key")

            tool_use = MagicMock()
            tool_use.id = "tool_456"
            tool_use.input = {"command": "false"}

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1, stdout="", stderr="command failed"
                )

                result = classifier._execute_tool_use(tool_use)

                assert result["type"] == "tool_result"
                assert result["tool_use_id"] == "tool_456"
                assert "command failed" in result["content"]

    def test_execute_tool_use_exception(self):
        """Test command execution that raises an exception."""
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_anthropic_class.return_value = MagicMock()
            classifier = PRFailureClassifier(api_key="test-key")

            tool_use = MagicMock()
            tool_use.id = "tool_789"
            tool_use.input = {"command": "some_command"}

            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = TimeoutError("Command timed out")

                result = classifier._execute_tool_use(tool_use)

                assert result["type"] == "tool_result"
                assert result["tool_use_id"] == "tool_789"
                assert "is_error" in result
                assert result["is_error"] is True
                assert "timed out" in result["content"]

    def test_execute_tool_use_invalid_input_format(self):
        """Test command execution with invalid input format."""
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_anthropic_class.return_value = MagicMock()
            classifier = PRFailureClassifier(api_key="test-key")

            tool_use = MagicMock()
            tool_use.id = "tool_invalid"
            tool_use.input = "not a dict"  # Invalid format

            result = classifier._execute_tool_use(tool_use)

            assert result["is_error"] is True
            assert "Invalid tool_use input format" in result["content"]

    def test_execute_tool_use_truncates_long_output(self):
        """Test that long command output is truncated."""
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_anthropic_class.return_value = MagicMock()
            classifier = PRFailureClassifier(api_key="test-key")

            tool_use = MagicMock()
            tool_use.id = "tool_long"
            tool_use.input = {"command": "cat big_file"}

            with patch("subprocess.run") as mock_run:
                # Generate output longer than 10000 chars
                long_output = "x" * 15000
                mock_run.return_value = MagicMock(
                    returncode=0, stdout=long_output, stderr=""
                )

                result = classifier._execute_tool_use(tool_use)

                assert len(result["content"]) == 10000


class TestParseJsonResponse:
    """Tests for _parse_json_response method."""

    def test_parse_embedded_json_in_text(self):
        """Test parsing JSON embedded in explanatory text (Strategy 3)."""
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_anthropic_class.return_value = MagicMock()
            classifier = PRFailureClassifier(api_key="test-key")

            response_text = """Based on my analysis, here is the classification:
            {"failure_type": "test", "confidence": 0.85, "reasoning": "pytest failed", "recommended_action": "fix test"}
            That's my assessment."""

            result = classifier._parse_json_response(response_text)

            assert result["failure_type"] == "test"
            assert result["confidence"] == 0.85

    def test_parse_incomplete_json_with_missing_braces(self):
        """Test parsing incomplete JSON with missing closing braces (Strategy 4)."""
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_anthropic_class.return_value = MagicMock()
            classifier = PRFailureClassifier(api_key="test-key")

            # JSON missing one closing brace
            response_text = '{"failure_type": "lint", "confidence": 0.9, "reasoning": "eslint error", "recommended_action": "run fix"'

            result = classifier._parse_json_response(response_text)

            assert result["failure_type"] == "lint"
            assert result["confidence"] == 0.9

    def test_parse_completely_invalid_json(self):
        """Test that completely invalid JSON raises JSONDecodeError."""
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_anthropic_class.return_value = MagicMock()
            classifier = PRFailureClassifier(api_key="test-key")

            response_text = "This has no JSON at all, just plain text"

            with pytest.raises(json.JSONDecodeError):
                classifier._parse_json_response(response_text)


class TestRunAgenticLoop:
    """Tests for _run_agentic_loop method."""

    def test_agentic_loop_with_tool_use(self):
        """Test agentic loop that executes tool uses."""
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_client = MagicMock()
            mock_anthropic_class.return_value = mock_client

            # First response: tool use
            tool_use_block = MagicMock()
            tool_use_block.type = "tool_use"
            tool_use_block.id = "tool_1"
            tool_use_block.name = "bash"
            tool_use_block.input = {"command": "grep error logs.txt"}

            first_response = MagicMock()
            first_response.content = [tool_use_block]

            # Second response: final text
            text_block = MagicMock()
            text_block.type = "text"
            text_block.text = '{"failure_type": "test", "confidence": 0.9, "reasoning": "test", "recommended_action": "fix"}'

            second_response = MagicMock()
            second_response.content = [text_block]
            second_response.stop_reason = "end_turn"

            mock_client.messages.create.side_effect = [first_response, second_response]

            classifier = PRFailureClassifier(api_key="test-key")

            with patch.object(classifier, "_execute_tool_use") as mock_execute:
                mock_execute.return_value = {
                    "type": "tool_result",
                    "tool_use_id": "tool_1",
                    "content": "Error: test failed",
                }

                messages = [{"role": "user", "content": "classify this"}]  # type: ignore[list-item]
                bash_tool = {"type": "bash_20250124", "name": "bash"}  # type: ignore[assignment]

                result = classifier._run_agentic_loop(messages, bash_tool)

                assert "failure_type" in result
                mock_execute.assert_called_once()

    def test_agentic_loop_max_turns_exceeded(self):
        """Test that agentic loop raises error when max turns exceeded."""
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_client = MagicMock()
            mock_anthropic_class.return_value = mock_client

            # Always return tool use (never stops)
            tool_use_block = MagicMock()
            tool_use_block.type = "tool_use"
            tool_use_block.id = "tool_endless"
            tool_use_block.name = "bash"
            tool_use_block.input = {"command": "echo loop"}

            response = MagicMock()
            response.content = [tool_use_block]

            mock_client.messages.create.return_value = response

            classifier = PRFailureClassifier(api_key="test-key")

            with patch.object(classifier, "_execute_tool_use") as mock_execute:
                mock_execute.return_value = {
                    "type": "tool_result",
                    "tool_use_id": "tool_endless",
                    "content": "output",
                }

                messages = [{"role": "user", "content": "classify"}]  # type: ignore[list-item]
                bash_tool = {"type": "bash_20250124", "name": "bash"}  # type: ignore[assignment]

                with pytest.raises(ValueError, match="Max tool use turns"):
                    classifier._run_agentic_loop(messages, bash_tool)

    def test_agentic_loop_max_tokens_warning(self):
        """Test that max_tokens truncation triggers a warning."""
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_client = MagicMock()
            mock_anthropic_class.return_value = mock_client

            text_block = MagicMock()
            text_block.type = "text"
            text_block.text = '{"failure_type": "build", "confidence": 0.8, "reasoning": "build failed", "recommended_action": "fix"}'

            response = MagicMock()
            response.content = [text_block]
            response.stop_reason = "max_tokens"  # Truncated

            mock_client.messages.create.return_value = response

            classifier = PRFailureClassifier(api_key="test-key")

            messages = [{"role": "user", "content": "classify"}]  # type: ignore[list-item]
            bash_tool = {"type": "bash_20250124", "name": "bash"}  # type: ignore[assignment]

            # Should still return result but log warning
            result = classifier._run_agentic_loop(messages, bash_tool)

            assert "failure_type" in result

    def test_agentic_loop_no_text_content_error(self):
        """Test that empty response raises an error."""
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_client = MagicMock()
            mock_anthropic_class.return_value = mock_client

            # Response with no text blocks
            response = MagicMock()
            response.content = []

            mock_client.messages.create.return_value = response

            classifier = PRFailureClassifier(api_key="test-key")

            messages = [{"role": "user", "content": "classify"}]  # type: ignore[list-item]
            bash_tool = {"type": "bash_20250124", "name": "bash"}  # type: ignore[assignment]

            with pytest.raises(ValueError, match="No text content"):
                classifier._run_agentic_loop(messages, bash_tool)


class TestValidateAndBuildResult:
    """Tests for _validate_and_build_result method."""

    def test_invalid_failure_type(self):
        """Test that invalid failure type raises ValueError."""
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_anthropic_class.return_value = MagicMock()
            classifier = PRFailureClassifier(api_key="test-key")

            result_data = {
                "failure_type": "invalid_type",  # Not a valid FailureType
                "confidence": 0.9,
                "reasoning": "test",
                "recommended_action": "fix",
            }

            failed_checks = [
                CheckFailure(
                    name="test",
                    conclusion="FAILURE",
                    workflow_name="CI",
                    details_url="https://github.com/...",
                    started_at="2025-01-01T00:00:00Z",
                    completed_at="2025-01-01T00:05:00Z",
                )
            ]

            with pytest.raises(ValueError, match="Invalid failure_type"):
                classifier._validate_and_build_result(result_data, failed_checks)

    def test_negative_confidence(self):
        """Test that negative confidence raises ValueError."""
        with patch(
            "aieng_bot.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_anthropic_class.return_value = MagicMock()
            classifier = PRFailureClassifier(api_key="test-key")

            result_data = {
                "failure_type": "test",
                "confidence": -0.5,  # Invalid negative
                "reasoning": "test",
                "recommended_action": "fix",
            }

            failed_checks = []

            with pytest.raises(ValueError, match="Invalid confidence value"):
                classifier._validate_and_build_result(result_data, failed_checks)
