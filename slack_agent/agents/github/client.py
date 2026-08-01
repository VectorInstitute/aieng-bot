"""GitHub REST API client, pinned to one organization.

Every repository path is built from the configured organization and a
bare repository name, so a caller (or the model) can never point a
request at another owner: an ``owner/name`` input keeps only ``name``.
"""

from typing import Any

import httpx

from .auth import API_VERSION, GITHUB_API, TokenProvider


class GitHubClient:
    """Thin HTTP client for the GitHub REST API.

    All methods return the parsed JSON response body and raise
    ``httpx.HTTPStatusError`` on non-2xx responses. The token comes from
    the injected provider per request, so short-lived App installation
    tokens refresh transparently.

    Parameters
    ----------
    auth : TokenProvider
        Source of API tokens (static PAT or App installation tokens).
    org : str
        GitHub organization all requests are pinned to.
    transport : httpx.BaseTransport, optional
        Custom transport, primarily for ``httpx.MockTransport`` in tests.

    """

    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        auth: TokenProvider,
        org: str = "VectorInstitute",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Initialise the client."""
        self._auth = auth
        self.org = org
        # A single client instance reuses connections across requests
        # (httpx.Client is thread-safe, so calls may run in worker threads).
        self._client = httpx.Client(
            base_url=GITHUB_API,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
            },
            timeout=self.DEFAULT_TIMEOUT,
            transport=transport,
        )

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def _get(self, path: str, params: dict[str, str | int] | None = None) -> Any:
        """Issue an authenticated GET and return parsed JSON."""
        response = self._client.get(
            path,
            params=params,
            headers={"Authorization": f"Bearer {self._auth.token()}"},
        )
        response.raise_for_status()
        return response.json()

    def _repo_path(self, repo: str) -> str:
        """Repository API path pinned to the configured org.

        Accepts a bare name or ``owner/name``; the owner segment is
        discarded so requests cannot cross into another organization.
        """
        name = repo.strip().strip("/").split("/")[-1]
        return f"/repos/{self.org}/{name}"

    # ------------------------------------------------------------------
    # Repositories and code
    # ------------------------------------------------------------------

    def list_repos(self, limit: int = 30, sort: str = "pushed") -> Any:
        """List the organization's repositories.

        Parameters
        ----------
        limit : int
            Number of repositories to return (max 100).
        sort : str
            GitHub sort order (``pushed``, ``updated``, ``full_name``).

        """
        return self._get(
            f"/orgs/{self.org}/repos", params={"per_page": limit, "sort": sort}
        )

    def get_repo(self, repo: str) -> Any:
        """Fetch one repository's metadata."""
        return self._get(self._repo_path(repo))

    def search_code(self, query: str, limit: int = 10) -> Any:
        """Search code across the organization's repositories.

        The org qualifier is appended here, not by the caller, so the
        search cannot escape the configured organization.
        """
        return self._get(
            "/search/code",
            params={"q": f"{query} org:{self.org}", "per_page": limit},
        )

    def get_file(self, repo: str, path: str, ref: str | None = None) -> Any:
        """Fetch a file's contents entry (base64-encoded) at an optional ref."""
        params: dict[str, str | int] = {"ref": ref} if ref else {}
        return self._get(
            f"{self._repo_path(repo)}/contents/{path.lstrip('/')}", params=params
        )

    # ------------------------------------------------------------------
    # Pull requests and issues
    # ------------------------------------------------------------------

    def list_pull_requests(
        self, repo: str, state: str = "open", limit: int = 20
    ) -> Any:
        """List a repository's pull requests, most recently updated first."""
        return self._get(
            f"{self._repo_path(repo)}/pulls",
            params={
                "state": state,
                "per_page": limit,
                "sort": "updated",
                "direction": "desc",
            },
        )

    def get_pull_request(self, repo: str, number: int) -> Any:
        """Fetch one pull request's metadata."""
        return self._get(f"{self._repo_path(repo)}/pulls/{number}")

    def list_pull_request_files(self, repo: str, number: int, limit: int = 50) -> Any:
        """List the files changed by a pull request."""
        return self._get(
            f"{self._repo_path(repo)}/pulls/{number}/files",
            params={"per_page": limit},
        )

    def list_issues(self, repo: str, state: str = "open", limit: int = 20) -> Any:
        """List a repository's issues (GitHub includes PRs; callers filter)."""
        return self._get(
            f"{self._repo_path(repo)}/issues",
            params={
                "state": state,
                "per_page": limit,
                "sort": "updated",
                "direction": "desc",
            },
        )

    def get_issue(self, repo: str, number: int) -> Any:
        """Fetch one issue's metadata and body."""
        return self._get(f"{self._repo_path(repo)}/issues/{number}")

    def list_issue_comments(self, repo: str, number: int, limit: int = 20) -> Any:
        """List an issue's (or PR's) discussion comments."""
        return self._get(
            f"{self._repo_path(repo)}/issues/{number}/comments",
            params={"per_page": limit},
        )

    # ------------------------------------------------------------------
    # CI
    # ------------------------------------------------------------------

    def get_check_runs(self, repo: str, ref: str) -> Any:
        """Fetch the check runs for a commit ref (branch, tag, or SHA)."""
        return self._get(
            f"{self._repo_path(repo)}/commits/{ref}/check-runs",
            params={"per_page": 50},
        )
