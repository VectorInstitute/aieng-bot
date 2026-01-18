"""Data models for PR failure classification."""

from dataclasses import dataclass
from enum import Enum


class FailureType(str, Enum):
    """Supported failure types that the bot can fix."""

    MERGE_CONFLICT = "merge_conflict"
    LINT = "lint"
    SECURITY = "security"
    TEST = "test"
    BUILD = "build"
    MERGE_ONLY = "merge_only"  # No failures, just needs rebase and merge
    UNKNOWN = "unknown"


# Priority order for failure types (higher priority = fix first)
# Security issues should be fixed first, then merge conflicts, etc.
FAILURE_TYPE_PRIORITY: dict[FailureType, int] = {
    FailureType.SECURITY: 1,  # Security vulnerabilities - highest priority
    FailureType.MERGE_CONFLICT: 2,  # Must resolve before other fixes
    FailureType.BUILD: 3,  # Build errors block everything
    FailureType.LINT: 4,  # Lint fixes are usually quick
    FailureType.TEST: 5,  # Test fixes after lint (lint may fix tests)
    FailureType.MERGE_ONLY: 6,  # Just needs merge
    FailureType.UNKNOWN: 7,  # Unknown - lowest priority
}


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
    """Result of failure classification.

    Supports multiple failure types for PRs with multiple issues.
    The `failure_types` list is ordered by priority (most important first).
    The `failure_type` property returns the primary (highest priority) type
    for backward compatibility.

    Attributes
    ----------
    failure_types : list[FailureType]
        List of detected failure types, ordered by priority.
    confidence : float
        Confidence score between 0.0 and 1.0.
    reasoning : str
        Explanation for the classification.
    failed_check_names : list[str]
        Names of the failed CI checks.
    recommended_action : str
        Suggested action to fix the failures.

    """

    failure_types: list[FailureType]
    confidence: float  # 0.0 to 1.0
    reasoning: str
    failed_check_names: list[str]
    recommended_action: str

    def __post_init__(self) -> None:
        """Validate classification result after initialization."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"Confidence must be between 0.0 and 1.0, got {self.confidence}"
            )
        if not self.failure_types:
            raise ValueError("failure_types must not be empty")
        # Sort by priority
        self.failure_types = sorted(
            self.failure_types, key=lambda ft: FAILURE_TYPE_PRIORITY.get(ft, 99)
        )

    @property
    def failure_type(self) -> FailureType:
        """Return primary failure type for backward compatibility.

        Returns
        -------
        FailureType
            The highest priority failure type.

        """
        return self.failure_types[0]

    @property
    def failure_type_values(self) -> list[str]:
        """Return list of failure type string values.

        Returns
        -------
        list[str]
            List of failure type values as strings.

        """
        return [ft.value for ft in self.failure_types]

    @property
    def has_multiple_failures(self) -> bool:
        """Check if multiple failure types were detected.

        Returns
        -------
        bool
            True if more than one failure type detected.

        """
        return len(self.failure_types) > 1
