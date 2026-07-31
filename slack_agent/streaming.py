"""Streaming reply renderer for Slack.

Slack has no token-streaming primitive for classic messages, so streaming is
emulated the way Slack's own AI apps do it: post a placeholder reply in the
thread, then edit it in place as the agent works. Updates are throttled to
stay well inside ``chat.update`` rate limits.

While the agent is working, the message shows a single muted status line
describing the current action (the style Claude Tag uses: quiet, no emoji,
trailing ellipsis). Once answer text starts streaming it replaces the
status. The final update shows the finished answer and a muted context
line summarizing what the agent did.
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
        self._status = ""
        self._text = ""
        self._last_flush = 0.0
        self._dirty = False

    # ------------------------------------------------------------------
    # State mutation (cheap; no network)
    # ------------------------------------------------------------------

    def set_status(self, line: str) -> None:
        """Replace the current status line (shown while no text streams).

        Parameters
        ----------
        line : str
            Plain description of the current action, no trailing ellipsis
            (one is added when rendering).

        """
        self._status = line
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
        if self._text:
            return self._text[:_MAX_TEXT] + _CURSOR
        if self._status:
            return f"_{self._status}…_"
        return "_Thinking…_"

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
