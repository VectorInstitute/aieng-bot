"""Observability tools for Claude Agent SDK executions.

This package provides comprehensive tracing and observability for Claude Agent SDK
executions. It captures tool calls, reasoning, actions, and errors in a structured
format for later analysis and dashboard display.

Main Components
---------------
- tracer : Main tracer class (local trace file, used for PR-comment summaries)
- classifiers : Message classification logic
- extractors : Content extraction from message blocks
- parsers : ResultMessage parsing utilities
- processors : Event processing and summary generation
- storage : Local trace file storage
- langfuse_tracing : Langfuse/OpenTelemetry instrumentation setup

Public API
----------
- AgentExecutionTracer : Main tracer class
- instrument_anthropic, instrument_claude_agent_sdk : Langfuse tracing setup
"""

from .activity_logger import ActivityLogger, ActivityStatus
from .langfuse_tracing import instrument_anthropic, instrument_claude_agent_sdk
from .tracer import AgentExecutionTracer

__all__ = [
    "AgentExecutionTracer",
    "ActivityLogger",
    "ActivityStatus",
    "instrument_anthropic",
    "instrument_claude_agent_sdk",
]
