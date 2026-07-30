"""aieng-bot Slack agent — Socket Mode scaffold.

Phase 1: a dummy agent that proves out the plumbing before any
intelligence is wired in:

- separate conversation contexts per channel/thread (and per DM)
- background listening in channels the bot is invited to
- responses when @mentioned or messaged directly
- a ``/aieng-bot version`` command that reports the running build,
  so auto-deploys from ``main`` can be verified in Slack

The ``respond_to`` function is the placeholder "brain" — replace it
with the real agent layer (Claude Agent SDK, Managed Agents, or a
custom harness) without touching the Slack plumbing around it.
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncAck, AsyncApp, AsyncRespond, AsyncSay

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("aieng_bot.slack_agent")

APP_VERSION = "0.1.0"
GIT_SHA = os.environ.get("GIT_SHA", "dev")


@dataclass
class ThreadContext:
    """Conversation context for a single Slack thread (or DM thread).

    Attributes
    ----------
    channel : str
        Channel ID the thread lives in.
    thread_ts : str
        Timestamp of the thread's root message (the message's own ``ts``
        for top-level messages).
    messages : list[dict[str, str]]
        Messages recorded in this thread, each with ``user`` and ``text``.

    """

    channel: str
    thread_ts: str
    messages: list[dict[str, str]] = field(default_factory=list)

    @property
    def users(self) -> set[str]:
        """Return the set of user IDs that have posted in this thread."""
        return {m["user"] for m in self.messages}


class ContextStore:
    """In-memory store of per-thread conversation contexts.

    Keyed by ``(channel, thread_ts)`` so every channel thread and DM
    gets an isolated context — the same model Claude Tag uses. This is
    a phase-1 placeholder; swap for persistent storage (or agent-side
    sessions) when the real agent layer lands.
    """

    def __init__(self) -> None:
        """Initialize an empty store."""
        self._contexts: dict[tuple[str, str], ThreadContext] = {}

    def get(self, channel: str, thread_ts: str) -> ThreadContext:
        """Return the context for a thread, creating it if needed.

        Parameters
        ----------
        channel : str
            Channel ID.
        thread_ts : str
            Thread root timestamp.

        Returns
        -------
        ThreadContext
            The (possibly new) context for the thread.

        """
        key = (channel, thread_ts)
        if key not in self._contexts:
            self._contexts[key] = ThreadContext(channel=channel, thread_ts=thread_ts)
        return self._contexts[key]

    def record(self, event: dict[str, Any]) -> ThreadContext:
        """Record a message event into its thread's context.

        Parameters
        ----------
        event : dict
            Slack message event payload.

        Returns
        -------
        ThreadContext
            The context the message was recorded into.

        """
        channel = event["channel"]
        thread_ts = event.get("thread_ts") or event["ts"]
        context = self.get(channel, thread_ts)
        context.messages.append(
            {"user": event.get("user", "unknown"), "text": event.get("text", "")}
        )
        return context

    def __len__(self) -> int:
        """Return the number of tracked thread contexts."""
        return len(self._contexts)


store = ContextStore()


def respond_to(context: ThreadContext, text: str, user: str) -> str:
    """Produce a reply for a message — the placeholder agent brain.

    Parameters
    ----------
    context : ThreadContext
        Isolated context of the thread the message arrived in.
    text : str
        The incoming message text.
    user : str
        Slack user ID of the sender.

    Returns
    -------
    str
        Reply text posted back to the thread.

    """
    return (
        f"Hi <@{user}>! I'm *aieng-bot* `v{APP_VERSION}` (build `{GIT_SHA[:7]}`). "
        "My agent layer isn't wired up yet — but the plumbing works:\n"
        f"• This thread's context: `{context.channel}:{context.thread_ts}` — "
        f"{len(context.messages)} message(s) from {len(context.users)} user(s), "
        "isolated from every other thread.\n"
        f"• You said: _{text[:200]}_"
    )


async def handle_message(event: dict[str, Any], say: AsyncSay) -> None:
    """Record channel/DM messages; reply only in DMs.

    This is the "listen in the background" path: every message in a
    channel the bot has been invited to is recorded into its thread's
    context, but the bot stays silent unless @mentioned or DMed.

    Parameters
    ----------
    event : dict
        Slack message event payload.
    say : AsyncSay
        Function to post a message to the same conversation.

    """
    if event.get("bot_id") or event.get("subtype"):
        return

    context = store.record(event)
    logger.info(
        "recorded message in %s:%s (%d msgs, %d threads tracked)",
        context.channel,
        context.thread_ts,
        len(context.messages),
        len(store),
    )

    if event.get("channel_type") == "im":
        reply = respond_to(context, event.get("text", ""), event.get("user", ""))
        await say(text=reply, thread_ts=event.get("thread_ts"))


async def handle_app_mention(event: dict[str, Any], say: AsyncSay) -> None:
    """Reply in-thread when the bot is @mentioned in a channel.

    Parameters
    ----------
    event : dict
        Slack ``app_mention`` event payload.
    say : AsyncSay
        Function to post a message to the same conversation.

    """
    thread_ts = event.get("thread_ts") or event["ts"]
    context = store.get(event["channel"], thread_ts)
    reply = respond_to(context, event.get("text", ""), event.get("user", ""))
    await say(text=reply, thread_ts=thread_ts)


async def handle_command(
    ack: AsyncAck, respond: AsyncRespond, command: dict[str, Any]
) -> None:
    """Handle the ``/aieng-bot`` slash command.

    Parameters
    ----------
    ack : AsyncAck
        Acknowledge function confirming receipt to Slack.
    respond : AsyncRespond
        Function to send an (ephemeral) response.
    command : dict
        Slash command payload.

    """
    await ack()
    text = command.get("text", "").strip().lower()

    if text in {"version", ""}:
        await respond(
            f"*aieng-bot* `v{APP_VERSION}` — build `{GIT_SHA}`\n"
            f"Tracking {len(store)} thread context(s) since last restart.\n"
            "<https://github.com/VectorInstitute/aieng-bot|Repository>"
        )
    else:
        await respond(
            f"Unknown command: `{text}`\n"
            "Available: `/aieng-bot version` — show the running build"
        )


def create_app() -> AsyncApp:
    """Build the Slack Bolt app and register event handlers.

    Returns
    -------
    AsyncApp
        Configured slack_bolt async application.

    """
    app = AsyncApp(token=os.environ["SLACK_BOT_TOKEN"])
    app.event("app_mention")(handle_app_mention)
    app.event("message")(handle_message)
    app.command("/aieng-bot")(handle_command)
    return app


async def serve_health(port: int) -> None:
    """Serve a minimal HTTP health endpoint for Cloud Run.

    Cloud Run requires the container to listen on ``$PORT`` even though
    Socket Mode needs no inbound traffic; this answers 200 to any request.

    Parameters
    ----------
    port : int
        TCP port to listen on.

    """

    async def handle(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.read(1024)
        body = f'{{"status":"ok","version":"{APP_VERSION}","sha":"{GIT_SHA}"}}'
        writer.write(
            (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
                f"{body}"
            ).encode()
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "0.0.0.0", port)
    logger.info("health endpoint listening on :%d", port)
    async with server:
        await server.serve_forever()


async def run() -> None:
    """Start the health server and the Socket Mode connection."""
    port = int(os.environ.get("PORT", "8080"))
    health_task = asyncio.create_task(serve_health(port))
    handler = AsyncSocketModeHandler(create_app(), os.environ["SLACK_APP_TOKEN"])
    logger.info("aieng-bot v%s (%s) connecting to Slack...", APP_VERSION, GIT_SHA[:7])
    try:
        await handler.start_async()
    finally:
        health_task.cancel()


def main() -> None:
    """Validate the environment and run the agent."""
    missing = [
        var for var in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN") if not os.environ.get(var)
    ]
    if missing:
        logger.error("missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("shutting down")


if __name__ == "__main__":
    main()
