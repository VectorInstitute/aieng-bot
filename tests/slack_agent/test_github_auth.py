"""Unit tests for GitHub token providers."""

import json
import time
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from slack_agent.agents.github.auth import (
    AppInstallationAuth,
    StaticTokenAuth,
    _parse_expiry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rsa_key_pair() -> tuple[str, str]:
    """Generate one RSA key pair for the module (keygen is slow)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


def _expiry(minutes: int = 60) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


class _FakeGitHub:
    """MockTransport handler recording requests to the App endpoints."""

    def __init__(self, installations: list[dict] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.installations = (
            installations
            if installations is not None
            else [
                {"id": 7, "account": {"login": "SomeOtherOrg"}},
                {"id": 42, "account": {"login": "VectorInstitute"}},
            ]
        )
        self.tokens_minted = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/app/installations":
            return httpx.Response(200, json=self.installations)
        if request.url.path.endswith("/access_tokens"):
            self.tokens_minted += 1
            return httpx.Response(
                201,
                json={
                    "token": f"ghs_test_{self.tokens_minted}",
                    "expires_at": _expiry(),
                },
            )
        return httpx.Response(404, json={"message": "Not Found"})


# ---------------------------------------------------------------------------
# StaticTokenAuth
# ---------------------------------------------------------------------------


def test_static_token_auth_returns_token() -> None:
    """The static provider hands back the configured token verbatim."""
    assert StaticTokenAuth("github_pat_x").token() == "github_pat_x"


# ---------------------------------------------------------------------------
# AppInstallationAuth
# ---------------------------------------------------------------------------


class TestAppInstallationAuth:
    """Tests for the GitHub App installation-token flow."""

    def test_discovers_installation_and_mints_token(
        self, rsa_key_pair: tuple[str, str]
    ) -> None:
        """First token() call discovers the org installation and mints."""
        private_pem, public_pem = rsa_key_pair
        fake = _FakeGitHub()
        auth = AppInstallationAuth(
            app_id="1234",
            private_key_pem=private_pem,
            org="VectorInstitute",
            transport=httpx.MockTransport(fake),
        )

        assert auth.token() == "ghs_test_1"
        # Discovery picked the VectorInstitute installation, not the other.
        assert fake.requests[-1].url.path == "/app/installations/42/access_tokens"

    def test_app_jwt_is_signed_and_names_the_app(
        self, rsa_key_pair: tuple[str, str]
    ) -> None:
        """The Authorization JWT verifies against the key and carries iss."""
        private_pem, public_pem = rsa_key_pair
        fake = _FakeGitHub()
        auth = AppInstallationAuth(
            app_id="1234",
            private_key_pem=private_pem,
            org="VectorInstitute",
            transport=httpx.MockTransport(fake),
        )
        auth.token()

        bearer = fake.requests[0].headers["Authorization"].removeprefix("Bearer ")
        claims = jwt.decode(bearer, public_pem, algorithms=["RS256"])
        assert claims["iss"] == "1234"
        assert claims["exp"] > time.time()

    def test_token_is_cached_until_near_expiry(
        self, rsa_key_pair: tuple[str, str]
    ) -> None:
        """Repeated calls reuse the cached token without new requests."""
        private_pem, _ = rsa_key_pair
        fake = _FakeGitHub()
        auth = AppInstallationAuth(
            app_id="1234",
            private_key_pem=private_pem,
            org="VectorInstitute",
            transport=httpx.MockTransport(fake),
        )

        first = auth.token()
        second = auth.token()

        assert first == second
        assert fake.tokens_minted == 1

    def test_expired_token_is_refreshed(self, rsa_key_pair: tuple[str, str]) -> None:
        """A token past the refresh margin is minted anew."""
        private_pem, _ = rsa_key_pair
        fake = _FakeGitHub()
        auth = AppInstallationAuth(
            app_id="1234",
            private_key_pem=private_pem,
            org="VectorInstitute",
            transport=httpx.MockTransport(fake),
        )
        auth.token()
        auth._expires_at = time.time()  # simulate expiry

        assert auth.token() == "ghs_test_2"
        assert fake.tokens_minted == 2

    def test_pinned_installation_skips_discovery(
        self, rsa_key_pair: tuple[str, str]
    ) -> None:
        """An explicit installation_id goes straight to the token exchange."""
        private_pem, _ = rsa_key_pair
        fake = _FakeGitHub()
        auth = AppInstallationAuth(
            app_id="1234",
            private_key_pem=private_pem,
            org="VectorInstitute",
            installation_id=99,
            transport=httpx.MockTransport(fake),
        )
        auth.token()

        paths = [r.url.path for r in fake.requests]
        assert paths == ["/app/installations/99/access_tokens"]

    def test_not_installed_on_org_raises(self, rsa_key_pair: tuple[str, str]) -> None:
        """No installation on the configured org is a clear error."""
        private_pem, _ = rsa_key_pair
        fake = _FakeGitHub(installations=[{"id": 7, "account": {"login": "Other"}}])
        auth = AppInstallationAuth(
            app_id="1234",
            private_key_pem=private_pem,
            org="VectorInstitute",
            transport=httpx.MockTransport(fake),
        )

        with pytest.raises(RuntimeError, match="not installed"):
            auth.token()


# ---------------------------------------------------------------------------
# Expiry parsing
# ---------------------------------------------------------------------------


def test_parse_expiry_reads_iso_timestamp() -> None:
    """GitHub's Z-suffixed ISO expiry converts to a Unix timestamp."""
    ts = _parse_expiry("2030-01-01T00:00:00Z")
    assert ts == datetime(2030, 1, 1, tzinfo=timezone.utc).timestamp()


def test_parse_expiry_falls_back_on_garbage() -> None:
    """A malformed expiry yields a bounded future timestamp, not forever."""
    ts = _parse_expiry("not-a-date")
    assert time.time() < ts < time.time() + 3600


def test_serialization_roundtrip_sanity(rsa_key_pair: tuple[str, str]) -> None:
    """The fixture's PEM pair is self-consistent (guards the other tests)."""
    private_pem, public_pem = rsa_key_pair
    token = jwt.encode({"iss": "x"}, private_pem, algorithm="RS256")
    assert json.loads(json.dumps(jwt.decode(token, public_pem, algorithms=["RS256"])))
