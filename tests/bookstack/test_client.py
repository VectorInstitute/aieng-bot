"""Unit tests for BookStackClient."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from aieng_bot.bookstack.client import BookStackClient


@pytest.fixture
def client() -> BookStackClient:
    """Return a client pointed at a dummy URL."""
    return BookStackClient(
        base_url="https://bookstack.example.com",
        token_id="test-id",
        token_secret="test-secret",
    )


def _mock_response(data: object, status_code: int = 200) -> MagicMock:
    """Build a mock httpx.Response."""
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    mock.json.return_value = data
    mock.raise_for_status = MagicMock()
    return mock


class TestBookStackClient:
    """Tests for BookStackClient."""

    def test_auth_header_format(self, client: BookStackClient) -> None:
        """Authorization header should use Token ID:SECRET format."""
        assert client._headers["Authorization"] == "Token test-id:test-secret"

    def test_api_base_strips_trailing_slash(self) -> None:
        """Trailing slash on base_url must be stripped."""
        c = BookStackClient("https://example.com/", "id", "secret")
        assert c._api_base == "https://example.com/api"

    def test_search_calls_correct_endpoint(self, client: BookStackClient) -> None:
        """search() should GET /api/search with query params."""
        payload = {"data": [], "total": 0}
        mock_resp = _mock_response(payload)

        with patch("httpx.Client") as mock_cls:
            mock_ctx = MagicMock()
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.get.return_value = mock_resp

            result = client.search("onboarding", count=5)

        mock_ctx.get.assert_called_once_with(
            "https://bookstack.example.com/api/search",
            headers=client._headers,
            params={"query": "onboarding", "count": 5, "page": 1},
        )
        assert result == payload

    def test_search_caps_count_at_30(self, client: BookStackClient) -> None:
        """search() should cap count at 30 regardless of caller input."""
        mock_resp = _mock_response({"data": [], "total": 0})

        with patch("httpx.Client") as mock_cls:
            mock_ctx = MagicMock()
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.get.return_value = mock_resp

            client.search("q", count=100)

        _, kwargs = mock_ctx.get.call_args
        assert kwargs["params"]["count"] == 30

    def test_get_page_calls_correct_endpoint(self, client: BookStackClient) -> None:
        """get_page() should GET /api/pages/{id}."""
        page_data = {
            "id": 42,
            "name": "Onboarding",
            "markdown": "# Hello",
            "url": "https://…",
        }
        mock_resp = _mock_response(page_data)

        with patch("httpx.Client") as mock_cls:
            mock_ctx = MagicMock()
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.get.return_value = mock_resp

            result = client.get_page(42)

        mock_ctx.get.assert_called_once_with(
            "https://bookstack.example.com/api/pages/42",
            headers=client._headers,
            params=None,
        )
        assert result == page_data

    def test_list_books_calls_correct_endpoint(self, client: BookStackClient) -> None:
        """list_books() should GET /api/books with count=100."""
        books_data = {"data": [{"id": 1, "name": "Policies"}], "total": 1}
        mock_resp = _mock_response(books_data)

        with patch("httpx.Client") as mock_cls:
            mock_ctx = MagicMock()
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.get.return_value = mock_resp

            result = client.list_books()

        mock_ctx.get.assert_called_once_with(
            "https://bookstack.example.com/api/books",
            headers=client._headers,
            params={"count": 100},
        )
        assert result == books_data

    def test_http_error_propagates(self, client: BookStackClient) -> None:
        """HTTP errors from raise_for_status() should bubble up."""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock()
        )

        with patch("httpx.Client") as mock_cls:
            mock_ctx = MagicMock()
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.get.return_value = mock_resp

            with pytest.raises(httpx.HTTPStatusError):
                client.search("test")
