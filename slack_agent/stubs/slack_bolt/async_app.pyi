"""Type stubs for slack_bolt.async_app."""

from collections.abc import Callable
from typing import Any, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])

class AsyncApp:
    """Slack Bolt async App class."""

    def __init__(
        self,
        *,
        token: str | None = None,
        signing_secret: str | None = None,
        **kwargs: Any,
    ) -> None: ...
    def event(self, event: str | dict[str, str]) -> Callable[[_F], _F]: ...
    def command(self, command: str) -> Callable[[_F], _F]: ...
    @property
    def client(self) -> Any: ...

class AsyncAck:
    """Async acknowledge function type."""

    async def __call__(self, text: str | None = None, **kwargs: Any) -> Any: ...

class AsyncRespond:
    """Async respond function type."""

    async def __call__(
        self,
        text: str | None = None,
        *,
        blocks: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any: ...

class AsyncSay:
    """Async say function type."""

    async def __call__(
        self,
        text: str | None = None,
        *,
        blocks: list[dict[str, Any]] | None = None,
        thread_ts: str | None = None,
        **kwargs: Any,
    ) -> Any: ...
