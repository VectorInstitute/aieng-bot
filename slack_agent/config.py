"""Environment-driven settings for the Slack agent."""

import base64
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Root .env holds LLM/BookStack credentials for local dev; slack_agent/.env
# holds the Slack tokens. Both are optional — production uses real env vars.
# Paths are explicit: load_dotenv()'s directory walk stops at the first .env
# it finds and would miss the second file.
_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")


@dataclass(frozen=True)
class Settings:
    """Resolved runtime configuration.

    Attributes
    ----------
    slack_bot_token : str
        Bot User OAuth token (``xoxb-``).
    slack_app_token : str
        App-level token for Socket Mode (``xapp-``).
    git_sha : str
        Commit SHA of the running build (injected by the deploy workflow).
    port : int
        Port for the health endpoint.
    bookstack_url : str
        Root URL of the BookStack instance.
    bookstack_token_id : str
        BookStack API token ID (empty if unconfigured).
    bookstack_token_secret : str
        BookStack API token secret (empty if unconfigured).
    context_window_tokens : int
        Context window of the serving model; history budgets derive
        from it.
    state_dir : str
        Directory for durable session snapshots (a GCS volume mount in
        production); empty disables persistence.
    github_org : str
        GitHub organization all GitHub tools are pinned to.
    github_app_id : str
        GitHub App ID for installation-token auth (empty if unconfigured).
    github_app_installation_id : str
        Installation ID override; empty auto-discovers from the org.
    github_app_private_key : str
        The App's private key in PEM form (resolved from file, base64,
        or inline env var; empty if unconfigured).
    github_token : str
        Fine-grained PAT fallback for local development (empty if
        unconfigured). App credentials take precedence.

    """

    slack_bot_token: str
    slack_app_token: str
    git_sha: str
    port: int
    bookstack_url: str
    bookstack_token_id: str
    bookstack_token_secret: str
    context_window_tokens: int
    state_dir: str
    github_org: str = "VectorInstitute"
    github_app_id: str = ""
    github_app_installation_id: str = ""
    github_app_private_key: str = ""
    github_token: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from environment variables.

        Returns
        -------
        Settings
            The resolved settings.

        Raises
        ------
        RuntimeError
            If required Slack tokens are missing.

        """
        missing = [
            var
            for var in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN")
            if not os.environ.get(var)
        ]
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}"
            )
        return cls(
            slack_bot_token=os.environ["SLACK_BOT_TOKEN"],
            slack_app_token=os.environ["SLACK_APP_TOKEN"],
            git_sha=os.environ.get("GIT_SHA", "dev"),
            port=int(os.environ.get("PORT", "8080")),
            bookstack_url=os.environ.get(
                "BOOKSTACK_URL", "https://bookstack.vectorinstitute.ai"
            ),
            bookstack_token_id=os.environ.get("BOOKSTACK_TOKEN_ID", ""),
            bookstack_token_secret=os.environ.get("BOOKSTACK_TOKEN_SECRET", ""),
            context_window_tokens=int(
                os.environ.get("CONTEXT_WINDOW_TOKENS", "262144")
            ),
            state_dir=os.environ.get("STATE_DIR", ""),
            github_org=os.environ.get("GITHUB_ORG", "VectorInstitute"),
            github_app_id=os.environ.get("GITHUB_APP_ID", ""),
            github_app_installation_id=os.environ.get("GITHUB_APP_INSTALLATION_ID", ""),
            github_app_private_key=_resolve_github_private_key(),
            github_token=os.environ.get("GITHUB_TOKEN", ""),
        )

    @property
    def llm_configured(self) -> bool:
        """Return True if an LLM backend (gateway or direct) is configured."""
        if os.environ.get("LLM_BASE_URL"):
            return bool(os.environ.get("LLM_API_KEY"))
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    @property
    def bookstack_configured(self) -> bool:
        """Return True if the BookStack QA capability can be enabled."""
        return (
            bool(self.bookstack_token_id and self.bookstack_token_secret)
            and self.llm_configured
        )

    @property
    def github_configured(self) -> bool:
        """Return True if the GitHub QA capability can be enabled."""
        has_app = bool(self.github_app_id and self.github_app_private_key)
        return (has_app or bool(self.github_token)) and self.llm_configured


def _resolve_github_private_key() -> str:
    """Resolve the GitHub App private key from the environment.

    Three forms, most specific first: a file path (local development,
    where the downloaded ``.pem`` stays on disk), a base64-encoded value
    (Cloud Run, where the deploy flag cannot carry PEM newlines), or the
    inline PEM with literal ``\\n`` escapes.
    """
    key_file = os.environ.get("GITHUB_APP_PRIVATE_KEY_FILE", "").strip()
    if key_file:
        path = Path(key_file)
        if path.is_file():
            return path.read_text()
    key_b64 = os.environ.get("GITHUB_APP_PRIVATE_KEY_B64", "").strip()
    if key_b64:
        try:
            return base64.b64decode(key_b64).decode()
        except (ValueError, UnicodeDecodeError):
            return ""
    return os.environ.get("GITHUB_APP_PRIVATE_KEY", "").replace("\\n", "\n")
