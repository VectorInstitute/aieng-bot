"""Environment-driven settings for the Slack agent."""

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
