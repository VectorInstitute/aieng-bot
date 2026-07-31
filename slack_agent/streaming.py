"""Streaming reply renderer for Slack.

Slack has no token-streaming primitive for classic messages, so streaming is
emulated the way Slack's own AI apps do it: post a placeholder reply in the
thread, then edit it in place as the agent works. Updates are throttled to
stay well inside ``chat.update`` rate limits.

While the agent is working, the message shows a live step checklist in the
GitHub Actions style: each step is a bullet whose status transitions in
place (🟡 running → 🟢 done → 🔴 failed), with the streaming answer text
below. Short tool-less replies skip the checklist entirely (the pattern
Claude Tag uses: questions get a direct reply, longer tasks get a live
checklist edited in place). The final update replaces everything with the
finished answer and a muted context line.
"""

import time
from dataclasses import dataclass
from typing import Any

from .reactions import visible_stream_text

# Slack rejects messages over 40k chars; leave generous headroom.
_MAX_TEXT = 12000
_CURSOR = " ▍"

_RUNNING = "\U0001f7e1"  # yellow circle
_DONE = "\U0001f7e2"  # green circle
_FAILED = "\U0001f534"  # red circle


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
        self._steps: list[_Step] = []
        self._text = ""
        self._last_flush = 0.0
        self._dirty = False
        self._native_plan = True
        self._flush_seq = 0

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
        self._dirty = True

    # ------------------------------------------------------------------
    # Rendering
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
        """Build the working-state Block Kit layout plus a text fallback.

        Steps render as a native plan block (Slack's task-list surface for
        AI apps, with built-in status indicators); if the workspace rejects
        it, steps fall back to a muted context block. The streaming text is
        a regular section block below.
        """
        blocks: list[dict[str, Any]] = []
        if self._steps:
            blocks.append(
                self._plan_block() if self._native_plan else self._steps_context_block()
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
        self._flush_seq += 1
        blocks, fallback = self._working_blocks()
        try:
            await self._client.chat_update(
                channel=self._channel, ts=self._ts, text=fallback, blocks=blocks
            )
        except Exception:
            if not (self._native_plan and self._steps):
                raise
            # Workspace rejected the plan block; fall back to context style.
            self._native_plan = False
            blocks, fallback = self._working_blocks()
            await self._client.chat_update(
                channel=self._channel, ts=self._ts, text=fallback, blocks=blocks
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

    async def delete(self) -> None:
        """Remove the placeholder message (the agent chose not to reply)."""
        await self._client.chat_delete(channel=self._channel, ts=self._ts)

    async def fail(self, message: str) -> None:
        """Render the checklist with the current step failed, plus the error."""
        for step in reversed(self._steps):
            if step.status == "running":
                step.status = "failed"
                break
        blocks: list[dict[str, Any]] = []
        if self._steps:
            blocks.append(
                self._plan_block() if self._native_plan else self._steps_context_block()
            )
        error_line = f"⚠️ Something went wrong: {message[:500]}"
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": error_line}}
        )
        await self._client.chat_update(
            channel=self._channel, ts=self._ts, text=error_line, blocks=blocks
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
