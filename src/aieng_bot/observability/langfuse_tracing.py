"""Langfuse tracing setup for aieng-bot.

Instruments the Anthropic SDK (used by the classifier) and the Claude Agent
SDK (used by the agent fixer) so their LLM calls and tool invocations are
captured as Langfuse traces via OpenTelemetry.

Instrumentation is best-effort: if Langfuse credentials are not configured,
or an instrumentation library fails to load, tracing is silently skipped
rather than breaking the classify/fix pipeline.
"""

from __future__ import annotations

import os

from langfuse import Langfuse, get_client
from openinference.instrumentation.claude_agent_sdk import ClaudeAgentSDKInstrumentor
from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

from ..utils.logging import log_info, log_warning


class _InstrumentationState:
    """Tracks which OpenTelemetry instrumentors have been applied."""

    def __init__(self) -> None:
        self.anthropic_instrumented = False
        self.agent_sdk_instrumented = False


_state = _InstrumentationState()


def langfuse_enabled() -> bool:
    """Return True if Langfuse credentials are configured via env vars."""
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def instrument_anthropic() -> Langfuse | None:
    """Instrument the raw Anthropic SDK for Langfuse tracing (classifier).

    Idempotent - safe to call on every classifier instantiation.

    Returns
    -------
    Langfuse or None
        The Langfuse client if tracing is enabled, else None.

    """
    if not langfuse_enabled():
        return None

    try:
        client = get_client()

        if not _state.anthropic_instrumented:
            AnthropicInstrumentor().instrument()
            _state.anthropic_instrumented = True
            log_info("Langfuse: instrumented Anthropic SDK for tracing")
    except Exception as e:
        log_warning(f"Langfuse: failed to instrument Anthropic SDK: {e}")
        return None
    else:
        return client


def instrument_claude_agent_sdk() -> Langfuse | None:
    """Instrument the Claude Agent SDK for Langfuse tracing (agent fixer).

    Idempotent - safe to call on every fixer run.

    Returns
    -------
    Langfuse or None
        The Langfuse client if tracing is enabled, else None.

    """
    if not langfuse_enabled():
        return None

    try:
        client = get_client()

        if not _state.agent_sdk_instrumented:
            ClaudeAgentSDKInstrumentor().instrument()
            _state.agent_sdk_instrumented = True
            log_info("Langfuse: instrumented Claude Agent SDK for tracing")
    except Exception as e:
        log_warning(f"Langfuse: failed to instrument Claude Agent SDK: {e}")
        return None
    else:
        return client
