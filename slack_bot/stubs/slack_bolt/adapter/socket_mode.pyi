"""Type stubs for slack_bolt.adapter.socket_mode."""

from typing import Any

from slack_bolt import App

class SocketModeHandler:
    """Socket Mode Handler for Slack Bolt."""

    def __init__(self, app: App, app_token: str | None = None, **kwargs: Any) -> None: ...
    def start(self) -> None: ...
