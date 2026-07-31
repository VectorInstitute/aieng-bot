"""Type stubs for slack_bolt.adapter.socket_mode.async_handler."""

from typing import Any

from slack_bolt.async_app import AsyncApp

class AsyncSocketModeHandler:
    """Async Socket Mode handler for Slack Bolt."""

    def __init__(
        self, app: AsyncApp, app_token: str | None = None, **kwargs: Any
    ) -> None: ...
    async def start_async(self) -> None: ...
    async def close_async(self) -> None: ...
