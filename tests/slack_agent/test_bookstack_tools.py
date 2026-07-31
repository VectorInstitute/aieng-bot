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
        """ALL_TOOLS exports exactly five tool definitions."""
        assert len(ALL_TOOLS) == 5


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

    def test_create_page_dispatches(self, mock_client: MagicMock) -> None:
        """create_page calls client.create_page() and returns name plus URL."""
        mock_client.create_page.return_value = {
            "id": 42,
            "name": "GPU Quotas",
            "url": "https://wiki.example.com/books/1/page/42",
            "html": "<h1>x</h1>",
        }
        mock_client.list_roles.return_value = {
            "data": [{"id": 5, "display_name": "VectorStaff"}]
        }

        result = execute_tool(
            "create_page",
            {"book_id": 1, "name": "GPU Quotas", "markdown": "# Quotas"},
            mock_client,
        )
        data = json.loads(result)

        mock_client.create_page.assert_called_once_with(
            book_id=1, name="GPU Quotas", markdown="# Quotas"
        )
        assert data["id"] == 42
        assert data["name"] == "GPU Quotas"
        assert data["url"] == "https://wiki.example.com/books/1/page/42"
        assert data["visibility"].startswith("restricted")

    def test_update_page_dispatches(self, mock_client: MagicMock) -> None:
        """update_page forwards only the provided fields."""
        mock_client.update_page.return_value = {"id": 7, "name": "N", "url": "u"}

        execute_tool("update_page", {"page_id": 7, "markdown": "# New"}, mock_client)
        mock_client.update_page.assert_called_once_with(
            page_id=7, name=None, markdown="# New"
        )

    def test_update_page_requires_a_change(self, mock_client: MagicMock) -> None:
        """update_page with nothing to change is an error, not an API call."""
        result = execute_tool("update_page", {"page_id": 7}, mock_client)
        assert result.startswith("Error")
        mock_client.update_page.assert_not_called()

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


class TestWriteAttribution:
    """Harness-stamped provenance on wiki writes."""

    def test_create_page_stamps_requester(self, mock_client: MagicMock) -> None:
        """Created pages carry a footer naming who asked for them."""
        mock_client.create_page.return_value = {"id": 1, "name": "T", "url": "u"}

        execute_tool(
            "create_page",
            {"book_id": 1, "name": "T", "markdown": "# Body"},
            mock_client,
            attribution="Amrit",
        )
        markdown = mock_client.create_page.call_args.kwargs["markdown"]
        assert markdown.startswith("# Body")
        assert "Maintained by aieng-bot; last change requested by Amrit" in markdown

    def test_update_replaces_previous_footer(self, mock_client: MagicMock) -> None:
        """A re-write replaces the old footer instead of stacking a second."""
        mock_client.update_page.return_value = {"id": 1, "name": "T", "url": "u"}
        old = (
            "# Body\n\n---\n"
            "*Maintained by aieng-bot; last change requested by Amrit (2026-01-01).*"
            "\n\nContent appended below the old footer."
        )

        execute_tool(
            "update_page",
            {"page_id": 1, "markdown": old},
            mock_client,
            attribution="Yan",
        )
        markdown = mock_client.update_page.call_args.kwargs["markdown"]
        assert markdown.count("Maintained by aieng-bot") == 1
        assert "requested by Yan" in markdown
        assert "Content appended below the old footer." in markdown
        assert markdown.rstrip().endswith(".*")

    def test_no_attribution_leaves_markdown_untouched(
        self, mock_client: MagicMock
    ) -> None:
        """Without a requester (CLI use) the body is written as-is."""
        mock_client.create_page.return_value = {"id": 1, "name": "T", "url": "u"}

        execute_tool(
            "create_page",
            {"book_id": 1, "name": "T", "markdown": "# Body"},
            mock_client,
        )
        assert mock_client.create_page.call_args.kwargs["markdown"] == "# Body"


class TestWriteVisibility:
    """Harness-enforced staff-only visibility on created pages."""

    def _roles(self) -> dict:
        return {
            "data": [
                {"id": 4, "display_name": "Public"},
                {"id": 5, "display_name": "VectorStaff"},
            ]
        }

    def test_created_page_is_restricted_to_staff(self, mock_client: MagicMock) -> None:
        """After creation the page denies Public and allows VectorStaff."""
        mock_client.create_page.return_value = {"id": 9, "name": "T", "url": "u"}
        mock_client.list_roles.return_value = self._roles()

        result = json.loads(
            execute_tool(
                "create_page",
                {"book_id": 1, "name": "T", "markdown": "# B"},
                mock_client,
            )
        )

        rows = mock_client.set_page_permissions.call_args.args[1]
        assert {r["role_id"]: r["view"] for r in rows} == {4: False, 5: True}
        assert mock_client.set_page_permissions.call_args.args[0] == 9
        assert result["visibility"].startswith("restricted")

    def test_restriction_failure_is_reported_not_swallowed(
        self, mock_client: MagicMock
    ) -> None:
        """A failed permission call surfaces a warning in the tool result."""
        mock_client.create_page.return_value = {"id": 9, "name": "T", "url": "u"}
        mock_client.list_roles.side_effect = RuntimeError("403")

        result = json.loads(
            execute_tool(
                "create_page",
                {"book_id": 1, "name": "T", "markdown": "# B"},
                mock_client,
            )
        )
        assert result["visibility"].startswith("WARNING")
