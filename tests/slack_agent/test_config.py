"""Unit tests for GitHub-related settings resolution."""

import base64
from pathlib import Path

import pytest

from slack_agent.config import Settings, _resolve_github_private_key

_PEM = "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n"

_GITHUB_VARS = (
    "GITHUB_ORG",
    "GITHUB_APP_ID",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_APP_PRIVATE_KEY",
    "GITHUB_APP_PRIVATE_KEY_B64",
    "GITHUB_APP_PRIVATE_KEY_FILE",
    "GITHUB_TOKEN",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Provide a baseline env: Slack tokens set, GitHub vars unset."""
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    for var in _GITHUB_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_github_unconfigured_by_default(clean_env: pytest.MonkeyPatch) -> None:
    """No GitHub credentials means the sub-agent stays disabled."""
    settings = Settings.from_env()
    assert settings.github_configured is False
    assert settings.github_org == "VectorInstitute"


def test_github_configured_via_token(clean_env: pytest.MonkeyPatch) -> None:
    """A plain PAT enables the capability (local development path)."""
    clean_env.setenv("GITHUB_TOKEN", "github_pat_x")
    assert Settings.from_env().github_configured is True


def test_github_configured_via_app(clean_env: pytest.MonkeyPatch) -> None:
    """App ID + private key enable the capability without a PAT."""
    clean_env.setenv("GITHUB_APP_ID", "1234")
    clean_env.setenv("GITHUB_APP_PRIVATE_KEY", _PEM)
    settings = Settings.from_env()
    assert settings.github_configured is True
    assert settings.github_app_private_key == _PEM


def test_private_key_from_file_wins(
    clean_env: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A key file beats the other env forms (local dev keeps PEM on disk)."""
    pem_file = tmp_path / "app.pem"
    pem_file.write_text(_PEM)
    clean_env.setenv("GITHUB_APP_PRIVATE_KEY_FILE", str(pem_file))
    clean_env.setenv("GITHUB_APP_PRIVATE_KEY", "inline-ignored")

    assert _resolve_github_private_key() == _PEM


def test_private_key_from_base64(clean_env: pytest.MonkeyPatch) -> None:
    """The Cloud Run form: base64 survives --set-env-vars intact."""
    clean_env.setenv(
        "GITHUB_APP_PRIVATE_KEY_B64", base64.b64encode(_PEM.encode()).decode()
    )
    assert _resolve_github_private_key() == _PEM


def test_private_key_inline_unescapes_newlines(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """Inline PEM with literal \\n escapes is normalized."""
    clean_env.setenv("GITHUB_APP_PRIVATE_KEY", _PEM.replace("\n", "\\n"))
    assert _resolve_github_private_key() == _PEM
