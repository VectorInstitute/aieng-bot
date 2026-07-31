"""Streaming reply renderer for Slack.

Two engines behind one interface:

- **Native streaming** (channels and threaded DMs): Slack's
  ``chat.startStream`` / ``chat.appendStream`` / ``chat.stopStream``
  render token streaming with Slack's own typing treatment; step
  transitions are sent best-effort as task-update chunks. Streamed
  messages are always thread replies, which channels want anyway.
- **Edit-in-place** (top-level DMs, and any workspace where the native
  API is unavailable): a placeholder message updated under a throttle,
  with steps as a native plan block. This keeps DM replies inline, which
  native streaming cannot do.

Finalization differs per engine. Edit-in-place messages are normalized
with a ``chat.update`` to the canonical answer layout (sections + muted
context footer). Streamed messages cannot be rewritten by ``chat.update``
(Slack rejects it with ``block_mismatch``: rich-text blocks cannot be
replaced), so the remainder of the answer and the footer travel on
``chat.stopStream`` itself. Protocol tokens (NO_REPLY, the reaction
sign-off) are masked from the visible stream by
:func:`~slack_agent.reactions.visible_stream_text`.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any

from .mrkdwn import to_mrkdwn
from .reactions import visible_stream_text

logger = logging.getLogger(__name__)

# Slack rejects messages over 40k chars; leave generous headroom.
_MAX_TEXT = 12000
_CURSOR = " ▍"

_RUNNING = "\U0001f7e1"  # yellow circle
_DONE = "\U0001f7e2"  # green circle
_FAILED = "\U0001f534"  # red circle

# Workspace capability flags, discovered on first failure and remembered
# for the process lifetime so every reply does not retry a dead API.
_CAPS = {"native_stream": True, "native_tasks": True, "native_plan_block": True}


@dataclass
class _Step:
    """One checklist entry with live status transitions."""

    running_label: str
    done_label: str
    status: str = "running"
    source_url: str = ""
    source_text: str = ""

    @property
    def label(self) -> str:
        return self.running_label if self.status == "running" else self.done_label

    def plan_status(self) -> str:
        return {"running": "in_progress", "done": "complete", "failed": "error"}[
            self.status
        ]

    def render(self) -> str:
        if self.status == "running":
            return f"{_RUNNING} {self.running_label}…"
        if self.status == "failed":
            return f"{_FAILED} {self.running_label}"
        return f"{_DONE} {self.done_label}"


class StreamingReply:
    """A single in-conversation reply rendered live as the agent works.

    Parameters
    ----------
    client : Any
        Bolt async web client (``app.client``).
    channel : str
        Channel ID the reply lives in.
    anchor_ts : str
        Timestamp of the user's message (native streams thread off it).
    reply_thread_ts : str or None
        Thread for edit-in-place replies; None posts inline (DMs).
    native_allowed : bool
        Whether native streaming may be used (False for top-level DMs,
        where it would force a thread).
    recipient_user_id : str
        Asker's user ID (required by native streaming in channels).
    recipient_team_id : str
        Asker's team ID (required by native streaming in channels).
    min_interval : float
        Minimum seconds between network flushes.

    """

    def __init__(
        self,
        client: Any,
        channel: str,
        anchor_ts: str,
        reply_thread_ts: str | None = None,
        native_allowed: bool = False,
        recipient_user_id: str = "",
        recipient_team_id: str = "",
        min_interval: float = 1.2,
    ) -> None:
        """Store configuration; call :meth:`start` before streaming."""
        self._client = client
        self._channel = channel
        self._anchor_ts = anchor_ts
        self._reply_thread_ts = reply_thread_ts
        self._native_allowed = native_allowed
        self._recipient_user_id = recipient_user_id
        self._recipient_team_id = recipient_team_id
        self._min_interval = min_interval
        self._steps: list[_Step] = []
        self._text = ""
        self._last_flush = 0.0
        self._dirty = False
        self._flush_seq = 0
        self._ts = ""
        self._native = False
        # Exact text delivered to the native stream so far, and the
        # retired prefix left behind by clear_text (appends are immutable).
        self._sent_stream = ""
        self._stream_base = ""
        self._sent_step_states: list[tuple[str, str]] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Open the reply: a native stream where possible, else a placeholder."""
        if self._native_allowed and _CAPS["native_stream"]:
            try:
                response = await self._client.chat_startStream(
                    channel=self._channel,
                    thread_ts=self._anchor_ts,
                    recipient_user_id=self._recipient_user_id,
                    recipient_team_id=self._recipient_team_id,
                    task_display_mode="plan",
                )
                self._ts = response["ts"]
                self._native = True
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("native streaming unavailable: %s", exc)
                _CAPS["native_stream"] = False

        response = await self._client.chat_postMessage(
            channel=self._channel,
            thread_ts=self._reply_thread_ts,
            text="_Thinking…_",
        )
        self._ts = response["ts"]
        self._native = False

    # ------------------------------------------------------------------
    # State mutation (cheap; no network)
    # ------------------------------------------------------------------

    def begin_step(self, running_label: str, done_label: str | None = None) -> None:
        """Start a new checklist step, completing any step still running.

        Parameters
        ----------
        running_label : str
            Present-tense label shown while the step runs (no ellipsis).
        done_label : str, optional
            Past-tense label shown once complete; defaults to the running
            label.

        """
        self.complete_step()
        self._steps.append(_Step(running_label, done_label or running_label))
        self._dirty = True

    def complete_step(
        self,
        done_label: str | None = None,
        source_url: str = "",
        source_text: str = "",
    ) -> None:
        """Mark the currently running step as done.

        Parameters
        ----------
        done_label : str, optional
            Replacement past-tense label (e.g. a resolved page title).
        source_url : str, optional
            Link to the resource this step used (shown as a source chip).
        source_text : str, optional
            Display text for the source link.

        """
        for step in reversed(self._steps):
            if step.status == "running":
                step.status = "done"
                if done_label:
                    step.done_label = done_label
                step.source_url = source_url
                step.source_text = source_text
                self._dirty = True
                return

    def append_text(self, chunk: str) -> None:
        """Append streamed answer text."""
        self._text += chunk
        self._dirty = True

    def clear_text(self) -> None:
        """Discard streamed text (the agent decided to use a tool instead)."""
        self._text = ""
        if self._native and self._sent_stream:
            # Native streams cannot retract already-sent text; retire it
            # and continue in a fresh paragraph below.
            self._stream_base = self._sent_stream + "\n\n"
        self._dirty = True

    # ------------------------------------------------------------------
    # Flushing
    # ------------------------------------------------------------------

    async def flush(self, force: bool = False) -> None:
        """Push pending state to Slack if the throttle window allows.

        Parameters
        ----------
        force : bool
            Update immediately, ignoring the throttle.

        """
        now = time.monotonic()
        if not self._dirty or not self._ts:
            return
        if not force and (now - self._last_flush) < self._min_interval:
            return
        self._last_flush = now
        self._dirty = False
        if self._native:
            await self._flush_native()
        else:
            await self._flush_update()

    async def _flush_native(self) -> None:
        """Append new text (and best-effort step updates) to the stream."""
        await self._append_step_chunks()
        target = self._stream_base + visible_stream_text(self._text)
        delta = _stream_delta(self._sent_stream, target)
        if delta:
            self._sent_stream += delta
            await self._client.chat_appendStream(
                channel=self._channel, ts=self._ts, markdown_text=delta
            )

    async def _append_step_chunks(self) -> None:
        """Send changed step states as task-update chunks, best-effort."""
        if not _CAPS["native_tasks"]:
            return
        chunks = self._step_chunks()
        if not chunks:
            return
        try:
            await self._client.chat_appendStream(
                channel=self._channel, ts=self._ts, chunks=chunks
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("task chunks rejected; text-only stream: %s", exc)
            _CAPS["native_tasks"] = False

    def _step_chunks(self) -> list[dict[str, Any]]:
        """Task-update chunks for steps that changed since the last flush."""
        states = [(step.label, step.plan_status()) for step in self._steps]
        chunks = [
            {"type": "task_update", "id": f"t{i}", "title": label, "status": status}
            for i, (label, status) in enumerate(states)
            if i >= len(self._sent_step_states)
            or self._sent_step_states[i] != (label, status)
        ]
        self._sent_step_states = states
        return chunks

    async def _flush_update(self) -> None:
        """Edit-in-place rendering (plan block + streaming section)."""
        self._flush_seq += 1
        blocks, fallback = self._working_blocks()
        try:
            await self._client.chat_update(
                channel=self._channel, ts=self._ts, text=fallback, blocks=blocks
            )
        except Exception:
            if not (_CAPS["native_plan_block"] and self._steps):
                raise
            _CAPS["native_plan_block"] = False
            blocks, fallback = self._working_blocks()
            await self._client.chat_update(
                channel=self._channel, ts=self._ts, text=fallback, blocks=blocks
            )

    # ------------------------------------------------------------------
    # Terminal states
    # ------------------------------------------------------------------

    async def finalize(self, text: str, footer: str | None = None) -> None:
        """Complete the reply with the final answer.

        Parameters
        ----------
        text : str
            Final answer in standard markdown. Native streams render it
            as-is; edit-in-place messages get it converted to mrkdwn.
        footer : str, optional
            Muted context line (activity summary) appended below the answer.

        """
        text = text[:_MAX_TEXT]
        if self._native:
            await self._finalize_native(text, footer)
            return
        mrkdwn = to_mrkdwn(text)
        blocks = _answer_blocks(mrkdwn, footer)
        await self._client.chat_update(
            channel=self._channel, ts=self._ts, text=mrkdwn, blocks=blocks
        )

    async def _finalize_native(self, text: str, footer: str | None) -> None:
        """Append what the stream is still missing, then stop it.

        A streamed message cannot be rewritten afterwards: ``chat.update``
        fails with ``block_mismatch`` (rich-text blocks cannot be
        replaced). The remaining answer delta and the footer must travel
        on ``chat.stopStream`` itself.
        """
        self.complete_step()
        await self._append_step_chunks()
        delta = _stream_delta(self._sent_stream, self._stream_base + text)
        kwargs: dict[str, Any] = {}
        if delta:
            kwargs["markdown_text"] = delta
        if footer:
            kwargs["blocks"] = [_footer_block(footer)]
        try:
            await self._client.chat_stopStream(
                channel=self._channel, ts=self._ts, **kwargs
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("stopStream with final payload failed: %s", exc)
            await self._repost_answer(to_mrkdwn(text), footer)

    async def _repost_answer(self, mrkdwn: str, footer: str | None) -> None:
        """Last-resort delivery: replace the stream with a fresh message.

        The truncated stream is stopped and deleted best-effort first so
        the answer never appears twice.
        """
        for call in (
            self._client.chat_stopStream,
            self._client.chat_delete,
        ):
            try:
                await call(channel=self._channel, ts=self._ts)
            except Exception as exc:  # noqa: BLE001
                logger.debug("stream cleanup step failed: %s", exc)
        response = await self._client.chat_postMessage(
            channel=self._channel,
            thread_ts=self._anchor_ts,
            text=mrkdwn,
            blocks=_answer_blocks(mrkdwn, footer),
        )
        self._ts = response["ts"]
        self._native = False

    async def delete(self) -> None:
        """Remove the reply entirely (the agent chose not to respond)."""
        await self._stop_native_stream()
        await self._client.chat_delete(channel=self._channel, ts=self._ts)

    async def fail(self, message: str) -> None:
        """Render the checklist with the current step failed, plus the error.

        Never raises: this is the terminal error surface, and an exception
        here would strand the working message in its half-streamed state.
        """
        for step in reversed(self._steps):
            if step.status == "running":
                step.status = "failed"
                break
        error_line = f"⚠️ Something went wrong: {message[:500]}"
        try:
            if self._native:
                await self._append_step_chunks()
                prefix = "\n\n" if self._sent_stream else ""
                await self._client.chat_stopStream(
                    channel=self._channel,
                    ts=self._ts,
                    markdown_text=prefix + error_line,
                )
                return
            blocks: list[dict[str, Any]] = []
            if self._steps:
                blocks.append(
                    self._plan_block()
                    if _CAPS["native_plan_block"]
                    else self._steps_context_block()
                )
            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": error_line}}
            )
            await self._client.chat_update(
                channel=self._channel, ts=self._ts, text=error_line, blocks=blocks
            )
        except Exception:
            logger.exception("could not render error state")
            try:
                await self._client.chat_postMessage(
                    channel=self._channel,
                    thread_ts=self._anchor_ts
                    if self._native
                    else self._reply_thread_ts,
                    text=error_line,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("error fallback post failed: %s", exc)

    async def _stop_native_stream(self) -> None:
        if not self._native:
            return
        try:
            await self._client.chat_stopStream(channel=self._channel, ts=self._ts)
        except Exception as exc:  # noqa: BLE001
            logger.debug("stopStream failed (already stopped?): %s", exc)

    # ------------------------------------------------------------------
    # Edit-in-place rendering helpers
    # ------------------------------------------------------------------

    def _plan_block(self) -> dict[str, Any]:
        """Render the steps as Slack's native plan block (AI task list)."""
        tasks: list[dict[str, Any]] = []
        for i, step in enumerate(self._steps):
            task: dict[str, Any] = {
                "task_id": f"t{i}",
                "title": step.label,
                "status": step.plan_status(),
            }
            if step.source_url:
                task["sources"] = [
                    {
                        "type": "url",
                        "url": step.source_url,
                        "text": step.source_text or step.source_url,
                    }
                ]
            tasks.append(task)
        return {
            "type": "plan",
            "block_id": f"plan_{self._flush_seq}",
            "title": {"type": "plain_text", "text": "Working on it"},
            "tasks": tasks,
        }

    def _steps_context_block(self) -> dict[str, Any]:
        """Fallback rendering: steps as a muted context block."""
        return {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": "\n".join(s.render() for s in self._steps)}
            ],
        }

    def _working_blocks(self) -> tuple[list[dict[str, Any]], str]:
        """Build the edit-in-place Block Kit layout plus a text fallback."""
        blocks: list[dict[str, Any]] = []
        if self._steps:
            blocks.append(
                self._plan_block()
                if _CAPS["native_plan_block"]
                else self._steps_context_block()
            )
        visible = visible_stream_text(self._text)
        if visible:
            # Section blocks cap at 3000 chars; the final render shows it all.
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": visible[:2900] + _CURSOR},
                }
            )
        if not blocks:
            blocks.append(
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": "Thinking…"}],
                }
            )
        fallback = visible[:200] if visible else "Working…"
        return blocks, fallback


def _stream_delta(sent: str, target: str) -> str:
    """Text to append so a native stream's content reaches *target*.

    Returns "" when the stream already shows *target*, when *target* does
    not extend what was sent (the masked tail can shrink while a protocol
    line is still forming; appends are immutable, so wait rather than
    duplicate), or when only whitespace would be appended.

    Parameters
    ----------
    sent : str
        Exact text delivered to the stream so far.
    target : str
        Full text the stream should show.

    Returns
    -------
    str
        The delta to append, possibly empty.

    """
    if not target.startswith(sent):
        return ""
    delta = target[len(sent) :]
    return delta if delta.strip() else ""


def _footer_block(footer: str) -> dict[str, Any]:
    """Muted context block for the activity-summary footer."""
    return {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": footer}],
    }


def _answer_blocks(mrkdwn: str, footer: str | None) -> list[dict[str, Any]]:
    """Canonical answer layout: section blocks plus an optional footer."""
    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": chunk}}
        for chunk in _split_for_blocks(mrkdwn)
    ]
    if footer:
        blocks.append(_footer_block(footer))
    return blocks


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
