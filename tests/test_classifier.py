"""Tests for the PR failure classifier."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aieng_bot_maintain import (
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
            "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
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
            "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
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
            "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
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
            "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
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
            "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
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
            "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
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
    import anthropic
    import httpx

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
            "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
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
            "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
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
    from aieng_bot_maintain import ClassificationResult

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
    from aieng_bot_maintain import ClassificationResult

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
