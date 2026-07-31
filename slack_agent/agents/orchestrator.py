"""Orchestrator: routes each request to the right specialist sub-agent.

The orchestrator is the single entry point the Slack handlers talk to. It
owns the roster of sub-agents and decides which one serves a request; the
chosen sub-agent runs its own LLM loop and streams into the reply.

Routing today is trivial because one sub-agent exists (BookStack QA).
When a second sub-agent lands, :meth:`Orchestrator.route` grows a real
dispatcher — cheap heuristics or a small classifier call over the
sub-agents' ``description`` fields — without any change to the Slack
plumbing or to the sub-agents themselves.
"""

import logging

from ..authorization import ANONYMOUS, Principal
from ..context import ThreadContext
from ..streaming import StreamingReply
from .base import SubAgent

logger = logging.getLogger(__name__)


class Orchestrator:
    """Dispatches user requests to specialist sub-agents.

    Parameters
    ----------
    agents : list[SubAgent]
        Available sub-agents in registration order.

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

        With a single registered sub-agent the choice is direct. With
        several, this becomes the dispatch point: classify the question
        against each agent's ``description`` and pick the best match.

        Parameters
        ----------
        question : str
            The user's question.
        context : ThreadContext
            Thread context (may inform routing, e.g. sticky routing to the
            agent already active in the thread).

        Returns
        -------
        SubAgent or None
            The chosen sub-agent, or None if none are registered.

        """
        if not self._agents:
            return None
        return self._agents[0]

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
        logger.info("routing to sub-agent %s", agent.name)
        return await agent.handle(question, context, reply, principal=principal)
