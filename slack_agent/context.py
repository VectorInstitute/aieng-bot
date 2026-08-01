"""Per-thread conversation state.

Every Slack thread (and DM) gets an isolated :class:`ThreadContext` keyed by
``(channel, thread_ts)``, the same conversation model Claude Tag uses. The
context holds both the raw Slack messages observed in the thread (background
listening) and the agent conversation history used for multi-turn follow-ups.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from .persistence import ContextArchive


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
    active_agent : str
        Name of the sub-agent serving this session; keeps follow-ups
        routed to the same agent (empty until first routed).
    lock : asyncio.Lock
        Serializes agent runs within the thread so concurrent questions
        cannot interleave their histories.

    """

    channel: str
    thread_ts: str
    messages: list[dict[str, str]] = field(default_factory=list)
    agent_history: list[Any] = field(default_factory=list)
    active_agent: str = ""
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ContextStore:
    """Store of per-thread conversation contexts.

    Live contexts sit in process memory; when an archive is configured,
    each context is also snapshotted after every turn and lazily
    restored on the first access after a restart, so sessions survive
    redeploys.

    Parameters
    ----------
    archive : ContextArchive, optional
        Durable snapshot store; None keeps contexts memory-only.

    """

    def __init__(self, archive: ContextArchive | None = None) -> None:
        """Initialize an empty store with an optional archive."""
        self._contexts: dict[tuple[str, str], ThreadContext] = {}
        self._archive = archive

    def get(self, channel: str, thread_ts: str) -> ThreadContext:
        """Return the context for a thread, restoring or creating it.

        Parameters
        ----------
        channel : str
            Channel ID.
        thread_ts : str
            Thread root timestamp.

        Returns
        -------
        ThreadContext
            The (possibly restored, possibly new) context for the thread.

        """
        key = (channel, thread_ts)
        if key not in self._contexts:
            self._contexts[key] = self._restore(channel, thread_ts)
        return self._contexts[key]

    def _restore(self, channel: str, thread_ts: str) -> ThreadContext:
        snapshot = self._archive.load(channel, thread_ts) if self._archive else None
        if snapshot is None:
            return ThreadContext(channel=channel, thread_ts=thread_ts)
        return ThreadContext(
            channel=channel,
            thread_ts=thread_ts,
            messages=list(snapshot.get("messages", [])),
            agent_history=list(snapshot.get("agent_history", [])),
            active_agent=str(snapshot.get("active_agent", "")),
        )

    def persist(self, context: ThreadContext) -> None:
        """Snapshot a context to the archive, if one is configured."""
        if self._archive is None:
            return
        self._archive.save(
            context.channel,
            context.thread_ts,
            {
                "messages": context.messages[-200:],
                "agent_history": context.agent_history,
                "active_agent": context.active_agent,
            },
        )

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
