"""Unit tests for BookStack tool definitions and execute_tool()."""

import json
from unittest.mock import MagicMock

import pytest

from slack_agent.agents.bookstack.client import BookStackClient
from slack_agent.agents.bookstack.tools import (
    ALL_TOOLS,
    GET_PAGE_TOOL,
    LIST_BOOKS_TOOL,
    SEARCH_TOOL,
    execute_tool,
)


@pytest.fixture
def mock_client() -> MagicMock:
    """Return a MagicMock standing in for BookStackClient."""
    return MagicMock(spec=BookStackClient)


class TestToolSchemas:
    """Validate the tool schema structures."""

    def test_all_tools_have_required_fields(self) -> None:
        """Every tool definition has name, description, and input_schema."""
        for tool in ALL_TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_search_tool_requires_query(self) -> None:
        """search_bookstack schema lists query as a required property."""
        schema = SEARCH_TOOL["input_schema"]
        assert "query" in schema["properties"]
        assert "query" in schema["required"]

    def test_get_page_tool_requires_page_id(self) -> None:
        """get_page schema lists page_id as a required property."""
        schema = GET_PAGE_TOOL["input_schema"]
        assert "page_id" in schema["properties"]
        assert "page_id" in schema["required"]

    def test_list_books_tool_has_no_required_params(self) -> None:
        """list_books tool schema has no required parameters."""
        schema = LIST_BOOKS_TOOL["input_schema"]
        assert schema["required"] == []

    def test_all_tools_list_length(self) -> None:
        """ALL_TOOLS exports exactly three tool definitions."""
        assert len(ALL_TOOLS) == 3


class TestExecuteTool:
    """Tests for execute_tool dispatch and output."""

    def test_search_bookstack_dispatches(self, mock_client: MagicMock) -> None:
        """search_bookstack tool calls client.search() and returns JSON."""
        mock_client.search.return_value = {"data": [], "total": 0}

        result = execute_tool("search_bookstack", {"query": "onboarding"}, mock_client)
        data = json.loads(result)

        mock_client.search.assert_called_once_with("onboarding", count=10)
        assert data == {"data": [], "total": 0}

    def test_search_bookstack_respects_count(self, mock_client: MagicMock) -> None:
        """search_bookstack passes an explicit count to client.search()."""
        mock_client.search.return_value = {"data": [], "total": 0}

        execute_tool("search_bookstack", {"query": "q", "count": 5}, mock_client)
        mock_client.search.assert_called_once_with("q", count=5)

    def test_get_page_dispatches(self, mock_client: MagicMock) -> None:
        """get_page tool calls client.get_page() and returns relevant fields."""
        mock_client.get_page.return_value = {
            "id": 7,
            "name": "Onboarding",
            "book_id": 1,
            "chapter_id": None,
            "markdown": "# Hello",
            "url": "https://wiki.example.com/books/1/page/7",
            "updated_at": "2025-01-01T00:00:00Z",
            "html": "<h1>Hello</h1>",  # should be stripped
        }

        result = execute_tool("get_page", {"page_id": 7}, mock_client)
        data = json.loads(result)

        mock_client.get_page.assert_called_once_with(7)
        # html field should not be forwarded
        assert "html" not in data
        assert data["markdown"] == "# Hello"
        assert data["name"] == "Onboarding"

    def test_list_books_dispatches(self, mock_client: MagicMock) -> None:
        """list_books tool calls client.list_books() and returns JSON."""
        books = {"data": [{"id": 1, "name": "Policies"}], "total": 1}
        mock_client.list_books.return_value = books

        result = execute_tool("list_books", {}, mock_client)
        assert json.loads(result) == books

    def test_unknown_tool_returns_error_string(self, mock_client: MagicMock) -> None:
        """An unrecognised tool name returns an error string."""
        result = execute_tool("nonexistent_tool", {}, mock_client)
        assert "Unknown tool" in result

    def test_client_exception_returns_error_string(
        self, mock_client: MagicMock
    ) -> None:
        """A client exception is caught and returned as an error string."""
        mock_client.search.side_effect = RuntimeError("network error")

        result = execute_tool("search_bookstack", {"query": "test"}, mock_client)
        assert "Error executing search_bookstack" in result
        assert "network error" in result
