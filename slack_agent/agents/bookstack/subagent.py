"""BookStack QA sub-agent.

Answers documentation questions from the Vector wiki by driving
:class:`~slack_agent.agents.bookstack.agent.BookstackQAAgent` and rendering
its streaming events into the thread's reply. Multi-turn follow-ups work
per thread: the Anthropic message history lives on the thread context.
"""

import logging
import time

from ...config import Settings
from ...context import ThreadContext
from ...mrkdwn import to_mrkdwn
from ...reactions import NO_REPLY, split_reaction
from ...slack_context import SlackContextService
from ...streaming import StreamingReply
from ..slack_tools import (
    SLACK_TOOLS,
    STEP_LABELS,
    SYSTEM_SUFFIX,
    build_slack_executor,
)
from .agent import BookstackQAAgent

logger = logging.getLogger(__name__)


class BookstackSubAgent:
    """Answer documentation questions from the BookStack wiki."""

    name = "bookstack"
    description = (
        "Answers questions about Vector Institute's internal documentation "
        "(cluster access, onboarding, tooling, processes) by searching the "
        "BookStack wiki."
    )

    def __init__(self, settings: Settings, slack_context: SlackContextService) -> None:
        """Build the underlying QA agent from settings.

        Parameters
        ----------
        settings : Settings
            Resolved runtime configuration with BookStack credentials.
        slack_context : SlackContextService
            Shared Slack context service powering the history tools.

        """
        self._slack_context = slack_context
        self._agent = BookstackQAAgent(
            base_url=settings.bookstack_url,
            token_id=settings.bookstack_token_id,
            token_secret=settings.bookstack_token_secret,
        )

    async def handle(
        self, question: str, context: ThreadContext, reply: StreamingReply
    ) -> str | None:
        """Answer *question* from the wiki, streaming progress into *reply*.

        Parameters
        ----------
        question : str
            The user's question.
        context : ThreadContext
            Thread context carrying the multi-turn agent history.
        reply : StreamingReply
            Renderer for the in-thread reply message.

        Returns
        -------
        str or None
            The model's chosen reaction emoji name, if it signed off.

        """
        started = time.monotonic()
        searches = 0
        pages: list[str] = []
        drafting = False

        slack_executor = build_slack_executor(self._slack_context, context.channel)
        async for event in self._agent.ask_stream(
            question,
            history=context.agent_history,
            extra_tools=SLACK_TOOLS,
            extra_executor=slack_executor,
            extra_system=SYSTEM_SUFFIX,
        ):
            event_type = event.get("type")

            if event_type == "tool_use":
                drafting = False
                searches += _begin_tool_step(reply, event)

            elif event_type == "tool_resolve":
                title = str(event.get("page_title", ""))
                if title:
                    pages.append(title)
                    reply.complete_step(
                        f"Read {title}",
                        source_url=str(event.get("page_url", "")),
                        source_text=title,
                    )

            elif event_type == "text_chunk":
                if (searches or pages) and not drafting:
                    reply.begin_step("Drafting answer", "Drafted answer")
                    drafting = True
                reply.append_text(str(event.get("chunk", "")))

            elif event_type == "text_clear":
                reply.clear_text()

            elif event_type == "answer":
                context.agent_history = _trimmed(list(event.get("history", [])))
                duration = time.monotonic() - started
                footer = (
                    _summary(searches, len(pages), duration)
                    if searches or pages
                    else None
                )
                answer, reaction = split_reaction(str(event.get("text", "")))
                if answer.strip().upper() == NO_REPLY:
                    await reply.delete()
                    return reaction or "thumbsup"
                await reply.finalize(to_mrkdwn(answer), footer)
                return reaction

            elif event_type == "error":
                message = str(event.get("message", "unknown error"))
                logger.error("bookstack sub-agent error: %s", message)
                await reply.fail(message)
                return None

            await reply.flush()

        await reply.fail("the agent returned no answer")
        return None


_HISTORY_LIMIT = 40


def _trimmed(history: list[object]) -> list[object]:
    """Cap session history, cutting only at plain user-question boundaries.

    Tool-use and tool-result entries must never be separated, so the cut
    lands on the first plain-text user turn inside the retention window.
    """
    if len(history) <= _HISTORY_LIMIT:
        return history
    for i in range(len(history) - _HISTORY_LIMIT, len(history)):
        entry = history[i]
        if (
            isinstance(entry, dict)
            and entry.get("role") == "user"
            and isinstance(entry.get("content"), str)
        ):
            return history[i:]
    return history[-_HISTORY_LIMIT:]


def _begin_tool_step(reply: StreamingReply, event: dict[str, object]) -> int:
    """Start the checklist step for a tool call; return 1 if it was a search."""
    tool = event.get("tool", "")
    tool_input = event.get("input", {})
    if tool == "search_bookstack":
        query = (
            str(tool_input.get("query", ""))[:80]
            if isinstance(tool_input, dict)
            else ""
        )
        reply.begin_step(
            f'Searching BookStack for "{query}"',
            f'Searched BookStack for "{query}"',
        )
        return 1
    labels = {
        "get_page": ("Reading documentation", "Read documentation"),
        "list_books": ("Browsing BookStack books", "Browsed BookStack books"),
        **STEP_LABELS,
    }
    reply.begin_step(*labels.get(str(tool), ("Working", "Worked")))
    return 0


def _summary(searches: int, pages: int, duration: float) -> str:
    """Build the muted context footer for a finished answer."""
    parts = ["aieng-bot searched BookStack"]
    if searches:
        parts.append(f"{searches} search{'es' if searches != 1 else ''}")
    if pages:
        parts.append(f"{pages} page{'s' if pages != 1 else ''} read")
    parts.append(f"{duration:.0f}s")
    return "  ·  ".join(parts)
