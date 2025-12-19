"""Tests for the PR failure classifier."""

import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.classify_pr_failure import (
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

    with patch.object(PRFailureClassifier, "client") as mock_client:
        mock_client.messages.create.return_value = mock_anthropic_response

        classifier = PRFailureClassifier(api_key="test-key")
        classifier.client = mock_client

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

    with patch.object(PRFailureClassifier, "client") as mock_client:
        mock_client.messages.create.return_value = mock_anthropic_response

        classifier = PRFailureClassifier(api_key="test-key")
        classifier.client = mock_client

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
