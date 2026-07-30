"""BookStack QA capability.

Answers questions from the Vector wiki by driving
:class:`aieng_bot.bookstack.BookstackQAAgent` and rendering its streaming
events into the thread's :class:`~slack_agent.streaming.StreamingReply`.
Multi-turn follow-ups work per thread: the Anthropic message history is
stored on the :class:`~slack_agent.context.ThreadContext`.
"""

import logging
import time

from aieng_bot.bookstack import BookstackQAAgent

from ..config import Settings
from ..context import ThreadContext
from ..mrkdwn import to_mrkdwn
from ..streaming import StreamingReply

logger = logging.getLogger(__name__)


class BookstackQACapability:
    """Answer documentation questions from the BookStack wiki."""

    name = "bookstack-qa"

    def __init__(self, settings: Settings) -> None:
        """Build the underlying QA agent from settings.

        Parameters
        ----------
        settings : Settings
            Resolved runtime configuration with BookStack credentials.

        """
        self._agent = BookstackQAAgent(
            base_url=settings.bookstack_url,
            token_id=settings.bookstack_token_id,
            token_secret=settings.bookstack_token_secret,
        )

    async def handle(
        self, question: str, context: ThreadContext, reply: StreamingReply
    ) -> None:
        """Answer *question* from the wiki, streaming progress into *reply*.

        Parameters
        ----------
        question : str
            The user's question.
        context : ThreadContext
            Thread context carrying the multi-turn agent history.
        reply : StreamingReply
            Renderer for the in-thread reply message.

        """
        started = time.monotonic()
        searches = 0
        pages: list[str] = []

        async for event in self._agent.ask_stream(
            question, history=context.agent_history
        ):
            event_type = event.get("type")

            if event_type == "tool_use":
                tool = event.get("tool", "")
                tool_input = event.get("input", {})
                reply.resolve_activity()
                if tool == "search_bookstack":
                    searches += 1
                    query = str(tool_input.get("query", ""))[:80]
                    reply.start_activity(f"Searching the wiki for _{query}_")
                elif tool == "get_page":
                    reply.start_activity("Reading a page…")
                elif tool == "list_books":
                    reply.start_activity("Listing wiki books")
                else:
                    reply.start_activity(f"Running {tool}")

            elif event_type == "tool_resolve":
                title = str(event.get("page_title", ""))
                if title:
                    pages.append(title)
                    reply.resolve_activity(f"Read *{title}*")

            elif event_type == "text_chunk":
                reply.resolve_activity()
                reply.append_text(str(event.get("chunk", "")))

            elif event_type == "text_clear":
                reply.clear_text()

            elif event_type == "answer":
                context.agent_history = list(event.get("history", []))
                duration = time.monotonic() - started
                await reply.finalize(
                    to_mrkdwn(str(event.get("text", ""))),
                    footer=_summary(searches, len(pages), duration),
                )
                return

            elif event_type == "error":
                message = str(event.get("message", "unknown error"))
                logger.error("bookstack qa error: %s", message)
                await reply.fail(message)
                return

            await reply.flush()

        await reply.fail("the agent returned no answer")


def _summary(searches: int, pages: int, duration: float) -> str:
    """Build the muted context footer for a finished answer."""
    parts = ["🔍 aieng-bot searched the wiki"]
    if searches:
        parts.append(f"{searches} search{'es' if searches != 1 else ''}")
    if pages:
        parts.append(f"{pages} page{'s' if pages != 1 else ''} read")
    parts.append(f"{duration:.0f}s")
    return "  ·  ".join(parts)
