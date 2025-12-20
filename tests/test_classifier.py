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


# Tests for _extract_relevant_logs method


def test_extract_relevant_logs_short_logs():
    """Test log extraction when logs are shorter than max_chars."""
    classifier = PRFailureClassifier(api_key="test-key")
    short_logs = "Error: something went wrong\nLine 2\nLine 3"

    result = classifier._extract_relevant_logs(short_logs, max_chars=5000)

    assert result == short_logs.strip()


def test_extract_relevant_logs_security_patterns():
    """Test that security patterns (CVE, GHSA) are prioritized."""
    classifier = PRFailureClassifier(api_key="test-key")
    logs = "\n".join(
        [f"Line {i}: regular log line" for i in range(100)]
        + [
            "Line 100: Found vulnerability GHSA-1234-5678-abcd in package",
            "Line 101: CVE-2024-12345 affects version 1.0.0",
            "Line 102: vulnerability detected in dependency",
        ]
        + [f"Line {i}: more regular lines" for i in range(103, 200)]
    )

    result = classifier._extract_relevant_logs(logs, max_chars=500)

    # Should prioritize security-related lines
    assert "GHSA-1234-5678-abcd" in result
    assert "CVE-2024-12345" in result
    assert "vulnerability" in result


def test_extract_relevant_logs_error_patterns():
    """Test that error patterns are extracted when no security issues."""
    classifier = PRFailureClassifier(api_key="test-key")
    logs = "\n".join(
        [f"Line {i}: regular log line" for i in range(100)]
        + [
            "Line 100: ERROR: Test failed",
            "Line 101: Exception: Something went wrong",
            "Line 102: Traceback (most recent call last):",
            "Line 103: AssertionError: expected 5 got 3",
        ]
        + [f"Line {i}: more regular lines" for i in range(104, 200)]
    )

    result = classifier._extract_relevant_logs(logs, max_chars=500)

    # Should prioritize error-related lines
    assert "ERROR: Test failed" in result
    assert "Exception: Something went wrong" in result
    assert "Traceback" in result
    assert "AssertionError" in result


def test_extract_relevant_logs_middle_section_fallback():
    """Test that middle section is used when no clear patterns found."""
    classifier = PRFailureClassifier(api_key="test-key")
    # Create logs with no security or error patterns
    logs = "\n".join([f"Line {i}: regular output" for i in range(200)])

    result = classifier._extract_relevant_logs(logs, max_chars=500)

    # Should extract from middle section (skip first 20% and last 20%)
    # Line 40 to Line 160 is the middle section
    assert "Line 40" in result or "Line 50" in result
    assert "Line 0" not in result  # First 20% should be skipped
    assert "Line 190" not in result  # Last 20% should be skipped


def test_extract_relevant_logs_respects_max_chars():
    """Test that extraction respects max_chars limit."""
    classifier = PRFailureClassifier(api_key="test-key")
    long_logs = "\n".join([f"Line {i}: " + "x" * 100 for i in range(1000)])

    result = classifier._extract_relevant_logs(long_logs, max_chars=1000)

    assert len(result) <= 1000


# Tests for _extract_with_context method


def test_extract_with_context_basic():
    """Test extraction with context around relevant lines."""
    classifier = PRFailureClassifier(api_key="test-key")
    lines = [f"Line {i}" for i in range(100)]
    relevant_indices = [50]  # One relevant line in the middle

    result = classifier._extract_with_context(lines, relevant_indices, max_chars=5000)

    # Should include 5 lines before and after (line 45-56)
    assert "Line 45" in result
    assert "Line 50" in result
    assert "Line 55" in result
    assert "Line 44" not in result
    assert "Line 56" not in result


def test_extract_with_context_multiple_indices():
    """Test extraction with multiple relevant line indices."""
    classifier = PRFailureClassifier(api_key="test-key")
    lines = [f"Line {i}" for i in range(100)]
    relevant_indices = [10, 50, 90]  # Multiple relevant lines

    result = classifier._extract_with_context(lines, relevant_indices, max_chars=5000)

    # Should include context around all three relevant lines
    assert "Line 10" in result
    assert "Line 50" in result
    assert "Line 90" in result


def test_extract_with_context_exceeds_max_chars():
    """Test that exceeding max_chars prioritizes relevant lines."""
    classifier = PRFailureClassifier(api_key="test-key")
    lines = [f"Line {i}: " + "x" * 100 for i in range(100)]
    relevant_indices = [10, 50, 90]

    result = classifier._extract_with_context(lines, relevant_indices, max_chars=500)

    # Should prioritize the relevant lines themselves
    assert len(result) <= 500
    # At least one relevant line should be present
    assert any(f"Line {idx}" in result for idx in relevant_indices)


