"""aieng-bot Slack agent entrypoint.

Wires settings, per-thread contexts, the orchestrator, and Slack event handlers
together, then runs the Socket Mode connection plus a minimal HTTP health
endpoint (required by Cloud Run).

Run locally from the repo root with ``uv run python -m slack_agent.app``.
"""

import asyncio
import logging
import sys

from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

from . import APP_VERSION
from .agents import build_orchestrator
from .config import Settings
from .context import ContextStore
from .handlers import SlackHandlers
from .slack_context import SlackContextService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("aieng_bot.slack_agent")


def create_app(settings: Settings) -> AsyncApp:
    """Build the Slack Bolt app with all handlers registered.

    Parameters
    ----------
    settings : Settings
        Resolved runtime configuration.

    Returns
    -------
    AsyncApp
        Configured slack_bolt async application.

    """
    store = ContextStore()
    orchestrator = build_orchestrator(settings)
    logger.info(
        "sub-agents enabled: %s",
        ", ".join(orchestrator.agent_names) or "none",
    )

    app = AsyncApp(token=settings.slack_bot_token)
    slack_context = SlackContextService(app.client)
    handlers = SlackHandlers(settings, store, orchestrator, slack_context)
    app.event("app_mention")(handlers.handle_app_mention)
    app.event("message")(handlers.handle_message)
    app.command("/aieng-bot")(handlers.handle_command)
    return app


async def serve_health(port: int, git_sha: str) -> None:
    """Serve a minimal HTTP health endpoint for Cloud Run.

    Cloud Run requires the container to listen on ``$PORT`` even though
    Socket Mode needs no inbound traffic; this answers 200 to any request.

    Parameters
    ----------
    port : int
        TCP port to listen on.
    git_sha : str
        Build SHA reported in the health payload.

    """

    async def handle(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.read(1024)
        body = f'{{"status":"ok","version":"{APP_VERSION}","sha":"{git_sha}"}}'
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


async def run(settings: Settings) -> None:
    """Start the health server and the Socket Mode connection."""
    health_task = asyncio.create_task(serve_health(settings.port, settings.git_sha))
    handler = AsyncSocketModeHandler(create_app(settings), settings.slack_app_token)
    logger.info(
        "aieng-bot v%s (%s) connecting to Slack...",
        APP_VERSION,
        settings.git_sha[:7],
    )
    try:
        await handler.start_async()
    finally:
        health_task.cancel()


def main() -> None:
    """Validate the environment and run the agent."""
    try:
        settings = Settings.from_env()
    except RuntimeError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        logger.info("shutting down")


if __name__ == "__main__":
    main()
