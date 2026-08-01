"""BookStack QA sub-agent.

Answers documentation questions from the Vector wiki by driving
:class:`~slack_agent.agents.bookstack.agent.BookstackQAAgent` and rendering
its streaming events into the thread's reply. Multi-turn follow-ups work
per thread: the Anthropic message history lives on the thread context.
"""

import asyncio
import logging
import re
import time
from typing import Any

from ...authorization import (
    ALL_LEVELS,
    ANONYMOUS,
    READ_LEVELS,
    AccessPolicy,
    Principal,
)
from ...config import Settings
from ...context import ThreadContext
from ...reactions import NO_REPLY, split_reaction
from ...slack_context import SlackContextService
from ...streaming import StreamingReply
from ..compaction import HistoryCompactor
from ..slack_tools import (
    SLACK_TOOLS,
    STEP_LABELS,
    SYSTEM_SUFFIX,
    build_slack_executor,
)
from ..slack_tools import TOOL_ACCESS as SLACK_TOOL_ACCESS
from ..system_prompt import build_system_prompt
from .agent import BookstackQAAgent
from .prompts import SYSTEM_PROMPT, WRITING_RULES
from .tools import ALL_TOOLS
from .tools import TOOL_ACCESS as BOOKSTACK_TOOL_ACCESS

logger = logging.getLogger(__name__)

_FULL_ACCESS = {**BOOKSTACK_TOOL_ACCESS, **SLACK_TOOL_ACCESS}
_FULL_ROSTER = [*ALL_TOOLS, *SLACK_TOOLS]


def _build_roster(levels: frozenset[str]) -> tuple[list[Any], str]:
    """Tool list and matching system prompt for one set of access levels.

    The roster is the authorization boundary (the API rejects calls to
    tools not in it) and the manifest is generated from that exact
    roster, so an unauthorized principal's agent neither has write
    tools nor claims to. Writing rules ride only with write access.
    """
    tools = [t for t in _FULL_ROSTER if _FULL_ACCESS[str(t["name"])] in levels]
    sections = [SYSTEM_PROMPT]
    if "write" in levels:
        sections.append(WRITING_RULES)
    sections.append(SYSTEM_SUFFIX)
    system = build_system_prompt(tools=tools, access=_FULL_ACCESS, sections=sections)
    return tools, system


# Assembled once at import per access tier (deterministic, so each tier
# stays prompt-cache-friendly). Fails at startup if any tool lacks an
# access declaration.
WRITER_TOOLS, WRITER_SYSTEM = _build_roster(ALL_LEVELS)
READER_TOOLS, READER_SYSTEM = _build_roster(READ_LEVELS)


