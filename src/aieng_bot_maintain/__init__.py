"""AI Engineering Bot Maintain - PR failure classification and auto-fix."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("aieng-bot-maintain")
except PackageNotFoundError:
    # Package not installed, use fallback
    __version__ = "0.1.0.dev"

from .classifier.classifier import PRFailureClassifier
from .classifier.models import (
    CheckFailure,
    ClassificationResult,
    FailureType,
    PRContext,
)
from .metrics import MetricsCollector
from .observability import AgentExecutionTracer, create_tracer_from_env

__all__ = [
    "PRFailureClassifier",
    "CheckFailure",
    "ClassificationResult",
    "FailureType",
    "PRContext",
    "MetricsCollector",
    "AgentExecutionTracer",
    "create_tracer_from_env",
    "__version__",
]
