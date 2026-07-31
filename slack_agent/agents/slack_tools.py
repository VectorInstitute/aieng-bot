"""On-demand Slack history tools for the agent loop (design layer L3).

The same pattern as the BookStack tools: instead of stuffing channel
history into every prompt, the model calls these tools when a question
references discussion outside the ambient window. Tools are hard-bound
to the channel the question came from, so private-channel data never
crosses channels.
"""

import logging
from collections.abc import Callable
from typing import Any

from anthropic.types import ToolParam
from slack_sdk import WebClient

from ..slack_context import NAME_CACHE, format_message

logger = logging.getLogger(__name__)

_RESULT_CHARS = 8000

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

SLACK_TOOL_NAMES = {t["name"] for t in SLACK_TOOLS}

SYSTEM_SUFFIX = """

<slack_context_tools>
You are working inside a Slack channel. The user message may include a
<slack_context> block with recent messages for orientation.
- Use get_channel_history when the question refers to earlier discussion
  that is not in <slack_context> (for example "what did we decide about X?").
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


def _sync_display_name(client: WebClient, user_id: str) -> str:
    if not user_id:
        return "unknown"
    if user_id not in NAME_CACHE:
        try:
            info: Any = client.users_info(user=user_id)
            profile = info["user"].get("profile", {})
            NAME_CACHE[user_id] = (
                profile.get("display_name")
                or profile.get("real_name")
                or info["user"].get("name")
                or user_id
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("users_info failed for %s: %s", user_id, exc)
            return user_id
    return NAME_CACHE[user_id]


def _render(client: WebClient, messages: list[dict[str, Any]]) -> str:
    lines = []
    for msg in messages:
        if msg.get("subtype"):
            continue
        user = msg.get("user", "")
        name = (
            _sync_display_name(client, user) if user else (msg.get("username") or "app")
        )
        line = format_message(msg.get("ts", ""), name, msg.get("text", ""))
        if msg.get("reply_count"):
            line += f"  (thread with {msg['reply_count']} replies, ts={msg['ts']})"
        lines.append(line)
    return "\n".join(lines)[:_RESULT_CHARS] or "(no messages)"


def build_slack_executor(
    token: str, channel: str, client: WebClient | None = None
) -> Callable[[str, dict[str, Any]], str]:
    """Build a synchronous executor for the Slack tools.

    Parameters
    ----------
    token : str
        Bot token used for Web API calls.
    channel : str
        The only channel the tools may read; bound at request time.
    client : WebClient, optional
        Injected client for tests; a real one is built from *token*
        otherwise.

    Returns
    -------
    Callable
        ``executor(name, tool_input) -> str`` matching the agent loop's
        tool execution convention.

    """
    web = client or WebClient(token=token)

    def execute(name: str, tool_input: dict[str, Any]) -> str:
        try:
            if name == "get_channel_history":
                limit = max(1, min(int(tool_input.get("limit", 30)), 100))
                kwargs: dict[str, Any] = {"channel": channel, "limit": limit}
                if tool_input.get("oldest"):
                    kwargs["oldest"] = str(tool_input["oldest"])
                response: Any = web.conversations_history(**kwargs)
                return _render(web, list(reversed(response.get("messages", []))))

            if name == "get_thread_replies":
                thread_ts = str(tool_input.get("thread_ts", "")).strip()
                if not thread_ts:
                    return "Error: thread_ts is required"
                response = web.conversations_replies(
                    channel=channel, ts=thread_ts, limit=50
                )
                return _render(web, list(response.get("messages", [])))

            return f"Unknown tool: {name}"
        except Exception as exc:  # noqa: BLE001
            return f"Error executing {name}: {exc}"

    return execute
