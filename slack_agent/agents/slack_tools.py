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

from ..reactions import EMOJI_NAME
from ..slack_context import CONTEXT_TAG, SlackContextService

# Expressive reactions are capped per run so the bot never emoji-spams.
_MAX_REACTIONS_PER_RUN = 3

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
    {
        "name": "add_reaction",
        "description": (
            "React to a message in the current channel with an emoji, the "
            "way a teammate would (a tada on a launch, raised hands on a "
            "win). Use sparingly: only when a human would naturally react."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "emoji": {
                    "type": "string",
                    "description": "Slack emoji name without colons, e.g. tada.",
                },
                "message_ts": {
                    "type": "string",
                    "description": "Timestamp of the message to react to.",
                },
            },
            "required": ["emoji", "message_ts"],
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
    "add_reaction": ("Adding a reaction", "Added a reaction"),
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
</slack_context_tools>

<reaction>
You may react to specific messages with the add_reaction tool, the way a
teammate would: a tada under a launch announcement you read, raised_hands
under a win, pray under a thank-you. At most a couple per conversation,
and only when a human would naturally react; most messages get none.

Separately, end your answer with one final line exactly of the form:
reaction: <slack_emoji_name>
Pick the reaction a friendly teammate would leave on the user's message:
white_check_mark for completed tasks or solid answers, wave for
greetings, tada for good news or launches, raised_hands for thanks or
wins, thinking_face when you are unsure, sweat_smile when apologizing,
eyes for intriguing questions, or any other standard Slack emoji that
fits the mood. This line is stripped before your answer is shown; it
never appears to the user.
</reaction>"""


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
    reactions_used = 0

    async def channel_history(tool_input: dict[str, Any]) -> str:
        limit = max(1, min(int(tool_input.get("limit", 30)), 100))
        oldest = str(tool_input["oldest"]) if tool_input.get("oldest") else None
        return await service.history_text(channel, limit, oldest)

    async def thread_replies(tool_input: dict[str, Any]) -> str:
        thread_ts = str(tool_input.get("thread_ts", "")).strip()
        if not thread_ts:
            return "Error: thread_ts is required"
        return await service.thread_text(channel, thread_ts)

    async def reaction(tool_input: dict[str, Any]) -> str:
        nonlocal reactions_used
        emoji = str(tool_input.get("emoji", "")).strip().strip(":").lower()
        message_ts = str(tool_input.get("message_ts", "")).strip()
        if not EMOJI_NAME.fullmatch(emoji) or not message_ts:
            return "Error: a valid emoji name and message_ts are required"
        if reactions_used >= _MAX_REACTIONS_PER_RUN:
            return "Error: reaction limit reached for this run"
        reactions_used += 1
        return await service.add_reaction(channel, message_ts, emoji)

    tool_handlers: dict[str, Callable[[dict[str, Any]], Awaitable[str]]] = {
        "get_channel_history": channel_history,
        "get_thread_replies": thread_replies,
        "add_reaction": reaction,
    }

    async def execute(name: str, tool_input: dict[str, Any]) -> str:
        handler = tool_handlers.get(name)
        if handler is None:
            return f"Unknown tool: {name}"
        try:
            return await handler(tool_input)
        except Exception as exc:  # noqa: BLE001
            return f"Error executing {name}: {exc}"

    return execute
