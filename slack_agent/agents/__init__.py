"""The agent layer: an orchestrator delegating to specialist sub-agents.

New sub-agents implement :class:`~.base.SubAgent` and register in
:func:`build_orchestrator` — the Slack plumbing does not change.
"""

import logging

from ..config import Settings
from .base import SubAgent
from .bookstack import BookstackSubAgent
from .orchestrator import Orchestrator

logger = logging.getLogger(__name__)


def build_orchestrator(settings: Settings) -> Orchestrator:
    """Construct the orchestrator with all configured sub-agents.

    Parameters
    ----------
    settings : Settings
        Resolved runtime configuration.

    Returns
    -------
    Orchestrator
        Orchestrator over the enabled sub-agents (possibly none).

    """
    agents: list[SubAgent] = []
    if settings.bookstack_configured:
        agents.append(BookstackSubAgent(settings))
    else:
        logger.warning(
            "bookstack sub-agent disabled: missing LLM or BookStack credentials"
        )
    return Orchestrator(agents)
