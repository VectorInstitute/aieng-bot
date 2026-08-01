"""Orchestrator: routes each request to the right specialist sub-agent.

The orchestrator is the single entry point the Slack handlers talk to. It
owns the roster of sub-agents and decides which one serves a request; the
chosen sub-agent runs its own LLM loop and streams into the reply.

Routing is two cheap rules, no extra LLM call:

1. **Sticky sessions** — a thread that already has agent history stays
   with the agent serving it, so follow-ups never switch domains (and
   never hand one agent's tool history to another).
2. **Keyword scoring** — a fresh session goes to the agent whose
   ``keywords`` hints match the question best; no match falls back to
   the first registered agent (BookStack, the broadest domain).

When keyword scoring proves too coarse, this is the one place to swap
in a classifier call over the sub-agents' ``description`` fields.
"""

import logging
import re

from ..authorization import ANONYMOUS, Principal
from ..context import ThreadContext
from ..streaming import StreamingReply
from .base import SubAgent

logger = logging.getLogger(__name__)

_WORDS = re.compile(r"[a-z0-9_]+")


class Orchestrator:
    """Dispatches user requests to specialist sub-agents.

    Parameters
    ----------
    agents : list[SubAgent]
        Available sub-agents in registration order; the first is the
        fallback for questions no agent's keywords claim.

    """

    def __init__(self, agents: list[SubAgent]) -> None:
        """Store the sub-agent roster."""
        self._agents = agents

    @property
    def agent_names(self) -> list[str]:
        """Return the names of all registered sub-agents."""
        return [a.name for a in self._agents]

    def route(self, question: str, context: ThreadContext) -> SubAgent | None:
        """Pick the sub-agent that should serve *question*.

        Parameters
        ----------
        question : str
            The user's question.
        context : ThreadContext
            Thread context; a session already served by an agent stays
            with it (sticky routing).

        Returns
        -------
        SubAgent or None
            The chosen sub-agent, or None if none are registered.

        """
        if not self._agents:
            return None
        if len(self._agents) == 1:
            return self._agents[0]

        if context.agent_history and context.active_agent:
            for agent in self._agents:
                if agent.name == context.active_agent:
                    return agent

        return self._classify(question)

    def _classify(self, question: str) -> SubAgent:
        """Score agents by keyword hits; ties and no-hits pick the first."""
        words = frozenset(_WORDS.findall(question.lower()))
        best = self._agents[0]
        best_score = 0
        for agent in self._agents:
            score = len(agent.keywords & words)
            if score > best_score:
                best, best_score = agent, score
        return best

    async def handle(
        self,
        question: str,
        context: ThreadContext,
        reply: StreamingReply,
        principal: Principal = ANONYMOUS,
    ) -> str | None:
        """Route *question* and delegate to the chosen sub-agent.

        Parameters
        ----------
        question : str
            The user's question.
        context : ThreadContext
            Isolated context of the Slack thread.
        reply : StreamingReply
            Renderer for the in-thread reply message.
        principal : Principal
            Who is asking; drives per-principal authorization and
            write provenance in sub-agents.

        Returns
        -------
        str or None
            The sub-agent's chosen reaction emoji name, if any.

        """
        agent = self.route(question, context)
        if agent is None:
            await reply.fail("no agents are configured")
            return None
        # Recorded before the run so the session stays sticky even if
        # this first turn fails midway.
        context.active_agent = agent.name
        logger.info("routing to sub-agent %s", agent.name)
        return await agent.handle(question, context, reply, principal=principal)
