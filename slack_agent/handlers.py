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
from .agents.orchestrator import Orchestrator
from .authorization import ANONYMOUS, Principal
from .config import Settings
from .context import ContextStore, ThreadContext, conversation_key
from .reactions import DEFAULT_REACTION
from .slack_context import SlackContextService
from .streaming import StreamingReply

logger = logging.getLogger(__name__)

_MENTION = re.compile(r"<@[A-Z0-9]+>")


class SlackHandlers:
    """Event handlers bound to a context store and the orchestrator.

    Parameters
    ----------
    settings : Settings
        Resolved runtime configuration.
    store : ContextStore
        Per-thread context store.
    orchestrator : Orchestrator
        Agent-layer entry point that routes requests to sub-agents.

    """

    def __init__(
        self,
        settings: Settings,
        store: ContextStore,
        orchestrator: Orchestrator,
        slack_context: SlackContextService,
    ) -> None:
        """Store collaborators."""
        self._settings = settings
        self._store = store
        self._orchestrator = orchestrator
        self._slack_context = slack_context

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
        self._store.persist(context)

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
        context = self._store.get(event["channel"], conversation_key(event))
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
        agent_names = ", ".join(self._orchestrator.agent_names) or "none"

        if text in {"version", ""}:
            await respond(
                f"*aieng-bot* `v{APP_VERSION}` (build `{self._settings.git_sha[:7]}`)\n"
                f"Agents: {agent_names}\n"
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
        """Run the orchestrator and stream the reply into the conversation."""
        channel = event["channel"]
        reply_thread = _reply_thread_ts(event)
        question = _MENTION.sub("", event.get("text", "")).strip()

        if not question:
            await client.chat_postMessage(
                channel=channel,
                thread_ts=reply_thread,
                text=(
                    "Hi! Ask me anything about Vector's documentation, "
                    "e.g. _how do I get access to the cluster?_"
                ),
            )
            return

        if not self._orchestrator.agent_names:
            await client.chat_postMessage(
                channel=channel,
                thread_ts=reply_thread,
                text=(
                    f"I'm running (`v{APP_VERSION}`, build "
                    f"`{self._settings.git_sha[:7]}`) but no agents are "
                    "configured yet."
                ),
            )
            return

        await _react(client, channel, event["ts"], "eyes")
        reply = StreamingReply(
            client,
            channel,
            anchor_ts=event["ts"],
            reply_thread_ts=reply_thread,
            # Native streams are always thread replies, which would force
            # threads in top-level DMs; those keep the inline engine.
            native_allowed=reply_thread is not None
            or event.get("channel_type") != "im",
            recipient_user_id=event.get("user", ""),
            recipient_team_id=event.get("team", ""),
        )
        await reply.start()
        question = await self._enrich_question(event, context, question)

        principal = ANONYMOUS
        if event.get("user"):
            principal = Principal(
                user_id=str(event["user"]),
                display_name=await self._slack_context.display_name(event["user"]),
            )

        async with context.lock:
            try:
                reaction = await self._orchestrator.handle(
                    question, context, reply, principal=principal
                )
            except Exception:
                logger.exception("agent run failed")
                await reply.fail("unexpected internal error")
                await _react(client, channel, event["ts"], "warning", remove="eyes")
                return
            finally:
                self._store.persist(context)

        await _react(
            client, channel, event["ts"], reaction or DEFAULT_REACTION, remove="eyes"
        )

    async def _enrich_question(
        self, event: dict[str, Any], context: ThreadContext, question: str
    ) -> str:
        """Wrap a new channel session's question with ambient context (L2).

        Applies only to the first turn of a channel thread session: DMs are
        their own conversation, and follow-up turns already carry the
        ambient block in the session history.
        """
        if event.get("channel_type") == "im" or context.agent_history:
            return question
        return await self._slack_context.wrap_question(
            channel=event["channel"],
            thread_ts=event.get("thread_ts") or event["ts"],
            exclude_ts=event["ts"],
            asker_id=event.get("user", ""),
            question=question,
        )


def _reply_thread_ts(event: dict[str, Any]) -> str | None:
    """Return where the reply goes.

    DMs answer inline (like a person typing in the conversation) unless
    the user is in an explicit thread; channel replies always thread off
    the mention.
    """
    if event.get("channel_type") == "im":
        thread = event.get("thread_ts")
        return str(thread) if thread else None
    return str(event.get("thread_ts") or event["ts"])


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
