"""GitHub QA sub-agent.

Answers questions about Vector Institute's GitHub organization by
driving :class:`~slack_agent.agents.github.agent.GithubQAAgent` and
rendering its streaming events into the thread's reply. Multi-turn
follow-ups work per thread: the Anthropic message history lives on the
thread context.

Every GitHub tool is read-only, so the roster is identical for all
principals; the credential itself (a read-only GitHub App installation
token or fine-grained PAT) is the second line of that defense.
"""

import asyncio
import logging
import time
from typing import Any

from ...authorization import ANONYMOUS, READ_LEVELS, Principal
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
from .agent import GithubQAAgent
from .auth import AppInstallationAuth, StaticTokenAuth, TokenProvider
from .prompts import IDENTITY, SYSTEM_PROMPT
from .tools import ALL_TOOLS
from .tools import TOOL_ACCESS as GITHUB_TOOL_ACCESS

logger = logging.getLogger(__name__)

_FULL_ACCESS = {**GITHUB_TOOL_ACCESS, **SLACK_TOOL_ACCESS}
_FULL_ROSTER = [*ALL_TOOLS, *SLACK_TOOLS]

# Assembled once at import (deterministic, so the prompt stays
# prompt-cache-friendly). All GitHub tools are read-level, so one roster
# serves every principal; assembly fails at startup if any tool lacks an
# access declaration.
READER_TOOLS = [t for t in _FULL_ROSTER if _FULL_ACCESS[str(t["name"])] in READ_LEVELS]
READER_SYSTEM = build_system_prompt(
    tools=READER_TOOLS,
    access=_FULL_ACCESS,
    sections=[SYSTEM_PROMPT, SYSTEM_SUFFIX],
    identity=IDENTITY,
    products=("GitHub", "Slack"),
)


def build_auth(settings: Settings) -> TokenProvider:
    """Pick the GitHub credential source from settings.

    App credentials win over a static token: installation tokens are
    short-lived and scoped by the app's own (read-only) permissions,
    while ``GITHUB_TOKEN`` is the local-development fallback.
    """
    if settings.github_app_id and settings.github_app_private_key:
        installation = settings.github_app_installation_id
        return AppInstallationAuth(
            app_id=settings.github_app_id,
            private_key_pem=settings.github_app_private_key,
            org=settings.github_org,
            installation_id=int(installation) if installation else None,
        )
    return StaticTokenAuth(settings.github_token)


