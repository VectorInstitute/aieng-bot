"""Ambient Slack context (design layer L2) and history rendering.

Owns everything about turning Slack conversations into model-readable
text: display-name resolution (cached), message formatting, the ambient
window injected when a thread session starts, and the question-wrapping
contract (the ``<slack_context>`` tag). The on-demand history tools (L3)
reuse the same service so both layers render identically.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Timestamps shown to the model (and echoed to users) follow the
# workspace's local time so they match what people see in Slack.
LOCAL_TZ = ZoneInfo(os.environ.get("SLACK_TIMEZONE", "America/Toronto"))

# The tag wrapping ambient context in the first user turn; the tool
# system prompt references it so the contract has one home.
CONTEXT_TAG = "slack_context"

_NAME_CACHE: dict[str, str] = {}

_CHANNEL_LIMIT = 15
_THREAD_LIMIT = 20
_MESSAGE_CHARS = 280
_WINDOW_CHARS = 6000
_RESULT_CHARS = 8000


def truncate(text: str, limit: int = _MESSAGE_CHARS) -> str:
    """Truncate one message body, marking elisions."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def format_message(ts: str, name: str, text: str) -> str:
    """Format one message as ``[MM-DD HH:MM] Name: text`` in local time."""
    try:
        moment = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        stamp = moment.astimezone(LOCAL_TZ).strftime("%m-%d %H:%M")
    except (TypeError, ValueError):
        stamp = "?"
    return f"[{stamp}] {name}: {truncate(text)}"


def _name_from_user_info(info: Any) -> str:
    """Extract the best display name from a ``users.info`` response."""
    profile = info["user"].get("profile", {})
    return (
        profile.get("display_name")
        or profile.get("real_name")
        or info["user"].get("name")
        or ""
    )


