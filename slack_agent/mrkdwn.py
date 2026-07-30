"""Convert standard markdown to Slack mrkdwn.

Slack messages use mrkdwn, not markdown: bold is ``*text*`` (single
asterisks), italic is ``_text_``, links are ``<url|text>``, and there is no
heading syntax. The agent produces regular markdown (it also feeds a web UI),
so this module translates the common constructs. The conversion is
line-based and code-block aware; fenced code blocks pass through untouched.
"""

import re

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_BULLET = re.compile(r"^(\s*)[-*]\s+")
_INLINE_CODE = re.compile(r"(`[^`]*`)")


def _convert_segment(segment: str) -> str:
    """Convert one non-code text segment to mrkdwn."""
    segment = _LINK.sub(r"<\2|\1>", segment)
    return _BOLD.sub(r"*\1*", segment)


def _convert_line(line: str) -> str:
    """Convert a single line outside fenced code blocks."""
    heading = _HEADING.match(line)
    if heading:
        return f"*{_convert_segment(heading.group(1)).strip('*')}*"

    line = _BULLET.sub(r"\1• ", line)

    # Convert around inline code spans so their contents stay verbatim.
    parts = _INLINE_CODE.split(line)
    return "".join(
        part if part.startswith("`") else _convert_segment(part) for part in parts
    )


def to_mrkdwn(markdown: str) -> str:
    """Convert markdown text to Slack mrkdwn.

    Parameters
    ----------
    markdown : str
        Standard markdown text.

    Returns
    -------
    str
        The equivalent Slack mrkdwn text.

    """
    out: list[str] = []
    in_code_block = False
    for line in markdown.split("\n"):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            out.append(line)
        elif in_code_block:
            out.append(line)
        else:
            out.append(_convert_line(line))
    return "\n".join(out)
