"""Type stubs for slack_bolt."""

from typing import Any, Callable

class App:
    """Slack Bolt App class."""

    def __init__(
        self,
        *,
        token: str | None = None,
        signing_secret: str | None = None,
        **kwargs: Any,
    ) -> None: ...
    def command(self, command: str) -> Callable[[Any], Any]: ...
    def event(self, event: str) -> Callable[[Any], Any]: ...

class Ack:
    """Acknowledge function type."""

    def __call__(self) -> None: ...

class Respond:
    """Respond function type."""

    def __call__(self, text: str | None = None, *, blocks: list[dict[str, Any]] | None = None, **kwargs: Any) -> None: ...

class Say:
    """Say function type."""

    def __call__(self, text: str | None = None, *, blocks: list[dict[str, Any]] | None = None, **kwargs: Any) -> None: ...
