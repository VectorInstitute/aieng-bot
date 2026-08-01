"""Unit tests for orchestrator routing (keywords + sticky sessions)."""

from unittest.mock import AsyncMock

import pytest

from slack_agent.agents.orchestrator import Orchestrator
from slack_agent.context import ThreadContext


class _DummyAgent:
    """Minimal SubAgent implementation recording handle() calls."""

    def __init__(self, name: str, keywords: frozenset[str]) -> None:
        self.name = name
        self.description = f"{name} agent"
        self.keywords = keywords
        self.calls: list[str] = []

    async def handle(self, question, context, reply, principal=None):  # noqa: ANN001, D102
        self.calls.append(question)
        return "white_check_mark"


def _bookstack() -> _DummyAgent:
    return _DummyAgent("bookstack", frozenset({"wiki", "docs", "cluster"}))


def _github() -> _DummyAgent:
    return _DummyAgent("github", frozenset({"github", "repo", "pr", "ci"}))


def _context() -> ThreadContext:
    return ThreadContext(channel="C1", thread_ts="1.0")


def test_single_agent_needs_no_classification() -> None:
    """With one agent registered, routing is direct."""
    agent = _bookstack()
    orchestrator = Orchestrator([agent])

    assert orchestrator.route("anything at all", _context()) is agent


def test_keywords_route_to_the_matching_domain() -> None:
    """A GitHub-shaped question reaches the GitHub agent."""
    bookstack, github = _bookstack(), _github()
    orchestrator = Orchestrator([bookstack, github])

    chosen = orchestrator.route("is CI passing on the aieng-bot repo?", _context())

    assert chosen is github


def test_unmatched_questions_fall_back_to_the_first_agent() -> None:
    """No keyword hits picks the first registered agent."""
    bookstack, github = _bookstack(), _github()
    orchestrator = Orchestrator([bookstack, github])

    chosen = orchestrator.route("what is the leave policy?", _context())

    assert chosen is bookstack


def test_sticky_sessions_override_keywords() -> None:
    """A thread already served by an agent stays with it."""
    bookstack, github = _bookstack(), _github()
    orchestrator = Orchestrator([bookstack, github])
    context = _context()
    context.active_agent = "bookstack"
    context.agent_history = [{"role": "user", "content": "hi"}]

    chosen = orchestrator.route("and what about the repo CI?", context)

    assert chosen is bookstack


def test_sticky_needs_history_fresh_threads_reclassify() -> None:
    """A persisted agent name without history does not pin routing."""
    bookstack, github = _bookstack(), _github()
    orchestrator = Orchestrator([bookstack, github])
    context = _context()
    context.active_agent = "bookstack"

    chosen = orchestrator.route("is the github CI green?", context)

    assert chosen is github


@pytest.mark.asyncio
async def test_handle_records_the_active_agent() -> None:
    """Routing decisions persist on the context for sticky follow-ups."""
    bookstack, github = _bookstack(), _github()
    orchestrator = Orchestrator([bookstack, github])
    context = _context()
    reply = AsyncMock()

    reaction = await orchestrator.handle("show me the repo PRs", context, reply)

    assert reaction == "white_check_mark"
    assert context.active_agent == "github"
    assert github.calls == ["show me the repo PRs"]


@pytest.mark.asyncio
async def test_handle_with_no_agents_fails_the_reply() -> None:
    """An empty roster reports failure instead of crashing."""
    orchestrator = Orchestrator([])
    reply = AsyncMock()

    result = await orchestrator.handle("hello", _context(), reply)

    assert result is None
    reply.fail.assert_awaited_once()
