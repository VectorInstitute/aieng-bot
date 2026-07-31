"""Tests for the principal-based authorization layer.

Guards the requirement that anyone in the workspace can ask questions
but only allowlisted principals can trigger write tools, with rosters
and manifests filtered accordingly (integration-agnostic: the policy
keys off TOOL_ACCESS declarations, so future connectors are covered).
"""

import pytest

from slack_agent.agents.bookstack.subagent import (
    READER_SYSTEM,
    READER_TOOLS,
    WRITER_SYSTEM,
    WRITER_TOOLS,
    BookstackSubAgent,
)
from slack_agent.authorization import ANONYMOUS, AccessPolicy, Principal
from slack_agent.config import Settings

AMRIT = Principal(user_id="U1AMRIT", display_name="Amrit")
RANDOM = Principal(user_id="U9RANDOM", display_name="Someone Random")


class TestAccessPolicy:
    """Allowlist semantics."""

    def test_default_is_read_only_for_everyone(self, monkeypatch):
        """With AGENT_WRITERS unset, nobody can write (safe default)."""
        monkeypatch.delenv("AGENT_WRITERS", raising=False)
        policy = AccessPolicy.from_env()
        assert not policy.can_write(AMRIT)
        assert not policy.can_write(ANONYMOUS)
        assert policy.allowed_levels(AMRIT) == frozenset({"read", "act"})

    def test_allowlisted_user_can_write(self, monkeypatch):
        """Only listed user IDs get the write level."""
        monkeypatch.setenv("AGENT_WRITERS", "U1AMRIT, U2OTHER")
        policy = AccessPolicy.from_env()
        assert policy.can_write(AMRIT)
        assert not policy.can_write(RANDOM)
        assert policy.allowed_levels(AMRIT) == frozenset({"read", "act", "write"})

    def test_star_allows_everyone_except_anonymous_stays_meaningful(self, monkeypatch):
        """The explicit * sentinel opens writes to all principals."""
        monkeypatch.setenv("AGENT_WRITERS", "*")
        policy = AccessPolicy.from_env()
        assert policy.can_write(RANDOM)

    def test_anonymous_never_writes_from_allowlist(self):
        """An empty user ID can never match an allowlist entry."""
        policy = AccessPolicy(frozenset({""}))
        assert not policy.can_write(ANONYMOUS)


class TestRosters:
    """Per-tier tool rosters and manifests."""

    def test_reader_roster_has_no_write_tools(self):
        """Unauthorized principals' agents lack write tools entirely."""
        names = {t["name"] for t in READER_TOOLS}
        assert "create_page" not in names
        assert "update_page" not in names
        assert {"search_bookstack", "get_page", "add_reaction"} <= names

    def test_writer_roster_has_everything(self):
        """Writers get the full roster."""
        names = {t["name"] for t in WRITER_TOOLS}
        assert {"create_page", "update_page", "search_bookstack"} <= names

    def test_manifests_match_their_rosters(self):
        """Each tier's manifest only claims that tier's abilities."""
        assert "create_page" in WRITER_SYSTEM
        assert "<writing>" in WRITER_SYSTEM
        assert "create_page" not in READER_SYSTEM
        assert "<writing>" not in READER_SYSTEM
        # The reader still has the reaction action, honestly listed.
        assert "add_reaction" in READER_SYSTEM

    def test_reader_manifest_denies_wiki_writes(self):
        """A reader's manifest tells the model unlisted means impossible."""
        assert "not listed above, you cannot do it" in READER_SYSTEM


class TestSubagentRosterSelection:
    """The sub-agent picks the roster from the policy, per principal."""

    @pytest.fixture
    def subagent(self, monkeypatch) -> BookstackSubAgent:
        """A sub-agent with dummy credentials and an explicit policy."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        settings = Settings(
            slack_bot_token="xoxb-test",
            slack_app_token="xapp-test",
            git_sha="dev",
            port=8080,
            bookstack_url="https://wiki.example.com",
            bookstack_token_id="id",
            bookstack_token_secret="secret",
            context_window_tokens=262144,
            state_dir="",
        )
        return BookstackSubAgent(
            settings,
            slack_context=None,  # type: ignore[arg-type]
            policy=AccessPolicy(frozenset({"U1AMRIT"})),
        )

    def test_writer_gets_writer_roster(self, subagent):
        """An allowlisted principal is served the write-capable agent."""
        tools, system = subagent._roster_for(AMRIT)
        assert tools is WRITER_TOOLS
        assert system is WRITER_SYSTEM

    def test_random_user_gets_reader_roster(self, subagent):
        """Anyone else is served the read-only agent."""
        tools, system = subagent._roster_for(RANDOM)
        assert tools is READER_TOOLS
        assert system is READER_SYSTEM

    def test_anonymous_gets_reader_roster(self, subagent):
        """A request with no resolvable user is read-only."""
        tools, _ = subagent._roster_for(ANONYMOUS)
        assert tools is READER_TOOLS
