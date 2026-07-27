"""Observability tools for Claude Agent SDK executions.

This package provides comprehensive tracing and observability for Claude Agent SDK
executions. It captures tool calls, reasoning, actions, and errors in a structured
format for later analysis and dashboard display.

Main Components
---------------
- tracer : Main tracer class
- classifiers : Message classification logic
- extractors : Content extraction from message blocks
- parsers : ResultMessage parsing utilities
- processors : Event processing and summary generation
- storage : Trace storage (JSON files and GCS)

Public API
----------
- AgentExecutionTracer : Main tracer class
"""

from .activity_logger import ActivityLogger, ActivityStatus
from .tracer import AgentExecutionTracer

__all__ = [
    "AgentExecutionTracer",
    "ActivityLogger",
    "ActivityStatus",
]
