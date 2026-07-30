"""Capability interface."""

from typing import Protocol

from ..context import ThreadContext
from ..streaming import StreamingReply


class Capability(Protocol):
    """One thing the agent can do in response to a user request.

    Implementations receive the user's question, the thread's context (for
    multi-turn history), and a :class:`StreamingReply` to render progress and
    the final answer into Slack.
    """

    name: str

    async def handle(
        self, question: str, context: ThreadContext, reply: StreamingReply
    ) -> None:
        """Answer *question* in *context*, rendering into *reply*.

        Parameters
        ----------
        question : str
            The user's question, with any bot mention stripped.
        context : ThreadContext
            Isolated context of the Slack thread.
        reply : StreamingReply
            Renderer for the in-thread reply message.

        """
        ...
