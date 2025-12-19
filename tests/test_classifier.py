"""Tests for the PR failure classifier."""

import json
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

    with patch(
        "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
    ) as mock_anthropic_class:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_response
        mock_anthropic_class.return_value = mock_client

        classifier = PRFailureClassifier(api_key="test-key")
        result = classifier.classify(pr_context, failed_checks, failure_logs)

        assert result.failure_type == FailureType.SECURITY
        assert result.confidence == 0.95
        assert "pip-audit" in result.reasoning.lower()
        assert len(result.failed_check_names) == 1
        assert result.failed_check_names[0] == "run-code-check"


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

    with patch(
        "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
    ) as mock_anthropic_class:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_response
        mock_anthropic_class.return_value = mock_client

        classifier = PRFailureClassifier(api_key="test-key")
        result = classifier.classify(pr_context, failed_checks, failure_logs)

        assert result.failure_type == FailureType.UNKNOWN
        assert result.confidence == 0.3


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

    with patch(
        "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
    ) as mock_anthropic_class:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_response
        mock_anthropic_class.return_value = mock_client

        classifier = PRFailureClassifier(api_key="test-key")
        result = classifier.classify(pr_context, failed_checks, failure_logs)

        # Should be downgraded to unknown due to low confidence
        assert result.failure_type == FailureType.UNKNOWN
        assert result.confidence == 0.5  # Original confidence preserved
        assert "below threshold" in result.reasoning.lower()


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

    with patch(
        "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
    ) as mock_anthropic_class:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_response
        mock_anthropic_class.return_value = mock_client

        classifier = PRFailureClassifier(api_key="test-key")
        result = classifier.classify(pr_context, failed_checks, "error logs")

        # Should fallback to unknown due to validation error
        assert result.failure_type == FailureType.UNKNOWN
        assert result.confidence == 0.0


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

    with patch(
        "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
    ) as mock_anthropic_class:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_response
        mock_anthropic_class.return_value = mock_client

        classifier = PRFailureClassifier(api_key="test-key")
        result = classifier.classify(pr_context, failed_checks, "error logs")

        # Should fallback to unknown due to invalid confidence
        assert result.failure_type == FailureType.UNKNOWN
        assert result.confidence == 0.0
