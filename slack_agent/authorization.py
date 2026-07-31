"""Principal-based authorization for agent capabilities.

Anyone in the Slack workspace can talk to the bot, so read tools are
open to all; anything that changes durable content is gated. The layer
is integration-agnostic: it keys off the access level every tool must
declare in its module's ``TOOL_ACCESS`` registry, so a future GitHub or
Drive connector is covered by declaring its tools, with no new policy
code.

Access levels:

- ``read``: open to everyone.
- ``act``: low-risk, reversible actions (an emoji reaction); open to
  everyone.
- ``write``: durable content changes (wiki pages, and later PRs,
  issues, files); only principals on the writer allowlist.

Enforcement happens at the harness boundary, not in the prompt: an
unauthorized principal's agent is given a tool roster without write
tools (the API then rejects any hallucinated call) and a capability
manifest that truthfully omits them.
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

READ_LEVELS = frozenset({"read", "act"})
ALL_LEVELS = frozenset({"read", "act", "write"})

_WRITERS_ENV = "AGENT_WRITERS"


@dataclass(frozen=True)
class Principal:
    """The person behind a request.

    Attributes
    ----------
    user_id : str
        Slack user ID (stable, the authorization key).
    display_name : str
        Human-readable name (used for provenance, never for authz).

    """

    user_id: str
    display_name: str


ANONYMOUS = Principal(user_id="", display_name="")


class AccessPolicy:
    """Grants tool access levels to principals.

    Parameters
    ----------
    writers : frozenset of str
        Slack user IDs allowed to use ``write`` tools. The sentinel
        ``{"*"}`` allows everyone.

    """

    def __init__(self, writers: frozenset[str]) -> None:
        """Store the writer allowlist."""
        self._writers = writers

    @classmethod
    def from_env(cls) -> "AccessPolicy":
        """Build the policy from ``AGENT_WRITERS``.

        Unset or empty means nobody can write (safe default); ``*``
        allows everyone; otherwise a comma-separated list of Slack user
        IDs.
        """
        raw = os.environ.get(_WRITERS_ENV, "")
        writers = frozenset(part.strip() for part in raw.split(",") if part.strip())
        if not writers:
            logger.info("write tools disabled for everyone (%s unset)", _WRITERS_ENV)
        return cls(writers)

    def can_write(self, principal: Principal) -> bool:
        """Return True if *principal* may use write tools."""
        if "*" in self._writers:
            return True
        return bool(principal.user_id) and principal.user_id in self._writers

    def allowed_levels(self, principal: Principal) -> frozenset[str]:
        """Return the access levels granted to *principal*."""
        return ALL_LEVELS if self.can_write(principal) else READ_LEVELS
