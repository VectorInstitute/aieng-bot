"""Streaming reply renderer for Slack.

Slack has no token-streaming primitive for classic messages, so streaming is
emulated the way Slack's own AI apps do it: post a placeholder reply in the
thread, then edit it in place as the agent works. Updates are throttled to
stay well inside ``chat.update`` rate limits.

While the agent is working, the message shows an activity trail (one line
per tool action, current one animated with an hourglass) above the partial
answer. The final update replaces all of it with the finished answer and a
muted context line summarizing what the agent did.
"""

import time
from typing import Any

# Slack rejects messages over 40k chars; leave generous headroom.
_MAX_TEXT = 12000
_CURSOR = " ▍"


class StreamingReply:
    """A single in-thread reply message that is edited as the agent works.

    Parameters
    ----------
    client : Any
        Bolt async web client (``app.client``).
    channel : str
        Channel ID the reply lives in.
    ts : str
        Timestamp of the placeholder message to edit.
    min_interval : float
        Minimum seconds between ``chat.update`` calls.

    """

    def __init__(
        self, client: Any, channel: str, ts: str, min_interval: float = 1.2
    ) -> None:
        """Initialize the renderer around an already-posted placeholder."""
        self._client = client
        self._channel = channel
        self._ts = ts
        self._min_interval = min_interval
        self._activity: list[str] = []
        self._text = ""
        self._last_flush = 0.0
        self._dirty = False

    # ------------------------------------------------------------------
    # State mutation (cheap; no network)
    # ------------------------------------------------------------------

    def start_activity(self, line: str) -> None:
        """Add an in-progress activity line (rendered with an hourglass)."""
        self._activity.append(f"⏳ {line}")
        self._dirty = True

    def resolve_activity(self, done_line: str | None = None) -> None:
        """Mark the most recent activity line as completed.

        Parameters
        ----------
        done_line : str, optional
            Replacement text; defaults to the original line without the
            hourglass.

        """
        if not self._activity:
            return
        current = self._activity[-1].removeprefix("⏳ ")
        self._activity[-1] = f"✔ {done_line or current}"
        self._dirty = True

    def append_text(self, chunk: str) -> None:
        """Append streamed answer text."""
        self._text += chunk
        self._dirty = True

    def clear_text(self) -> None:
        """Discard streamed text (the agent decided to use a tool instead)."""
        self._text = ""
        self._dirty = True

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_working(self) -> str:
        parts: list[str] = []
        if self._activity:
            parts.append("\n".join(self._activity))
        if self._text:
            parts.append(self._text[:_MAX_TEXT] + _CURSOR)
        return "\n\n".join(parts) or "⏳ _Thinking…_"

    async def flush(self, force: bool = False) -> None:
        """Push pending state to Slack if the throttle window allows.

        Parameters
        ----------
        force : bool
            Update immediately, ignoring the throttle.

        """
        now = time.monotonic()
        if not self._dirty:
            return
        if not force and (now - self._last_flush) < self._min_interval:
            return
        self._last_flush = now
        self._dirty = False
        await self._client.chat_update(
            channel=self._channel, ts=self._ts, text=self._render_working()
        )

    async def finalize(self, text: str, footer: str | None = None) -> None:
        """Replace the working message with the final answer.

        Parameters
        ----------
        text : str
            Final answer in Slack mrkdwn.
        footer : str, optional
            Muted context line (activity summary) appended below the answer.

        """
        text = text[:_MAX_TEXT]
        blocks: list[dict[str, Any]] = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": chunk},
            }
            for chunk in _split_for_blocks(text)
        ]
        if footer:
            blocks.append(
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": footer}],
                }
            )
        await self._client.chat_update(
            channel=self._channel, ts=self._ts, text=text, blocks=blocks
        )

    async def fail(self, message: str) -> None:
        """Replace the working message with an error notice."""
        await self._client.chat_update(
            channel=self._channel,
            ts=self._ts,
            text=f"⚠️ Something went wrong: {message[:500]}",
        )


def _split_for_blocks(text: str, limit: int = 2900) -> list[str]:
    """Split text into chunks under Slack's 3000-char section block limit.

    Splits on paragraph boundaries where possible so formatting survives.

    Parameters
    ----------
    text : str
        Full mrkdwn text.
    limit : int
        Maximum characters per chunk.

    Returns
    -------
    list[str]
        Non-empty chunks in order.

    """
    if len(text) <= limit:
        return [text] if text else ["_(empty answer)_"]

    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        # A single oversized paragraph gets hard-split.
        rest = paragraph
        while len(rest) > limit:
            chunks.append(rest[:limit])
            rest = rest[limit:]
        current = rest
    if current:
        chunks.append(current)
    return chunks
