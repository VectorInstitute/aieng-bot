"""Tool definitions and execution for the BookStack QA agent."""

import json
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

ALL_TOOLS: list[ToolParam] = [SEARCH_TOOL, GET_PAGE_TOOL, LIST_BOOKS_TOOL]


def execute_tool(name: str, tool_input: dict[str, Any], client: BookStackClient) -> str:
    """Execute a tool call against the BookStack API and return a JSON string result.

    Parameters
    ----------
    name : str
        Tool name (``search_bookstack``, ``get_page``, or ``list_books``).
    tool_input : dict
        Tool input as provided by the model.
    client : BookStackClient
        Authenticated BookStack API client.

    Returns
    -------
    str
        JSON-encoded result, or an error message string.

    """
    try:
        if name == "search_bookstack":
            query = str(tool_input["query"])
            count = int(tool_input.get("count", 10))
            result = client.search(query, count=count)
            return json.dumps(result, indent=2)

        if name == "get_page":
            page_id = int(tool_input["page_id"])
            raw = client.get_page(page_id)
            # Return only the fields useful for answering — omits large HTML body
            return json.dumps(
                {
                    "id": raw.get("id"),
                    "name": raw.get("name"),
                    "book_id": raw.get("book_id"),
                    "chapter_id": raw.get("chapter_id"),
                    "markdown": raw.get("markdown", ""),
                    "url": raw.get("url", ""),
                    "updated_at": raw.get("updated_at"),
                },
                indent=2,
            )

        if name == "list_books":
            result = client.list_books()
            return json.dumps(result, indent=2)

        return f"Unknown tool: {name}"

    except Exception as e:  # noqa: BLE001
        return f"Error executing {name}: {e}"
