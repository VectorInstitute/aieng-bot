"""Slack bot for aieng-bot-maintain.

This bot provides Slack slash commands to interact with the aieng-bot-maintain
project and get information about bot activity.
"""

import os
import sys
from importlib.metadata import version as get_pkg_version
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from slack_bolt import Ack, App, Respond, Say
from slack_bolt.adapter.socket_mode import SocketModeHandler

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path to import from aieng_bot_maintain
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aieng_bot_maintain.utils.logging import (  # noqa: E402
    log_error,
    log_info,
    log_success,
)

# Initialize the Slack app with bot token and signing secret
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)


def get_version_info() -> dict[str, str]:
    """Get version and metadata information about aieng-bot-maintain.

    Returns
    -------
    dict[str, str]
        Dictionary containing version and metadata information.

    """
    try:
        version = get_pkg_version("aieng-bot-maintain")
    except Exception:
        version = "unknown"

    return {
        "version": version,
        "project": "aieng-bot-maintain",
        "description": "Vector Institute AI Engineering Bot for Maintenance Tasks",
        "repository": "https://github.com/VectorInstitute/aieng-bot-maintain",
        "dashboard": "https://catalog.vectorinstitute.ai/aieng-bot-maintain",
    }


@app.command("/aieng-bot")
def handle_aieng_bot_command(ack: Ack, respond: Respond, command: dict) -> None:
    """Handle /aieng-bot slash command.

    Parameters
    ----------
    ack : callable
        Acknowledge function to confirm receipt of the command.
    respond : callable
        Function to send response to the channel.
    command : dict
        Command payload containing text and other metadata.

    """
    # Acknowledge command request immediately
    ack()

    # Extract the subcommand from the text
    text = command.get("text", "").strip().lower()

    if text in {"version", ""}:
        # Get version information
        info = get_version_info()

        # Format response as a rich block layout
        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🤖 AI Engineering Maintenance Bot",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Version:*\n{info['version']}"},
                    {"type": "mrkdwn", "text": f"*Project:*\n{info['project']}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Description:*\n{info['description']}",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Links:*",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"<{info['repository']}|📦 Repository>",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"<{info['dashboard']}|📊 Dashboard>",
                    },
                ],
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "_Maintaining Vector Institute Repositories built by AI Engineering_",
                    }
                ],
            },
        ]

        respond(blocks=blocks)
    else:
        # Unknown subcommand
        respond(
            f"Unknown command: `{text}`\n\n"
            "Available commands:\n"
            "• `/aieng-bot version` - Display version and metadata information"
        )


@app.event("app_mention")
def handle_app_mention(event: dict, say: Say) -> None:
    """Handle app mentions in channels.

    Parameters
    ----------
    event : dict
        Event payload containing mention details.
    say : callable
        Function to send response to the channel.

    """
    user = event["user"]
    say(f"Hi <@{user}>! Use `/aieng-bot version` to get information about the bot.")


def main() -> None:
    """Start the Slack bot in Socket Mode."""
    # Validate required environment variables
    required_vars = ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_SIGNING_SECRET"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]

    if missing_vars:
        log_error(f"Missing required environment variables: {', '.join(missing_vars)}")
        log_info("Please set these variables in your .env file or environment")
        sys.exit(1)

    log_info("Starting AI Engineering Maintenance Bot...")

    try:
        # Start the app using Socket Mode
        handler = SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN"))
        log_success("⚡️ AI Engineering Maintenance Bot is running!")
        log_info("Press Ctrl+C to stop")
        handler.start()
    except KeyboardInterrupt:
        log_info("Shutting down bot...")
    except Exception as e:
        log_error(f"Failed to start bot: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
