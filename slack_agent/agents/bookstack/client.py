"""BookStack REST API client."""

import httpx


class BookStackClient:
    """Thin HTTP client for the BookStack API.

    Authenticates via token ID / token secret header. All methods return
    the parsed JSON response body and raise ``httpx.HTTPStatusError`` on
    non-2xx responses.

    Parameters
    ----------
    base_url : str
        Root URL of the BookStack instance (e.g. ``https://bookstack.vectorinstitute.ai``).
    token_id : str
        BookStack API token ID.
    token_secret : str
        BookStack API token secret.
    transport : httpx.BaseTransport, optional
        Custom transport, primarily for injecting ``httpx.MockTransport``
        in tests.

    """

    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        base_url: str,
        token_id: str,
        token_secret: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Initialise the client."""
        # A single client instance reuses connections across requests
        # (httpx.Client is thread-safe, so calls may run in worker threads).
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/api",
            headers={
                "Authorization": f"Token {token_id}:{token_secret}",
                "Content-Type": "application/json",
            },
            timeout=self.DEFAULT_TIMEOUT,
            transport=transport,
        )

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def _get(
        self, path: str, params: dict[str, str | int] | None = None
    ) -> dict[str, object]:
        """Issue an authenticated GET and return parsed JSON."""
        response = self._client.get(path, params=params)
        response.raise_for_status()
        result: dict[str, object] = response.json()
        return result

    def search(self, query: str, count: int = 10, page: int = 1) -> dict[str, object]:
        """Full-text search across books, chapters, and pages.

        Parameters
        ----------
        query : str
            Search terms.
        count : int
            Number of results (max 30).
        page : int
            Pagination offset (1-based).

        Returns
        -------
        dict
            BookStack search response with ``data`` list and ``total`` count.

        """
        return self._get(
            "/search", {"query": query, "count": min(count, 30), "page": page}
        )

    def get_page(self, page_id: int) -> dict[str, object]:
        """Fetch full content for a single page.

        Parameters
        ----------
        page_id : int
            Numeric page ID (as returned by search results).

        Returns
        -------
        dict
            Page object including ``markdown``, ``name``, ``url``, etc.

        """
        return self._get(f"/pages/{page_id}")

    def list_books(self) -> dict[str, object]:
        """List all books (up to 100).

        Returns
        -------
        dict
            BookStack response with ``data`` list of book objects.

        """
        return self._get("/books", {"count": 100})
