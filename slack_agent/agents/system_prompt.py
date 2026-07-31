"""System prompt assembly for sub-agents.

The prompt is composed from structured sections instead of hand-joined
strings so that what the model believes about itself cannot drift from
what the harness actually provides:

- The ``<identity>`` and ``<capabilities>`` sections are generated from
  the exact tool definitions sent to the API, so the capability manifest
  is always true by construction.
- Every tool must declare an access level (``read`` or ``write``) in its
  module's ``TOOL_ACCESS`` registry. A tool without a declaration fails
  prompt assembly at import time, before it can ever be described
  wrongly at runtime.
- Assembly is deterministic (stable section and tool ordering), which
  keeps the prompt byte-identical across requests and therefore
  cache-friendly.

Domain behavior (search strategy, response format, Slack etiquette)
stays in per-agent section strings; this module owns only identity,
capabilities, and their composition.
"""

from collections.abc import Mapping, Sequence
from typing import Any

_ACCESS_LEVELS = frozenset({"read", "write"})

IDENTITY = """\
<identity>
You are aieng-bot, Vector Institute's internal Slack assistant. You help
staff by answering questions from the internal BookStack wiki and the
current Slack channel's history. You are not a general-purpose agent:
the tools listed in <capabilities> are everything you can do.
</identity>"""


def _summary(description: str) -> str:
    """First sentence of a tool description, for the capability manifest."""
    first = description.split(". ", maxsplit=1)[0].strip()
    return first if first.endswith(".") else f"{first}."


def _render_capabilities(
    tools: Sequence[Mapping[str, Any]], access: Mapping[str, str]
) -> str:
    """Render the <capabilities> section from the actual tool roster."""
    read_lines = [
        f"- {t['name']}: {_summary(str(t['description']))}"
        for t in tools
        if access[str(t["name"])] == "read"
    ]
    write_lines = [
        f"- {t['name']}: {_summary(str(t['description']))}"
        for t in tools
        if access[str(t["name"])] == "write"
    ]

    parts = ["<capabilities>", "Read-only tools:", *read_lines]
    if write_lines:
        parts += ["", "Actions (the only ways you can change anything):", *write_lines]
        boundary = (
            "Beyond the actions listed above, you cannot change anything in any system."
        )
    else:
        boundary = (
            "All of your tools are read-only. You cannot create, modify, or "
            "delete anything in any system."
        )
    parts += [
        "",
        f"This list is complete; there are no hidden abilities. {boundary}",
        "The products behind these tools (BookStack, Slack) have many",
        "features you do not have access to, so never infer an ability from",
        "general knowledge about those products: if a tool for something is",
        "not listed above, you cannot do it.",
        "",
        "When asked what you can or cannot do, answer in plain language from",
        "the list above alone. If something is not listed, say plainly that",
        "you cannot do it and point to the closest capability you do have.",
        "Greetings and questions about you need no wiki search and no",
        "Sources section.",
        "</capabilities>",
    ]
    return "\n".join(parts)


def build_system_prompt(
    tools: Sequence[Mapping[str, Any]],
    access: Mapping[str, str],
    sections: Sequence[str],
    identity: str = IDENTITY,
) -> str:
    """Assemble a sub-agent system prompt.

    Parameters
    ----------
    tools : list of dict
        The exact Anthropic tool definitions the agent will be given.
    access : dict
        Access level (``"read"`` or ``"write"``) per tool name. Every
        tool must be declared; assembly fails otherwise so a new tool
        cannot ship undescribed.
    sections : list of str
        Domain sections (strategy, response format, etiquette) appended
        after identity and capabilities, in order.
    identity : str, optional
        The ``<identity>`` block; defaults to the aieng-bot identity.

    Returns
    -------
    str
        The complete system prompt.

    Raises
    ------
    ValueError
        If a tool has no access declaration or an unknown access level.

    """
    names = [str(t["name"]) for t in tools]
    undeclared = [n for n in names if n not in access]
    if undeclared:
        raise ValueError(
            f"tools missing an access declaration: {', '.join(undeclared)}"
        )
    invalid = sorted({access[n] for n in names} - _ACCESS_LEVELS)
    if invalid:
        raise ValueError(f"unknown access levels: {', '.join(invalid)}")

    blocks = [identity, _render_capabilities(tools, access)]
    blocks += [s.strip() for s in sections if s.strip()]
    return "\n\n".join(blocks)
