"""Per-thread conversation state.

Every Slack thread (and DM) gets an isolated :class:`ThreadContext` keyed by
``(channel, thread_ts)``, the same conversation model Claude Tag uses. The
context holds both the raw Slack messages observed in the thread (background
listening) and the agent conversation history used for multi-turn follow-ups.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any


def conversation_key(event: dict[str, Any]) -> str:
    """Return the session key for a message event.

    Channel messages key by thread (each thread is a session). A DM's
    top level is one rolling conversation, so it keys by the channel
    itself; explicit threads inside a DM still get their own session.
    """
    if event.get("channel_type") == "im" and not event.get("thread_ts"):
        return str(event["channel"])
    return str(event.get("thread_ts") or event["ts"])


@dataclass
class ThreadContext:
    """Conversation context for a single Slack thread (or DM thread).

    Attributes
    ----------
    channel : str
        Channel ID the thread lives in.
    thread_ts : str
        Timestamp of the thread's root message.
    messages : list[dict[str, str]]
        Raw Slack messages observed in this thread (``user`` and ``text``).
    agent_history : list[Any]
        Anthropic message history for multi-turn agent conversations.
    lock : asyncio.Lock
        Serializes agent runs within the thread so concurrent questions
        cannot interleave their histories.

    """

    channel: str
    thread_ts: str
    messages: list[dict[str, str]] = field(default_factory=list)
    agent_history: list[Any] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ContextStore:
    """In-memory store of per-thread conversation contexts.

    Phase-2 note: contexts (including agent history) live in process memory
    and are lost on redeploy. Persistence is a planned follow-up.
    """

    def __init__(self) -> None:
        """Initialize an empty store."""
        self._contexts: dict[tuple[str, str], ThreadContext] = {}

    def get(self, channel: str, thread_ts: str) -> ThreadContext:
        """Return the context for a thread, creating it if needed.

        Parameters
        ----------
        channel : str
            Channel ID.
        thread_ts : str
            Thread root timestamp.

        Returns
        -------
        ThreadContext
            The (possibly new) context for the thread.

        """
        key = (channel, thread_ts)
        if key not in self._contexts:
            self._contexts[key] = ThreadContext(channel=channel, thread_ts=thread_ts)
        return self._contexts[key]

    def record(self, event: dict[str, Any]) -> ThreadContext:
        """Record a Slack message event into its thread's context.

        Parameters
        ----------
        event : dict
            Slack message event payload.

        Returns
        -------
        ThreadContext
            The context the message was recorded into.

        """
        channel = event["channel"]
        context = self.get(channel, conversation_key(event))
        context.messages.append(
            {"user": event.get("user", "unknown"), "text": event.get("text", "")}
        )
        return context

    def __len__(self) -> int:
        """Return the number of tracked thread contexts."""
        return len(self._contexts)
