"""Tool definitions and execution for the BookStack QA agent."""

import json
import re
from datetime import datetime, timezone
from typing import Any

from anthropic.types import ToolParam

from .client import BookStackClient

SEARCH_TOOL: ToolParam = {
    "name": "search_bookstack",
    "description": (
        "Full-text search across all BookStack books, chapters, and pages. "
        "Returns matching items with titles, snippets, and IDs. "
        "Use this first to find relevant content, then call get_page for the full text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query. Use specific keywords for the best results.",
            },
            "count": {
                "type": "integer",
                "description": "Number of results to return (1–30, default 10).",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}

GET_PAGE_TOOL: ToolParam = {
    "name": "get_page",
    "description": (
        "Fetch the complete markdown content of a BookStack page by its numeric ID. "
        "Call this after search to read the full documentation for relevant pages. "
        "The response includes the page name, markdown body, and canonical URL."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "page_id": {
                "type": "integer",
                "description": "Numeric page ID returned by search_bookstack.",
            },
        },
        "required": ["page_id"],
    },
}

LIST_BOOKS_TOOL: ToolParam = {
    "name": "list_books",
    "description": (
        "List all books available in BookStack with their names and descriptions. "
        "Use this to understand what topics are documented before crafting a search query."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

CREATE_PAGE_TOOL: ToolParam = {
    "name": "create_page",
    "description": (
        "Create a new page in the BookStack wiki with markdown content. "
        "Only use after the user explicitly asked for documentation to be "
        "written and has confirmed the target book, title, and outline. "
        "Use list_books to find the book_id. "
        "Returns the created page's name and URL."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "book_id": {
                "type": "integer",
                "description": "Numeric ID of the target book (from list_books).",
            },
            "name": {
                "type": "string",
                "description": "Page title.",
            },
            "markdown": {
                "type": "string",
                "description": "Full page body in markdown.",
            },
        },
        "required": ["book_id", "name", "markdown"],
    },
}

UPDATE_PAGE_TOOL: ToolParam = {
    "name": "update_page",
    "description": (
        "Update an existing BookStack page's title and/or markdown content. "
        "Only use after the user explicitly asked for the page to be changed. "
        "Call get_page first and preserve everything you were not asked to "
        "change. Returns the updated page's name and URL."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "page_id": {
                "type": "integer",
                "description": "Numeric ID of the page to update.",
            },
            "name": {
                "type": "string",
                "description": "New page title (omit to keep the current one).",
            },
            "markdown": {
                "type": "string",
                "description": (
                    "Full replacement page body in markdown (omit to keep "
                    "the current content)."
                ),
            },
        },
        "required": ["page_id"],
    },
}

ALL_TOOLS: list[ToolParam] = [
    SEARCH_TOOL,
    GET_PAGE_TOOL,
    LIST_BOOKS_TOOL,
    CREATE_PAGE_TOOL,
    UPDATE_PAGE_TOOL,
]

BOOKSTACK_TOOL_NAMES = frozenset(str(t["name"]) for t in ALL_TOOLS)

# Access level per tool, consumed by the system-prompt capability
# manifest. Every tool defined here must be declared; write tools are
# listed as actions in the generated prompt.
TOOL_ACCESS: dict[str, str] = {
    "search_bookstack": "read",
    "get_page": "read",
    "list_books": "read",
    "create_page": "write",
    "update_page": "write",
}


# The wiki API token belongs to a single account, so BookStack's own
# metadata cannot attribute bot writes to the person who asked. The
# harness stamps provenance into the page itself instead: every write
# carries a footer naming the requester, appended here rather than by
# the model so it cannot be forgotten or forged.
# Matched anywhere, not just at the end: when the model edits fetched
# markdown it often appends below the old footer, which would otherwise
# survive mid-document and stack up.
_ATTRIBUTION_FOOTER = re.compile(r"\n*---\n\*Maintained by aieng-bot;[^\n]*\*\n?")


def _with_attribution(markdown: str, attribution: str) -> str:
    """Append the harness-owned attribution footer, replacing any prior one."""
    if not attribution:
        return markdown
    body = _ATTRIBUTION_FOOTER.sub("\n", markdown).rstrip()
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return (
        f"{body}\n\n---\n*Maintained by aieng-bot; "
        f"last change requested by {attribution} ({date}).*"
    )


