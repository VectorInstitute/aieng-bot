#!/usr/bin/env python3
"""Verify the Slack agent's GitHub credentials end to end.

Uses the same auth + client code as the github sub-agent, so a passing
run means the deployed bot will work with the same environment.

Reads the same env vars as the agent (a repo-root ``.env`` works):
``GITHUB_APP_ID`` + ``GITHUB_APP_PRIVATE_KEY_FILE`` (or ``_B64`` /
inline) and optional ``GITHUB_APP_INSTALLATION_ID``, else a read-only
``GITHUB_TOKEN``; ``GITHUB_ORG`` defaults to VectorInstitute.

Usage:
    uv run python scripts/verify_github_access.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# slack_agent is a top-level directory, not an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from slack_agent.agents.github.auth import (  # noqa: E402
    AppInstallationAuth,
    StaticTokenAuth,
    TokenProvider,
)
from slack_agent.agents.github.client import GitHubClient  # noqa: E402
from slack_agent.config import _resolve_github_private_key  # noqa: E402


def _build_auth(org: str) -> TokenProvider:
    app_id = os.environ.get("GITHUB_APP_ID", "")
    private_key = _resolve_github_private_key()
    if app_id and private_key:
        installation = os.environ.get("GITHUB_APP_INSTALLATION_ID", "")
        print(f"auth: GitHub App {app_id} (installation: {installation or 'auto'})")
        return AppInstallationAuth(
            app_id=app_id,
            private_key_pem=private_key,
            org=org,
            installation_id=int(installation) if installation else None,
        )
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        print("auth: static GITHUB_TOKEN")
        return StaticTokenAuth(token)
    sys.exit(
        "No GitHub credentials: set GITHUB_APP_ID + GITHUB_APP_PRIVATE_KEY_FILE "
        "(or _B64/inline), or GITHUB_TOKEN"
    )


def main() -> None:
    """Mint a token and exercise the read tools against the org."""
    org = os.environ.get("GITHUB_ORG", "VectorInstitute")
    client = GitHubClient(_build_auth(org), org=org)

    repos = client.list_repos(limit=5)
    print(f"\n✓ list_repos: {len(repos)} of the most recently pushed {org} repos:")
    for repo in repos:
        print(f"    {repo['name']}  ({repo.get('visibility')})")

    readme = client.get_file("aieng-bot", "README.md")
    print(f"\n✓ get_file: read {readme['path']} from aieng-bot")

    checks = client.get_check_runs("aieng-bot", "main")
    print(f"✓ get_check_runs: {checks.get('total_count', 0)} checks on aieng-bot@main")

    print("\nAll reads succeeded. The github sub-agent will enable with this env.")


if __name__ == "__main__":
    main()
