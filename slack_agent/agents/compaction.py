"""Client-side history compaction (the Claude Code pattern).

When a session's history crosses the trigger threshold, the older
portion is summarized by the model into a single ``<conversation_summary>``
turn and the recent tail is kept verbatim. Summaries are cumulative: a
later compaction re-summarizes the previous summary together with the
turns that followed it.

This is the portable equivalent of Anthropic's server-side compaction,
which is unavailable behind the LLM gateway. Compaction runs after the
reply has been delivered, off the answer's latency path, and can never
break a session: any failure falls back to a boundary-safe hard trim.
"""

import logging
from typing import Any

from .history import (
    Message,
    fold_summary,
    hard_trim,
    history_tokens,
    split_for_compaction,
)

logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM = """\
You compact agent conversation history. Produce a terse bullet summary of
the transcript you are given, preserving exactly what a future turn may
need:
- the user's goals, questions asked, and answers given (with key facts)
- wiki pages read, as title plus URL
- decisions made and user preferences expressed
- unresolved questions or promised follow-ups
Do not add preamble, commentary, or information not in the transcript."""

# Per-block caps keep the summarization request itself small.
_TOOL_INPUT_CHARS = 300
_TOOL_RESULT_CHARS = 1500
_TRANSCRIPT_CHARS = 120_000


def _render_transcript(head: list[Message]) -> str:
    """Flatten history entries into a plain-text transcript to summarize."""
    lines: list[str] = []
    for message in head:
        role = str(message.get("role", "?"))
        content = message.get("content")
        if isinstance(content, str):
            lines.append(f"{role}: {content}")
            continue
        for block in content or []:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "text":
                lines.append(f"{role}: {block.get('text', '')}")
            elif kind == "tool_use":
                arguments = str(block.get("input", {}))[:_TOOL_INPUT_CHARS]
                lines.append(f"{role} called {block.get('name')}({arguments})")
            elif kind == "tool_result":
                result = str(block.get("content", ""))[:_TOOL_RESULT_CHARS]
                lines.append(f"tool result: {result}")
    return "\n".join(lines)[-_TRANSCRIPT_CHARS:]


class HistoryCompactor:
    """Keeps a session's history within its context budget.

    Parameters
    ----------
    client : Any
        Async Anthropic-compatible client used for summarization calls.
    model : str
        Model name for summarization (the agent's own model).
    context_window : int
        The model's context window in tokens; budgets derive from it.
    trigger_ratio : float
        Fraction of the window at which compaction starts.
    keep_ratio : float
        Fraction of the window kept verbatim as the recent tail.

    """

    def __init__(
        self,
        client: Any,
        model: str,
        context_window: int,
        trigger_ratio: float = 0.5,
        keep_ratio: float = 0.2,
    ) -> None:
        """Derive token budgets from the model's context window."""
        self._client = client
        self._model = model
        self.trigger_tokens = int(context_window * trigger_ratio)
        self.keep_tokens = int(context_window * keep_ratio)

    async def compact(self, history: list[Message]) -> list[Message]:
        """Return *history*, compacted if it exceeds the trigger budget.

        Parameters
        ----------
        history : list of dict
            Full Anthropic message history after the latest turn.

        Returns
        -------
        list of dict
            The same history when under budget; otherwise a summary turn
            plus the recent tail, or a hard-trimmed history if the
            summarization call fails.

        """
        used = history_tokens(history)
        if used <= self.trigger_tokens:
            return history
        head, tail = split_for_compaction(history, self.keep_tokens)
        if not head:
            return history
        try:
            summary = await self._summarize(head)
        except Exception:
            logger.exception("compaction summary failed; hard-trimming instead")
            return hard_trim(history, self.trigger_tokens)
        compacted = fold_summary(summary, tail)
        logger.info(
            "compacted history: ~%d -> ~%d tokens (%d entries -> %d)",
            used,
            history_tokens(compacted),
            len(history),
            len(compacted),
        )
        return compacted

    async def _summarize(self, head: list[Message]) -> str:
        """Summarize *head* with the model; raise if the result is empty."""
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            system=_SUMMARY_SYSTEM,
            messages=[{"role": "user", "content": _render_transcript(head)}],
        )
        summary = "".join(
            block.text
            for block in response.content
            if getattr(block, "type", "") == "text"
        ).strip()
        if not summary:
            raise ValueError("model returned an empty summary")
        return summary
