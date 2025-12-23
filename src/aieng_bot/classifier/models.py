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

    def __post_init__(self) -> None:
        """Validate classification result after initialization."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"Confidence must be between 0.0 and 1.0, got {self.confidence}"
            )