class SlackContextService:
    """Fetches and formats Slack conversation context via the Web API.

    Parameters
    ----------
    client : Any
        Bolt async web client (``app.client``).

    """

    def __init__(self, client: Any) -> None:
        """Store the async Slack client."""
        self._client = client

    # ------------------------------------------------------------------
    # Names
    # ------------------------------------------------------------------

    async def display_name(self, user_id: str) -> str:
        """Resolve a user ID to a display name, with caching."""
        if not user_id:
            return "unknown"
        if user_id not in _NAME_CACHE:
            try:
                info = await self._client.users_info(user=user_id)
                _NAME_CACHE[user_id] = _name_from_user_info(info) or user_id
            except Exception as exc:  # noqa: BLE001
                logger.debug("users_info failed for %s: %s", user_id, exc)
                return user_id
        return _NAME_CACHE[user_id]

    async def _warm_names(self, messages: list[dict[str, Any]]) -> None:
        """Resolve all uncached user IDs in *messages* concurrently."""
        missing = {
            m["user"]
            for m in messages
            if m.get("user") and m["user"] not in _NAME_CACHE
        }
        if missing:
            await asyncio.gather(*(self.display_name(uid) for uid in missing))

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    async def render_messages(
        self,
        messages: list[dict[str, Any]],
        thread_markers: bool = False,
        char_budget: int = _WINDOW_CHARS,
    ) -> str:
        """Render Slack messages as compact, name-resolved lines.

        Parameters
        ----------
        messages : list[dict]
            Slack message payloads, oldest first.
        thread_markers : bool
            Annotate messages that have replies with their thread ts so
            the model can drill in via ``get_thread_replies``.
        char_budget : int
            Stop rendering once the output exceeds this many characters.

        Returns
        -------
        str
            One line per message, or ``(no messages)``.

        """
        messages = [m for m in messages if not m.get("subtype")]
        await self._warm_names(messages)
        lines: list[str] = []
        total = 0
        for msg in messages:
            user = msg.get("user", "")
            name = (
                await self.display_name(user)
                if user
                else (msg.get("username") or "app")
            )
            line = format_message(msg.get("ts", ""), name, msg.get("text", ""))
            if thread_markers and msg.get("reply_count"):
                line += f"  (thread with {msg['reply_count']} replies, ts={msg['ts']})"
            lines.append(line)
            total += len(line)
            if total > char_budget:
                break
        return "\n".join(lines) or "(no messages)"

    # ------------------------------------------------------------------
    # Fetching (also used by the L3 tools)
    # ------------------------------------------------------------------

    async def history_text(
        self, channel: str, limit: int, oldest: str | None = None
    ) -> str:
        """Fetch and render recent channel messages, oldest first."""
        kwargs: dict[str, Any] = {"channel": channel, "limit": limit}
        if oldest:
            kwargs["oldest"] = oldest
        response = await self._client.conversations_history(**kwargs)
        return await self.render_messages(
            list(reversed(response.get("messages", []))),
            thread_markers=True,
            char_budget=_RESULT_CHARS,
        )

    async def thread_text(self, channel: str, thread_ts: str) -> str:
        """Fetch and render one thread's replies, oldest first."""
        response = await self._client.conversations_replies(
            channel=channel, ts=thread_ts, limit=50
        )
        return await self.render_messages(
            list(response.get("messages", [])), char_budget=_RESULT_CHARS
        )

    # ------------------------------------------------------------------
    # Ambient window (L2)
    # ------------------------------------------------------------------

    async def _channel_part(self, channel: str, exclude_ts: str) -> str:
        try:
            history = await self._client.conversations_history(
                channel=channel, limit=_CHANNEL_LIMIT
            )
            messages = [
                m
                for m in reversed(history.get("messages", []))
                if m.get("ts") != exclude_ts
            ]
            rendered = await self.render_messages(messages)
            if rendered != "(no messages)":
                return "Recent messages in this channel (oldest first):\n" + rendered
        except Exception as exc:  # noqa: BLE001
            logger.warning("ambient channel history failed: %s", exc)
        return ""

    async def _thread_part(self, channel: str, thread_ts: str, exclude_ts: str) -> str:
        if thread_ts == exclude_ts:
            return ""
        try:
            replies = await self._client.conversations_replies(
                channel=channel, ts=thread_ts, limit=_THREAD_LIMIT
            )
            messages = [
                m for m in replies.get("messages", []) if m.get("ts") != exclude_ts
            ]
            rendered = await self.render_messages(messages)
            if rendered != "(no messages)":
                return "The thread you were mentioned in (oldest first):\n" + rendered
        except Exception as exc:  # noqa: BLE001
            logger.warning("ambient thread replies failed: %s", exc)
        return ""

    async def wrap_question(
        self,
        channel: str,
        thread_ts: str,
        exclude_ts: str,
        asker_id: str,
        question: str,
    ) -> str:
        """Wrap a new session's question with the ambient window.

        Owns the full prompt contract: the ``<slack_context>`` tag, the
        window content, and the asker framing. Fetches run concurrently.

        Parameters
        ----------
        channel : str
            Channel the mention arrived in.
        thread_ts : str
            Root timestamp of the mention's thread.
        exclude_ts : str
            Timestamp of the mention message itself (never included).
        asker_id : str
            User ID of the person asking.
        question : str
            The question with the bot mention stripped.

        Returns
        -------
        str
            The wrapped question ready for the agent.

        """
        channel_part, thread_part, asker = await asyncio.gather(
            self._channel_part(channel, exclude_ts),
            self._thread_part(channel, thread_ts, exclude_ts),
            self.display_name(asker_id),
        )
        ambient = "\n\n".join(p for p in (channel_part, thread_part) if p)
        ambient = ambient[:_WINDOW_CHARS]
        if not ambient:
            return f"{asker} asks: {question}"
        return (
            f"<{CONTEXT_TAG}>\n{ambient}\n</{CONTEXT_TAG}>\n\n{asker} asks: {question}"
        )
