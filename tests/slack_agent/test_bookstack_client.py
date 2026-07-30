"""Unit tests for BookStackClient."""

import json

import httpx
import pytest

from aieng_bot.bookstack.client import BookStackClient


def _make_client(
    handler,
    base_url: str = "https://bookstack.example.com",
) -> BookStackClient:
    """Build a client whose HTTP layer is served by *handler*."""
    return BookStackClient(
        base_url=base_url,
        token_id="test-id",
        token_secret="test-secret",
        transport=httpx.MockTransport(handler),
    )


def _json_response(data: object, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=data)


class TestBookStackClient:
    """Tests for BookStackClient."""

    def test_auth_header_format(self) -> None:
        """Authorization header should use Token ID:SECRET format."""
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers["Authorization"]
            return _json_response({"data": []})

        client = _make_client(handler)
        client.search("q")
        assert seen["auth"] == "Token test-id:test-secret"

    def test_api_base_strips_trailing_slash(self) -> None:
        """Trailing slash on base_url must be stripped."""
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return _json_response({"data": []})

        client = _make_client(handler, base_url="https://example.com/")
        client.list_books()
        assert seen["url"].startswith("https://example.com/api/books")

    def test_search_calls_correct_endpoint(self) -> None:
        """search() should GET /api/search with query params."""
        payload = {"data": [], "total": 0}
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["params"] = dict(request.url.params)
            return _json_response(payload)

        client = _make_client(handler)
        result = client.search("onboarding", count=5)

        assert seen["path"] == "/api/search"
        assert seen["params"] == {"query": "onboarding", "count": "5", "page": "1"}
        assert result == payload

    def test_search_caps_count_at_30(self) -> None:
        """search() should cap count at 30 regardless of caller input."""
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["params"] = dict(request.url.params)
            return _json_response({"data": [], "total": 0})

        client = _make_client(handler)
        client.search("q", count=100)

        assert seen["params"]["count"] == "30"

    def test_get_page_calls_correct_endpoint(self) -> None:
        """get_page() should GET /api/pages/{id}."""
        page_data = {
            "id": 42,
            "name": "Onboarding",
            "markdown": "# Hello",
            "url": "https://example.com/page",
        }
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            return _json_response(page_data)

        client = _make_client(handler)
        result = client.get_page(42)

        assert seen["path"] == "/api/pages/42"
        assert result == page_data

    def test_list_books_calls_correct_endpoint(self) -> None:
        """list_books() should GET /api/books with count=100."""
        books_data = {"data": [{"id": 1, "name": "Policies"}], "total": 1}
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["params"] = dict(request.url.params)
            return _json_response(books_data)

        client = _make_client(handler)
        result = client.list_books()

        assert seen["path"] == "/api/books"
        assert seen["params"] == {"count": "100"}
        assert result == books_data

    def test_http_error_propagates(self) -> None:
        """HTTP errors from raise_for_status() should bubble up."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": "not found"})

        client = _make_client(handler)
        with pytest.raises(httpx.HTTPStatusError):
            client.search("test")

    def test_connection_reuse_single_client(self) -> None:
        """Sequential calls should reuse the same underlying httpx.Client."""
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return _json_response({"data": []})

        client = _make_client(handler)
        underlying = client._client
        client.search("a")
        client.list_books()
        assert client._client is underlying
        assert calls == 2

    def test_close_closes_pool(self) -> None:
        """close() should close the underlying client."""

        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response({"data": []})

        client = _make_client(handler)
        client.close()
        with pytest.raises(RuntimeError):
            client.search("after close")

    def test_response_json_parsed(self) -> None:
        """Responses should be parsed from JSON bodies."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=json.dumps({"data": [{"id": 7}]}),
                headers={"Content-Type": "application/json"},
            )

        client = _make_client(handler)
        assert client.list_books() == {"data": [{"id": 7}]}
