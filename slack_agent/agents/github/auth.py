"""GitHub credentials: static tokens and App installation tokens.

The client never holds a credential directly; it asks a token provider
before each request. That makes the safest setup (a GitHub App minting
short-lived, read-only installation tokens) and the simplest one (a
fine-grained PAT in an env var for local dev) interchangeable behind
one interface.
"""

import threading
import time
from datetime import datetime
from typing import Protocol

import httpx
import jwt

GITHUB_API = "https://api.github.com"
API_VERSION = "2022-11-28"


class TokenProvider(Protocol):
    """Supplies a valid GitHub API token on demand."""

    def token(self) -> str:
        """Return a token currently valid for API requests."""
        ...


class StaticTokenAuth:
    """A fixed token (fine-grained PAT), mainly for local development.

    Parameters
    ----------
    token : str
        The GitHub token to present on every request.

    """

    def __init__(self, token: str) -> None:
        """Store the token."""
        self._token = token

    def token(self) -> str:
        """Return the configured token."""
        return self._token


class AppInstallationAuth:
    """Mints short-lived installation tokens for a GitHub App.

    The flow: sign a JWT with the app's private key, discover the app's
    installation on the target organization (unless pinned via
    *installation_id*), then exchange the JWT for an installation access
    token. Tokens last an hour; a cached token is reused until shortly
    before expiry. The token's permissions are whatever the app grants,
    so a read-only app yields tokens that physically cannot write.

    Parameters
    ----------
    app_id : str
        The GitHub App's numeric ID (shown on the app settings page).
    private_key_pem : str
        The app's private key in PEM format.
    org : str
        Organization login the app must be installed on.
    installation_id : int, optional
        Installation to mint tokens for; discovered from *org* when omitted.
    transport : httpx.BaseTransport, optional
        Custom transport, primarily for ``httpx.MockTransport`` in tests.

    """

    DEFAULT_TIMEOUT = 30.0
    # Refresh when less than this many seconds of validity remain, so a
    # token never expires mid-request.
    _REFRESH_MARGIN = 300.0
    # App JWT lifetime; GitHub caps it at 10 minutes.
    _JWT_TTL = 540

    def __init__(
        self,
        app_id: str,
        private_key_pem: str,
        org: str,
        installation_id: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Store app credentials; no network calls until the first token."""
        self._app_id = str(app_id)
        self._private_key = private_key_pem
        self._org = org
        self._installation_id = installation_id
        self._client = httpx.Client(
            base_url=GITHUB_API,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
            },
            timeout=self.DEFAULT_TIMEOUT,
            transport=transport,
        )
        self._lock = threading.Lock()
        self._cached_token = ""
        self._expires_at = 0.0

    def token(self) -> str:
        """Return a valid installation token, minting one if needed.

        Thread-safe: tool calls run in worker threads and must not race
        a refresh.

        Raises
        ------
        RuntimeError
            If the app is not installed on the configured organization.
        httpx.HTTPStatusError
            If GitHub rejects the JWT or the token exchange.

        """
        with self._lock:
            if self._cached_token and (
                time.time() < self._expires_at - self._REFRESH_MARGIN
            ):
                return self._cached_token
            return self._refresh()

    def _refresh(self) -> str:
        """Mint a new installation token (caller holds the lock)."""
        now = int(time.time())
        app_jwt = jwt.encode(
            # iat backdated 60s to absorb clock drift, per GitHub docs.
            {"iat": now - 60, "exp": now + self._JWT_TTL, "iss": self._app_id},
            self._private_key,
            algorithm="RS256",
        )
        headers = {"Authorization": f"Bearer {app_jwt}"}

        if self._installation_id is None:
            self._installation_id = self._discover_installation(headers)

        response = self._client.post(
            f"/app/installations/{self._installation_id}/access_tokens",
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        self._cached_token = str(data["token"])
        self._expires_at = _parse_expiry(str(data.get("expires_at", "")))
        return self._cached_token

    def _discover_installation(self, headers: dict[str, str]) -> int:
        """Find the app's installation on the configured organization."""
        response = self._client.get("/app/installations", headers=headers)
        response.raise_for_status()
        for installation in response.json():
            account = installation.get("account") or {}
            if str(account.get("login", "")).lower() == self._org.lower():
                return int(installation["id"])
        raise RuntimeError(
            f"GitHub App {self._app_id} is not installed on the "
            f"{self._org} organization"
        )


def _parse_expiry(expires_at: str) -> float:
    """Convert GitHub's ISO-8601 expiry to a Unix timestamp.

    Falls back to 50 minutes from now (tokens last an hour) if the
    field is missing or malformed, so a parse hiccup never produces a
    token believed valid forever.
    """
    try:
        return datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return time.time() + 3000.0