class GithubSubAgent:
    """Answer questions about the Vector Institute GitHub organization."""

    name = "github"
    description = (
        "Answers questions about Vector Institute's GitHub organization: "
        "repositories, code, pull requests, issues, and CI status."
    )
    # Routing hints consumed by the orchestrator's keyword dispatcher.
    keywords = frozenset(
        {
            "github",
            "repo",
            "repos",
            "repository",
            "repositories",
            "pr",
            "prs",
            "pull",
            "issue",
            "issues",
            "commit",
            "commits",
            "branch",
            "merge",
            "merged",
            "ci",
            "workflow",
            "workflows",
            "pipeline",
            "build",
            "release",
            "readme",
            "codebase",
            "dependabot",
            "vectorinstitute",
        }
    )

    def __init__(
        self,
        settings: Settings,
        slack_context: SlackContextService,
    ) -> None:
        """Build the underlying QA agent from settings.

        Parameters
        ----------
        settings : Settings
            Resolved runtime configuration with GitHub credentials.
        slack_context : SlackContextService
            Shared Slack context service powering the history tools.

        """
        self._slack_context = slack_context
        self._agent = GithubQAAgent(
            auth=build_auth(settings),
            org=settings.github_org,
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
        """Answer *question* from GitHub, streaming progress into *reply*.

        Parameters
        ----------
        question : str
            The user's question.
        context : ThreadContext
            Thread context carrying the multi-turn agent history.
        reply : StreamingReply
            Renderer for the in-thread reply message.
        principal : Principal
            Who is asking; unused today because every GitHub tool is
            read-only, but part of the sub-agent contract.

        Returns
        -------
        str or None
            The model's chosen reaction emoji name, if it signed off.

        """
        started = time.monotonic()
        lookups = 0
        drafting = False

        slack_executor = build_slack_executor(self._slack_context, context.channel)
        async for event in self._agent.ask_stream(
            question,
            history=context.agent_history,
            extra_executor=slack_executor,
            system=READER_SYSTEM,
            tools=READER_TOOLS,
        ):
            event_type = event.get("type")

            if event_type == "tool_use":
                drafting = False
                lookups += _begin_tool_step(reply, event)

            elif event_type == "tool_resolve":
                title = str(event.get("page_title", ""))
                if title:
                    reply.complete_step(
                        f"Read {title}",
                        source_url=str(event.get("page_url", "")),
                        source_text=title,
                    )

            elif event_type == "text_chunk":
                if lookups and not drafting:
                    reply.begin_step("Drafting answer", "Drafted answer")
                    drafting = True
                reply.append_text(str(event.get("chunk", "")))

            elif event_type == "text_clear":
                reply.clear_text()

            elif event_type == "answer":
                history = list(event.get("history", []))
                context.agent_history = history
                duration = time.monotonic() - started
                footer = _summary(lookups, duration) if lookups else None
                answer, reaction = split_reaction(str(event.get("text", "")))
                if answer.strip().upper() == NO_REPLY:
                    await reply.delete()
                    reaction = reaction or "thumbsup"
                else:
                    await reply.finalize(answer, footer)
                self._schedule_compaction(context, history)
                return reaction

            elif event_type == "error":
                message = str(event.get("message", "unknown error"))
                logger.error("github sub-agent error: %s", message)
                await reply.fail(message)
                return None

            await reply.flush()

        await reply.fail("the agent returned no answer")
        return None

    def _schedule_compaction(self, context: ThreadContext, history: list[Any]) -> None:
        """Compact *history* in the background, never blocking the thread."""
        task = asyncio.create_task(self._compact_later(context, history))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _compact_later(self, context: ThreadContext, history: list[Any]) -> None:
        """Swap in the compacted history unless a newer turn landed first."""
        try:
            compacted = await self._compactor.compact(history)
        except Exception:  # noqa: BLE001
            logger.exception("background compaction failed")
            return
        if compacted is not history and context.agent_history is history:
            context.agent_history = compacted


def _begin_tool_step(reply: StreamingReply, event: dict[str, object]) -> int:
    """Start the checklist step for a tool call; return 1 if it was a GitHub lookup."""
    tool = str(event.get("tool", ""))
    tool_input = event.get("input", {})
    ti = tool_input if isinstance(tool_input, dict) else {}
    repo = str(ti.get("repo", ""))
    number = ti.get("number", "")

    if tool == "search_code":
        query = str(ti.get("query", ""))[:80]
        reply.begin_step(
            f'Searching code for "{query}"', f'Searched code for "{query}"'
        )
        return 1

    labels = {
        "list_repos": ("Listing repositories", "Listed repositories"),
        "get_repo": (f"Reading about {repo}", f"Read about {repo}"),
        "get_file": (
            f"Reading a file in {repo}",
            f"Read a file in {repo}",
        ),
        "list_pull_requests": (
            f"Listing pull requests in {repo}",
            f"Listed pull requests in {repo}",
        ),
        "get_pull_request": (
            f"Reading PR #{number} in {repo}",
            f"Read PR #{number} in {repo}",
        ),
        "list_issues": (f"Listing issues in {repo}", f"Listed issues in {repo}"),
        "get_issue": (
            f"Reading issue #{number} in {repo}",
            f"Read issue #{number} in {repo}",
        ),
        "get_ci_status": (
            f"Checking CI status of {repo}",
            f"Checked CI status of {repo}",
        ),
    }
    if tool in labels:
        reply.begin_step(*labels[tool])
        return 1
    reply.begin_step(*STEP_LABELS.get(tool, ("Working", "Worked")))
    return 0


def _summary(lookups: int, duration: float) -> str:
    """Build the muted context footer for a finished answer."""
    parts = ["aieng-bot searched GitHub"]
    if lookups:
        parts.append(f"{lookups} lookup{'s' if lookups != 1 else ''}")
    parts.append(f"{duration:.0f}s")
    return "  ·  ".join(parts)
