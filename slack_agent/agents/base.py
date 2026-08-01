"""Sub-agent interface."""

from typing import Protocol

from ..authorization import ANONYMOUS, Principal
from ..context import ThreadContext
from ..streaming import StreamingReply


class SubAgent(Protocol):
    """A specialist agent the orchestrator can delegate a request to.

    Each sub-agent owns one domain (BookStack documentation, GitHub, CI, …),
    runs its own LLM loop with its own tools, and renders its progress and
    final answer into the thread's :class:`StreamingReply`.

    ``keywords`` are routing hints: lowercase terms whose presence in a
    question signals this agent's domain. The orchestrator scores agents
    by keyword hits and falls back to the first registered agent.
    """

    name: str
    description: str
    keywords: frozenset[str]

    async def handle(
        self,
        question: str,
        context: ThreadContext,
        reply: StreamingReply,
        principal: Principal = ANONYMOUS,
    ) -> str | None:
        """Answer *question* in *context*, rendering into *reply*.

        Parameters
        ----------
        question : str
            The user's question, with any bot mention stripped.
        context : ThreadContext
            Isolated context of the Slack thread.
        reply : StreamingReply
            Renderer for the in-thread reply message.
        principal : Principal
            Who is asking. Sub-agents must derive their tool roster
            from it (via the access policy) and use it for provenance
            on any write action.

        Returns
        -------
        str or None
            Slack emoji name the agent chose as its reaction to the
            user's message, or None for the default.

        """
        ...