class BookstackSubAgent:
    """Answer documentation questions from the BookStack wiki."""

    name = "bookstack"
    description = (
        "Answers questions about Vector Institute's internal documentation "
        "(cluster access, onboarding, tooling, processes) by searching the "
        "BookStack wiki."
    )
    # Routing hints consumed by the orchestrator's keyword dispatcher.
    # The wiki agent is also the fallback for unmatched questions, so
    # these only need to win ties against other domains.
    keywords = frozenset(
        {
            "wiki",
            "bookstack",
            "documentation",
            "docs",
            "onboarding",
            "cluster",
            "vaughan",
            "killarney",
            "page",
            "handbook",
        }
    )

    def __init__(
        self,
        settings: Settings,
        slack_context: SlackContextService,
        policy: AccessPolicy | None = None,
    ) -> None:
        """Build the underlying QA agent from settings.

        Parameters
        ----------
        settings : Settings
            Resolved runtime configuration with BookStack credentials.
        slack_context : SlackContextService
            Shared Slack context service powering the history tools.
        policy : AccessPolicy, optional
            Authorization policy; defaults to the environment-derived
            policy (writes disabled unless AGENT_WRITERS is set).

        """
        self._policy = policy or AccessPolicy.from_env()
        self._slack_context = slack_context
        self._agent = BookstackQAAgent(
            base_url=settings.bookstack_url,
            token_id=settings.bookstack_token_id,
            token_secret=settings.bookstack_token_secret,
        )
        self._compactor = HistoryCompactor(
            client=self._agent.async_client,
            model=self._agent.model,
            context_window=settings.context_window_tokens,
        )
        self._background: set[asyncio.Task[None]] = set()

    async def handle(
        self,
        question: str,
        context: ThreadContext,
        reply: StreamingReply,
        principal: Principal = ANONYMOUS,
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
        principal : Principal
            Who is asking; selects the tool roster (write tools only
            for authorized writers) and provides write provenance.

        Returns
        -------
        str or None
            The model's chosen reaction emoji name, if it signed off.

        """
        started = time.monotonic()
        searches = 0
        pages: list[str] = []
        drafting = False

        tools, system = self._roster_for(principal)
        slack_executor = build_slack_executor(self._slack_context, context.channel)
        async for event in self._agent.ask_stream(
            question,
            history=context.agent_history,
            extra_executor=slack_executor,
            system=system,
            tools=tools,
            write_attribution=principal.display_name,
        ):
            event_type = event.get("type")

            if event_type == "tool_use":
                drafting = False
                searches += _begin_tool_step(reply, event)

            elif event_type == "tool_resolve":
                title = str(event.get("page_title", ""))
                if title:
                    tool = str(event.get("tool", "get_page"))
                    if tool == "get_page":
                        pages.append(title)
                    verb = {"create_page": "Created", "update_page": "Updated"}.get(
                        tool, "Read"
                    )
                    reply.complete_step(
                        f"{verb} {title}",
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
                history = list(event.get("history", []))
                context.agent_history = history
                duration = time.monotonic() - started
                footer = (
                    _summary(searches, len(pages), duration)
                    if searches or pages
                    else None
                )
                answer, reaction = split_reaction(str(event.get("text", "")))
                answer = _strip_empty_sources(answer)
                if answer.strip().upper() == NO_REPLY:
                    await reply.delete()
                    reaction = reaction or "thumbsup"
                else:
                    await reply.finalize(answer, footer)
                self._schedule_compaction(context, history)
                return reaction

            elif event_type == "error":
                message = str(event.get("message", "unknown error"))
                logger.error("bookstack sub-agent error: %s", message)
                await reply.fail(message)
                return None

            await reply.flush()

        await reply.fail("the agent returned no answer")
        return None

    def _roster_for(self, principal: Principal) -> tuple[list[Any], str]:
        """Tool roster and system prompt for *principal* per the policy."""
        if self._policy.can_write(principal):
            return WRITER_TOOLS, WRITER_SYSTEM
        return READER_TOOLS, READER_SYSTEM

    def _schedule_compaction(self, context: ThreadContext, history: list[Any]) -> None:
        """Compact *history* in the background, never blocking the thread.

        The turn's reply and reaction are already delivered and the
        thread lock is released before compaction runs, so a follow-up
        question is never kept waiting on a summarization call.
        """
        task = asyncio.create_task(self._compact_later(context, history))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _compact_later(self, context: ThreadContext, history: list[Any]) -> None:
        """Swap in the compacted history unless a newer turn landed first.

        The identity check plus assignment run without an await between
        them, so on the single-threaded event loop the swap is atomic;
        a session that moved on keeps its newer history and simply
        compacts after its own next turn instead.
        """
        try:
            compacted = await self._compactor.compact(history)
        except Exception:  # noqa: BLE001
            logger.exception("background compaction failed")
            return
        if compacted is not history and context.agent_history is history:
            context.agent_history = compacted


# A "Sources" heading with nothing under it (belt to the prompt's braces).
_EMPTY_SOURCES = re.compile(r"\n+\s*(?:#{1,6}\s*|\*\*?)?Sources(?:\*\*?)?:?\s*$")


def _strip_empty_sources(answer: str) -> str:
    """Drop a trailing Sources heading that has no entries beneath it."""
    return _EMPTY_SOURCES.sub("", answer)


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
        "create_page": ("Writing a wiki page", "Wrote a wiki page"),
        "update_page": ("Updating a wiki page", "Updated a wiki page"),
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
