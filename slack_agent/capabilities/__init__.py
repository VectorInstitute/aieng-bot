"""Agent capabilities.

Each capability is one thing the agent can do (answer wiki questions, triage
CI, …). The router picks the first capability that can serve a request, so
new capabilities are added by implementing :class:`~.base.Capability` and
registering them in :func:`build_capabilities` — no plumbing changes.
"""

import logging

from ..config import Settings
from .base import Capability
from .bookstack_qa import BookstackQACapability

logger = logging.getLogger(__name__)


def build_capabilities(settings: Settings) -> list[Capability]:
    """Construct the enabled capabilities in routing priority order.

    Parameters
    ----------
    settings : Settings
        Resolved runtime configuration.

    Returns
    -------
    list[Capability]
        Enabled capabilities; may be empty if none are configured.

    """
    capabilities: list[Capability] = []
    if settings.bookstack_configured:
        capabilities.append(BookstackQACapability(settings))
    else:
        logger.warning(
            "BookStack QA capability disabled: missing LLM or BookStack credentials"
        )
    return capabilities
