"""Slack event handlers.

Routing model (mirrors Claude Tag's behavior):

- ``message`` events are recorded into per-thread contexts for all channels
  the bot is invited to (background listening) but never answered — except
  DMs, which are treated as direct questions.
- ``app_mention`` events are direct questions: the bot replies in the
  thread, streaming progress as it works.
- Each thread's agent run is serialized with the thread's lock so two rapid
  questions in one thread cannot interleave their histories.
"""

import logging
import re
from typing import Any

from . import APP_VERSION
from .capabilities.base import Capability
from .config import Settings
from .context import ContextStore, ThreadContext
from .streaming import StreamingReply

logger = logging.getLogger(__name__)

_MENTION = re.compile(r"<@[A-Z0-9]+>")


class SlackHandlers:
    """Event handlers bound to a context store and capability list.

    Parameters
    ----------
    settings : Settings
        Resolved runtime configuration.
    store : ContextStore
        Per-thread context store.
    capabilities : list[Capability]
        Enabled capabilities in routing priority order.

    """

    def __init__(
        self,
        settings: Settings,
        store: ContextStore,
        capabilities: list[Capability],
    ) -> None:
        """Store collaborators."""
        self._settings = settings
        self._store = store
        self._capabilities = capabilities

    # ------------------------------------------------------------------
    # Event handlers (registered in app.py)
    # ------------------------------------------------------------------

    async def handle_message(self, event: dict[str, Any], client: Any) -> None:
        """Record channel/DM messages; treat DMs as direct questions.

        Parameters
        ----------
        event : dict
            Slack message event payload.
        client : Any
            Bolt async web client.

        """
        if event.get("bot_id") or event.get("subtype"):
            return

        context = self._store.record(event)
        logger.info(
            "recorded message in %s:%s (%d msgs, %d threads tracked)",
            context.channel,
            context.thread_ts,
            len(context.messages),
            len(self._store),
        )

        if event.get("channel_type") == "im":
            await self._answer(event, client, context)

    async def handle_app_mention(self, event: dict[str, Any], client: Any) -> None:
        """Answer when the bot is @mentioned in a channel.

        Parameters
        ----------
        event : dict
            Slack ``app_mention`` event payload.
        client : Any
            Bolt async web client.

        """
        thread_ts = event.get("thread_ts") or event["ts"]
        context = self._store.get(event["channel"], thread_ts)
        await self._answer(event, client, context)

    async def handle_command(
        self, ack: Any, respond: Any, command: dict[str, Any]
    ) -> None:
        """Handle the ``/aieng-bot`` slash command.

        Parameters
        ----------
        ack : Any
            Acknowledge function confirming receipt to Slack.
        respond : Any
            Function to send an ephemeral response.
        command : dict
            Slash command payload.

        """
        await ack()
        text = command.get("text", "").strip().lower()
        capability_names = ", ".join(c.name for c in self._capabilities) or "none"

        if text in {"version", ""}:
            await respond(
                f"*aieng-bot* `v{APP_VERSION}` (build `{self._settings.git_sha[:7]}`)\n"
                f"Capabilities: {capability_names}\n"
                f"Tracking {len(self._store)} thread context(s) since last restart."
            )
        else:
            await respond(
                f"Unknown command: `{text}`\n"
                "Available: `/aieng-bot version` — show the running build"
            )

    # ------------------------------------------------------------------
    # Core answer flow
    # ------------------------------------------------------------------

    async def _answer(
        self, event: dict[str, Any], client: Any, context: ThreadContext
    ) -> None:
        """Run the routed capability and stream the reply into the thread."""
        channel = event["channel"]
        thread_ts = event.get("thread_ts") or event["ts"]
        question = _MENTION.sub("", event.get("text", "")).strip()

        if not question:
            await client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=(
                    "Hi! Ask me anything about Vector's documentation, "
                    "e.g. _how do I get access to the cluster?_"
                ),
            )
            return

        capability = self._capabilities[0] if self._capabilities else None
        if capability is None:
            await client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=(
                    f"I'm running (`v{APP_VERSION}`, build "
                    f"`{self._settings.git_sha[:7]}`) but no capabilities are "
                    "configured yet."
                ),
            )
            return

        await _react(client, channel, event["ts"], "eyes")
        posted = await client.chat_postMessage(
            channel=channel, thread_ts=thread_ts, text="_Thinking…_"
        )
        reply = StreamingReply(client, channel, posted["ts"])

        async with context.lock:
            try:
                await capability.handle(question, context, reply)
            except Exception:
                logger.exception("capability %s failed", capability.name)
                await reply.fail("unexpected internal error")
                await _react(client, channel, event["ts"], "warning", remove="eyes")
                return

        await _react(client, channel, event["ts"], "white_check_mark", remove="eyes")


async def _react(
    client: Any, channel: str, ts: str, name: str, remove: str | None = None
) -> None:
    """Add (and optionally swap) a reaction, ignoring failures.

    Reactions are decoration; a missing scope or a duplicate reaction must
    never break the answer flow.
    """
    try:
        if remove:
            await client.reactions_remove(channel=channel, timestamp=ts, name=remove)
        await client.reactions_add(channel=channel, timestamp=ts, name=name)
    except Exception as exc:  # noqa: BLE001
        logger.debug("reaction %s failed: %s", name, exc)
