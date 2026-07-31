"""Sub-agent interface."""

from typing import Protocol

from ..context import ThreadContext
from ..streaming import StreamingReply


class SubAgent(Protocol):
    """A specialist agent the orchestrator can delegate a request to.

    Each sub-agent owns one domain (BookStack documentation, GitHub, CI, …),
    runs its own LLM loop with its own tools, and renders its progress and
    final answer into the thread's :class:`StreamingReply`.
    """

    name: str
    description: str

    async def handle(
        self, question: str, context: ThreadContext, reply: StreamingReply
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

        Returns
        -------
        str or None
            Slack emoji name the agent chose as its reaction to the
            user's message, or None for the default.

        """
        ...
