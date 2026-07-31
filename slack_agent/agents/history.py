"""Token-aware agent-history bookkeeping.

The harness budgets conversation history in tokens, not entry counts:
forty short turns cost almost nothing while forty wiki-page tool results
can dwarf the context window. Estimates use a chars/4 heuristic over the
JSON rendering; gateway-hosted models expose no token-counting endpoint,
and budgeting only needs to be roughly right.

Splitting rules protect API invariants: history is only ever cut at a
plain user text turn, so a ``tool_use`` block is never separated from
its ``tool_result``.
"""

import json
from typing import Any

Message = dict[str, Any]


def estimate_tokens(entry: Any) -> int:
    """Estimate the token cost of one history entry (chars/4 heuristic)."""
    return max(1, len(json.dumps(entry, default=str)) // 4)


def history_tokens(history: list[Message]) -> int:
    """Estimate the total token cost of a history list."""
    return sum(estimate_tokens(entry) for entry in history)


def is_plain_user_turn(entry: Message) -> bool:
    """Return True for a plain text user turn (a safe cut boundary)."""
    return entry.get("role") == "user" and isinstance(entry.get("content"), str)


def split_for_compaction(
    history: list[Message], keep_tokens: int
) -> tuple[list[Message], list[Message]]:
    """Split history into ``(head, tail)`` for compaction.

    The tail is the most recent stretch that fits *keep_tokens*, widened
    forward to the next plain user turn so tool call/result pairs stay
    together. The head is everything older, destined for summarization.

    Parameters
    ----------
    history : list of dict
        Full Anthropic message history.
    keep_tokens : int
        Token budget for the tail kept verbatim.

    Returns
    -------
    tuple of (list, list)
        ``(head, tail)``; the head is empty when everything fits, and
        the tail is empty when no safe boundary exists in the window.

    """
    total = 0
    cut = 0
    for i in range(len(history) - 1, -1, -1):
        total += estimate_tokens(history[i])
        if total > keep_tokens:
            cut = i + 1
            break
    for j in range(cut, len(history)):
        if is_plain_user_turn(history[j]):
            return history[:j], history[j:]
    return history, []


def hard_trim(history: list[Message], max_tokens: int) -> list[Message]:
    """Drop the oldest turn groups until the history fits *max_tokens*.

    The fallback when summarization is unavailable. Cuts only at plain
    user turns; if a single remaining group still exceeds the budget it
    is returned as-is rather than corrupting tool pairing.
    """
    while history and history_tokens(history) > max_tokens:
        boundary = next(
            (j for j in range(1, len(history)) if is_plain_user_turn(history[j])),
            None,
        )
        if boundary is None:
            break
        history = history[boundary:]
    return history


def fold_summary(summary: str, tail: list[Message]) -> list[Message]:
    """Rebuild history as one summary turn followed by the recent tail."""
    text = (
        "<conversation_summary>\n"
        "System note: earlier turns of this conversation were compacted "
        "to save context space. Summary of what happened before:\n"
        f"{summary.strip()}\n"
        "</conversation_summary>"
    )
    return [{"role": "user", "content": text}, *tail]
