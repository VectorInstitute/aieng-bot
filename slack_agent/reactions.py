"""Model-chosen emoji reactions.

UX intent: the instant 👀 acknowledgment is mechanical (the "seen"
signal must beat the model to the punch), but the completion reaction
is expressive: the model picks the emoji a teammate would leave on the
user's message. The model signs off its answer with a final
``reaction: <emoji_name>`` line; this module strips that line from the
visible answer and validates the emoji name, falling back to a safe
default so a parsing miss never leaks plumbing into the reply.
"""

import re

DEFAULT_REACTION = "white_check_mark"

# Slack emoji-name charset: lowercase alphanumerics, _, +, -, '.
EMOJI_NAME = re.compile(r"[a-z0-9_+'-]{1,50}")

# Final non-empty line of the answer, e.g. "reaction: raised_hands".
# Emoji names are Slack's charset: lowercase alphanumerics, _, +, -, '.
_SIGNOFF = re.compile(r"\n?\s*reaction:\s*:?([a-z0-9_+'-]{1,50}):?\s*$", re.IGNORECASE)


NO_REPLY = "NO_REPLY"

_SIGNOFF_PREFIX = "reaction:"


def visible_stream_text(text: str) -> str:
    """Mask protocol tokens while text is still streaming.

    The raw stream may open with ``NO_REPLY`` (the whole reply will be
    deleted) and always ends with the ``reaction:`` sign-off line; both
    are protocol, not content, and must never flash on screen mid-stream.

    Parameters
    ----------
    text : str
        Raw accumulated stream text.

    Returns
    -------
    str
        The portion safe to display right now.

    """
    stripped = text.lstrip()
    forming_no_reply = len(stripped) < len(NO_REPLY) and NO_REPLY.startswith(stripped)
    if stripped.startswith(NO_REPLY) or forming_no_reply:
        return ""

    head, _, last_line = text.rpartition("\n")
    candidate = last_line.strip().lower()
    is_signoff = candidate.startswith(_SIGNOFF_PREFIX)
    forming_signoff = bool(candidate) and _SIGNOFF_PREFIX.startswith(candidate)
    if is_signoff or forming_signoff:
        return head
    return text


def split_reaction(answer: str) -> tuple[str, str | None]:
    """Split a raw answer into visible text and the chosen reaction.

    Parameters
    ----------
    answer : str
        Raw answer text, possibly ending with a ``reaction:`` sign-off.

    Returns
    -------
    tuple[str, str | None]
        ``(visible_answer, emoji_name)``; the emoji is None when the
        model did not sign off (callers fall back to
        :data:`DEFAULT_REACTION`).

    """
    match = _SIGNOFF.search(answer)
    if not match:
        return answer.strip(), None
    return answer[: match.start()].strip(), match.group(1).lower()
