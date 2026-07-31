"""On-demand Slack history tools for the agent loop (design layer L3).

The same pattern as the BookStack tools: instead of stuffing channel
history into every prompt, the model calls these tools when a question
references discussion outside the ambient window. Tools are hard-bound
to the channel the question came from, so private-channel data never
crosses channels. Fetching and rendering are delegated to the shared
:class:`~slack_agent.slack_context.SlackContextService` so the ambient
window (L2) and tool results (L3) always render identically.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from anthropic.types import ToolParam

from ..slack_context import CONTEXT_TAG, SlackContextService

SLACK_TOOLS: list[ToolParam] = [
    {
        "name": "get_channel_history",
        "description": (
            "Fetch recent messages from the current Slack channel, beyond the "
            "context you were given. Use when the question refers to earlier "
            "discussion (decisions, links, requests) not visible in the "
            "provided context. Returns messages oldest first with timestamps."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of messages to fetch (1-100, default 30).",
                    "default": 30,
                },
                "oldest": {
                    "type": "string",
                    "description": (
                        "Optional Slack timestamp; only messages after it are "
                        "returned. Use a ts from earlier results to page back."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_thread_replies",
        "description": (
            "Fetch all replies of one conversation thread in the current "
            "channel. Use a thread_ts from get_channel_history results to "
            "read a discussion in full."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "thread_ts": {
                    "type": "string",
                    "description": "Timestamp of the thread's root message.",
                },
            },
            "required": ["thread_ts"],
        },
    },
]

# Progress-checklist labels for these tools, kept beside the definitions.
STEP_LABELS: dict[str, tuple[str, str]] = {
    "get_channel_history": (
        "Reading recent channel messages",
        "Read recent channel messages",
    ),
    "get_thread_replies": ("Reading a thread", "Read a thread"),
}

SYSTEM_SUFFIX = f"""

<slack_context_tools>
You are working inside a Slack channel. The user message may include a
<{CONTEXT_TAG}> block with recent messages for orientation.
- Use get_channel_history when the question refers to earlier discussion
  that is not in <{CONTEXT_TAG}> (for example "what did we decide about X?").
- Use get_thread_replies with a thread_ts from history results to read one
  conversation in full.
- These tools only see the current channel. Never invent channel history.
- When the question clearly refers to prior discussion, use the tools
  immediately; do not ask the user for permission to look first.
- The most recent message in the history is usually the user's current
  question; do not list it as a prior message.
- Documentation questions still require searching BookStack.
- Synthesize; do not quote long raw history dumps back at the user.
- Never show raw Slack timestamps or ts values (like ts=1785502998.830229)
  to the user; refer to time naturally, e.g. "this morning at 9:03".
- Slack history is not a source: the Sources section is only for wiki
  pages. If the answer used only Slack context, omit Sources entirely.
</slack_context_tools>"""


def build_slack_executor(
    service: SlackContextService, channel: str
) -> Callable[[str, dict[str, Any]], Awaitable[str]]:
    """Build the async executor for the Slack tools.

    Parameters
    ----------
    service : SlackContextService
        Shared context service (one client, one name cache, one renderer).
    channel : str
        The only channel the tools may read; bound at request time.

    Returns
    -------
    Callable
        ``await executor(name, tool_input) -> str`` matching the agent
        loop's extra-tool convention.

    """

    async def execute(name: str, tool_input: dict[str, Any]) -> str:
        try:
            if name == "get_channel_history":
                limit = max(1, min(int(tool_input.get("limit", 30)), 100))
                oldest = str(tool_input["oldest"]) if tool_input.get("oldest") else None
                return await service.history_text(channel, limit, oldest)

            if name == "get_thread_replies":
                thread_ts = str(tool_input.get("thread_ts", "")).strip()
                if not thread_ts:
                    return "Error: thread_ts is required"
                return await service.thread_text(channel, thread_ts)

            return f"Unknown tool: {name}"
        except Exception as exc:  # noqa: BLE001
            return f"Error executing {name}: {exc}"

    return execute
