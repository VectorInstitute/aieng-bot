"""AI Engineering Bot Maintain - PR failure classification and auto-fix."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("aieng-bot")
except PackageNotFoundError:
    # Package not installed, use fallback
    __version__ = "0.2.0.dev"

from .auto_merger import ActivityLogger, ActivityStatus
from .classifier.classifier import PRFailureClassifier
from .classifier.models import (
    CheckFailure,
    ClassificationResult,
    FailureType,
    PRContext,
)
from .config import get_model_name
from .observability import AgentExecutionTracer, create_tracer_from_env

__all__ = [
    "PRFailureClassifier",
    "CheckFailure",
    "ClassificationResult",
    "FailureType",
    "PRContext",
    "AgentExecutionTracer",
    "create_tracer_from_env",
    "ActivityLogger",
    "ActivityStatus",
    "get_model_name",
    "__version__",
]
