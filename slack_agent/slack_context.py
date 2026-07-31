"""Ambient Slack context (design layer L2).

Builds the small recent-message window injected when a thread session
starts: the last few channel messages plus the pre-mention thread
replies, formatted compactly with display names. Deeper history is the
model's job via the on-demand Slack tools (L3), so this window stays
deliberately small and cheap.
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Shared user-id -> display-name cache (also used by the sync tool executor).
NAME_CACHE: dict[str, str] = {}

_CHANNEL_LIMIT = 15
_THREAD_LIMIT = 20
_MESSAGE_CHARS = 280
_WINDOW_CHARS = 6000


def truncate(text: str, limit: int = _MESSAGE_CHARS) -> str:
    """Truncate one message body, marking elisions."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def format_message(ts: str, name: str, text: str) -> str:
    """Format one message as ``[MM-DD HH:MM] Name: text``."""
    try:
        stamp = time.strftime("%m-%d %H:%M", time.gmtime(float(ts)))
    except (TypeError, ValueError):
        stamp = "?"
    return f"[{stamp}] {name}: {truncate(text)}"


class SlackContextService:
    """Fetches and formats ambient context via the Slack Web API.

    Parameters
    ----------
    client : Any
        Bolt async web client (``app.client``).

    """

    def __init__(self, client: Any) -> None:
        """Store the async Slack client."""
        self._client = client

    async def display_name(self, user_id: str) -> str:
        """Resolve a user ID to a display name, with caching."""
        if not user_id:
            return "unknown"
        if user_id not in NAME_CACHE:
            try:
                info = await self._client.users_info(user=user_id)
                profile = info["user"].get("profile", {})
                NAME_CACHE[user_id] = (
                    profile.get("display_name")
                    or profile.get("real_name")
                    or info["user"].get("name")
                    or user_id
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("users_info failed for %s: %s", user_id, exc)
                return user_id
        return NAME_CACHE[user_id]

    async def _format_messages(self, messages: list[dict[str, Any]]) -> list[str]:
        lines = []
        for msg in messages:
            if msg.get("subtype"):
                continue
            user = msg.get("user", "")
            name = (
                await self.display_name(user)
                if user
                else (msg.get("username") or "app")
            )
            lines.append(format_message(msg.get("ts", ""), name, msg.get("text", "")))
        return lines

    async def ambient_window(
        self, channel: str, thread_ts: str, exclude_ts: str
    ) -> str:
        """Build the ambient window for a new thread session.

        Parameters
        ----------
        channel : str
            Channel the mention arrived in.
        thread_ts : str
            Root timestamp of the mention's thread.
        exclude_ts : str
            Timestamp of the mention message itself (never included).

        Returns
        -------
        str
            Formatted context block, or empty string when unavailable.

        """
        parts: list[str] = []
        try:
            history = await self._client.conversations_history(
                channel=channel, limit=_CHANNEL_LIMIT
            )
            messages = [
                m
                for m in reversed(history.get("messages", []))
                if m.get("ts") != exclude_ts
            ]
            lines = await self._format_messages(messages)
            if lines:
                parts.append(
                    "Recent messages in this channel (oldest first):\n"
                    + "\n".join(lines)
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("ambient channel history failed: %s", exc)

        if thread_ts != exclude_ts:
            # Mentioned mid-thread: include the thread so far.
            try:
                replies = await self._client.conversations_replies(
                    channel=channel, ts=thread_ts, limit=_THREAD_LIMIT
                )
                messages = [
                    m for m in replies.get("messages", []) if m.get("ts") != exclude_ts
                ]
                lines = await self._format_messages(messages)
                if lines:
                    parts.append(
                        "The thread you were mentioned in (oldest first):\n"
                        + "\n".join(lines)
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("ambient thread replies failed: %s", exc)

        return "\n\n".join(parts)[:_WINDOW_CHARS]