def test_extract_with_context_boundary_conditions():
    """Test context extraction at list boundaries."""
    classifier = PRFailureClassifier(api_key="test-key")
    lines = [f"Line {i}" for i in range(20)]
    relevant_indices = [0, 19]  # First and last lines

    result = classifier._extract_with_context(lines, relevant_indices, max_chars=5000)

    # Should include lines without going out of bounds
    assert "Line 0" in result
    assert "Line 19" in result


# Tests for classify method edge cases


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

    with patch(
        "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
    ) as mock_anthropic_class:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        classifier = PRFailureClassifier(api_key="test-key")
        result = classifier.classify(pr_context, failed_checks, "eslint errors")

        assert result.failure_type == FailureType.LINT
        assert result.confidence == 0.92
        assert "ESLint" in result.reasoning


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

    with patch(
        "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
    ) as mock_anthropic_class:
        # Create a mock request for APIError
        mock_request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        api_error = anthropic.APIError("API Error", request=mock_request, body=None)

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = api_error
        mock_anthropic_class.return_value = mock_client

        classifier = PRFailureClassifier(api_key="test-key")
        result = classifier.classify(pr_context, failed_checks, "error logs")

        # Should fallback to unknown with API error reasoning
        assert result.failure_type == FailureType.UNKNOWN
        assert result.confidence == 0.0
        assert "API error" in result.reasoning


def test_classify_invalid_json():
    """Test classification when API returns invalid JSON."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = "This is not valid JSON {invalid"
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

    with patch(
        "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
    ) as mock_anthropic_class:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        classifier = PRFailureClassifier(api_key="test-key")
        result = classifier.classify(pr_context, failed_checks, "error logs")

        # Should fallback to unknown with parse error
        assert result.failure_type == FailureType.UNKNOWN
        assert result.confidence == 0.0
        assert "Parse error" in result.reasoning


def test_classify_invalid_failure_type():
    """Test classification when API returns invalid failure type."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps(
        {
            "failure_type": "invalid_type",
            "confidence": 0.95,
            "reasoning": "Some reasoning",
            "recommended_action": "Some action",
        }
    )
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

    with patch(
        "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
    ) as mock_anthropic_class:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        classifier = PRFailureClassifier(api_key="test-key")
        result = classifier.classify(pr_context, failed_checks, "error logs")

        # Should fallback to unknown with validation error
        assert result.failure_type == FailureType.UNKNOWN
        assert result.confidence == 0.0
        assert "Parse error" in result.reasoning


def test_classify_non_text_block_response():
    """Test classification when API returns non-TextBlock content."""
    mock_response = MagicMock()
    mock_content = MagicMock(spec=[])  # No 'text' attribute
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

    with patch(
        "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
    ) as mock_anthropic_class:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        classifier = PRFailureClassifier(api_key="test-key")
        result = classifier.classify(pr_context, failed_checks, "error logs")

        # Should fallback to unknown
        assert result.failure_type == FailureType.UNKNOWN
        assert result.confidence == 0.0


def test_classify_different_failure_types(mock_anthropic_response):
    """Test classification for different failure types."""
    failure_types = [
        ("lint", 0.95, "Formatting issues"),
        ("test", 0.98, "Test assertion failed"),
        ("build", 0.92, "Compilation error"),
        ("merge_conflict", 0.99, "Unmerged paths detected"),
    ]

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

    for failure_type, confidence, reasoning in failure_types:
        mock_content = MagicMock()
        mock_content.text = json.dumps(
            {
                "failure_type": failure_type,
                "confidence": confidence,
                "reasoning": reasoning,
                "recommended_action": f"Fix {failure_type}",
            }
        )
        mock_anthropic_response.content = [mock_content]

        with patch(
            "aieng_bot_maintain.classifier.classifier.anthropic.Anthropic"
        ) as mock_anthropic_class:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_anthropic_response
            mock_anthropic_class.return_value = mock_client

            classifier = PRFailureClassifier(api_key="test-key")
            result = classifier.classify(pr_context, failed_checks, "error logs")

            assert result.failure_type == FailureType(failure_type)
            assert result.confidence == confidence
            assert reasoning in result.reasoning


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