# Visibility policy for bot-written pages: never public, viewable (and
# editable) by staff only. Enforced by the harness right after creation
# so the model cannot forget it; role IDs are resolved by name at write
# time to survive role renumbering.
_DENY_VIEW_ROLE = "public"
_ALLOW_VIEW_ROLE = "vectorstaff"


def _restrict_page(client: BookStackClient, page_id: int) -> str:
    """Apply the staff-only visibility policy to a freshly created page.

    Returns a human-readable status for the tool result, so the model
    reports honestly if the restriction could not be applied.
    """
    raw_roles = client.list_roles().get("data", [])
    roles = (
        [role for role in raw_roles if isinstance(role, dict)]
        if isinstance(raw_roles, list)
        else []
    )
    ids_by_name = {
        str(role.get("display_name", "")).lower(): int(role["id"])
        for role in roles
        if "id" in role
    }
    staff_id = ids_by_name.get(_ALLOW_VIEW_ROLE)
    public_id = ids_by_name.get(_DENY_VIEW_ROLE)
    if staff_id is None:
        return "WARNING: VectorStaff role not found; page visibility not set"
    rows: list[dict[str, object]] = [
        {
            "role_id": staff_id,
            "view": True,
            "create": False,
            "update": True,
            "delete": False,
        }
    ]
    if public_id is not None:
        rows.insert(
            0,
            {
                "role_id": public_id,
                "view": False,
                "create": False,
                "update": False,
                "delete": False,
            },
        )
    client.set_page_permissions(page_id, rows)
    return "restricted: viewable by VectorStaff only, hidden from Public"


def _page_summary(raw: dict[str, object]) -> dict[str, object]:
    """Condense a page API response to what the model needs to report back."""
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "url": raw.get("url", ""),
    }


def execute_tool(
    name: str,
    tool_input: dict[str, Any],
    client: BookStackClient,
    attribution: str = "",
) -> str:
    """Execute a tool call against the BookStack API and return a JSON string result.

    Parameters
    ----------
    name : str
        Tool name (any name in :data:`BOOKSTACK_TOOL_NAMES`).
    tool_input : dict
        Tool input as provided by the model.
    client : BookStackClient
        Authenticated BookStack API client.
    attribution : str, optional
        Who requested the change; stamped into written pages as a
        footer (writes only, empty disables).

    Returns
    -------
    str
        JSON-encoded result, or an error message string.

    """

    def _search() -> str:
        result = client.search(
            str(tool_input["query"]), count=int(tool_input.get("count", 10))
        )
        return json.dumps(result, indent=2)

    def _get_page() -> str:
        raw = client.get_page(int(tool_input["page_id"]))
        return json.dumps(
            {
                "name": raw.get("name"),
                "markdown": raw.get("markdown", ""),
                "url": raw.get("url", ""),
            },
            indent=2,
        )

    def _list_books() -> str:
        return json.dumps(client.list_books(), indent=2)

    def _create_page() -> str:
        raw = client.create_page(
            book_id=int(tool_input["book_id"]),
            name=str(tool_input["name"]),
            markdown=_with_attribution(str(tool_input["markdown"]), attribution),
        )
        summary = _page_summary(raw)
        try:
            summary["visibility"] = _restrict_page(client, int(str(raw.get("id"))))
        except Exception as exc:  # noqa: BLE001
            summary["visibility"] = (
                f"WARNING: could not restrict page visibility ({exc}); "
                "tell the user so they can fix permissions manually"
            )
        return json.dumps(summary, indent=2)

    def _update_page() -> str:
        new_name = tool_input.get("name")
        new_markdown = tool_input.get("markdown")
        if new_name is None and new_markdown is None:
            return "Error: provide a new name, new markdown, or both"
        raw = client.update_page(
            page_id=int(tool_input["page_id"]),
            name=str(new_name) if new_name is not None else None,
            markdown=(
                _with_attribution(str(new_markdown), attribution)
                if new_markdown is not None
                else None
            ),
        )
        return json.dumps(_page_summary(raw), indent=2)

    handlers = {
        "search_bookstack": _search,
        "get_page": _get_page,
        "list_books": _list_books,
        "create_page": _create_page,
        "update_page": _update_page,
    }
    handler = handlers.get(name)
    if handler is None:
        return f"Unknown tool: {name}"
    try:
        return handler()
    except Exception as e:  # noqa: BLE001
        return f"Error executing {name}: {e}"
