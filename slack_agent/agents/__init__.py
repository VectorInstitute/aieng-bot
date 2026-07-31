"""The agent layer: an orchestrator delegating to specialist sub-agents.

New sub-agents implement :class:`~.base.SubAgent` and register in
:func:`build_orchestrator` — the Slack plumbing does not change.
"""

import logging

from ..config import Settings
from ..slack_context import SlackContextService
from .base import SubAgent
from .bookstack import BookstackSubAgent
from .orchestrator import Orchestrator

logger = logging.getLogger(__name__)


def build_orchestrator(
    settings: Settings, slack_context: SlackContextService
) -> Orchestrator:
    """Construct the orchestrator with all configured sub-agents.

    Parameters
    ----------
    settings : Settings
        Resolved runtime configuration.
    slack_context : SlackContextService
        Shared Slack context service for the history tools.

    Returns
    -------
    Orchestrator
        Orchestrator over the enabled sub-agents (possibly none).

    """
    agents: list[SubAgent] = []
    if settings.bookstack_configured:
        agents.append(BookstackSubAgent(settings, slack_context))
    else:
        logger.warning(
            "bookstack sub-agent disabled: missing LLM or BookStack credentials"
        )
    return Orchestrator(agents)
