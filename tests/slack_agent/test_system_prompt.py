"""Tests for system prompt assembly and the capability manifest.

Guards against the capability-hallucination bug: the agent once claimed
it could write to BookStack because the prompt never stated its actual
abilities. The manifest is generated from the real tool roster, so these
tests pin the properties that keep it truthful.
"""

import pytest

from slack_agent.agents.bookstack.subagent import WRITER_SYSTEM as SYSTEM
from slack_agent.agents.bookstack.tools import ALL_TOOLS
from slack_agent.agents.slack_tools import SLACK_TOOLS
from slack_agent.agents.system_prompt import IDENTITY, build_system_prompt

READ_TOOL = {
    "name": "search_wiki",
    "description": "Search the wiki. Use this before answering.",
    "input_schema": {"type": "object", "properties": {}},
}
WRITE_TOOL = {
    "name": "add_reaction",
    "description": "React to a message with an emoji. Use sparingly.",
    "input_schema": {"type": "object", "properties": {}},
}


class TestBuildSystemPrompt:
    """Assembly rules for the generated prompt."""

    def test_every_tool_appears_in_manifest(self):
        """Each tool name and its summary sentence make it into the prompt."""
        prompt = build_system_prompt(
            tools=[READ_TOOL, WRITE_TOOL],
            access={"search_wiki": "read", "add_reaction": "write"},
            sections=[],
        )
        assert "- search_wiki: Search the wiki." in prompt
        assert "- add_reaction: React to a message with an emoji." in prompt

    def test_undeclared_tool_fails_assembly(self):
        """A tool without an access declaration cannot ship undescribed."""
        with pytest.raises(ValueError, match="search_wiki"):
            build_system_prompt(tools=[READ_TOOL], access={}, sections=[])

    def test_unknown_access_level_fails_assembly(self):
        """Only read and write are valid access levels."""
        with pytest.raises(ValueError, match="admin"):
            build_system_prompt(
                tools=[READ_TOOL], access={"search_wiki": "admin"}, sections=[]
            )

    def test_all_read_roster_claims_read_only(self):
        """With no write tools, the prompt states the agent is read-only."""
        prompt = build_system_prompt(
            tools=[READ_TOOL], access={"search_wiki": "read"}, sections=[]
        )
        assert "All of your tools are read-only" in prompt
        assert "Actions" not in prompt

    def test_write_tool_scopes_the_boundary(self):
        """A write tool is listed as an action; the read-only claim is gone."""
        prompt = build_system_prompt(
            tools=[READ_TOOL, WRITE_TOOL],
            access={"search_wiki": "read", "add_reaction": "write"},
            sections=[],
        )
        assert "All of your tools are read-only" not in prompt
        assert "Actions (the only ways you can change anything):" in prompt

    def test_capability_rules_present(self):
        """The prompt tells the model to answer about itself from the list."""
        prompt = build_system_prompt(
            tools=[READ_TOOL], access={"search_wiki": "read"}, sections=[]
        )
        assert "answer in plain language from" in prompt
        assert "never infer an ability from" in prompt
        assert "not listed above, you cannot do it" in prompt

    def test_sections_appended_in_order_after_capabilities(self):
        """Domain sections follow identity and capabilities, in order."""
        prompt = build_system_prompt(
            tools=[READ_TOOL],
            access={"search_wiki": "read"},
            sections=["<alpha>a</alpha>", "", "<beta>b</beta>"],
        )
        assert prompt.startswith(IDENTITY)
        assert prompt.index("<capabilities>") < prompt.index("<alpha>")
        assert prompt.index("<alpha>") < prompt.index("<beta>")

    def test_assembly_is_deterministic(self):
        """Byte-identical output across builds keeps prompt caching warm."""
        args = {
            "tools": [READ_TOOL, WRITE_TOOL],
            "access": {"search_wiki": "read", "add_reaction": "write"},
            "sections": ["<s>x</s>"],
        }
        assert build_system_prompt(**args) == build_system_prompt(**args)


class TestBookstackSubagentPrompt:
    """The real assembled prompt for the BookStack sub-agent."""

    def test_manifest_covers_the_full_roster(self):
        """Every BookStack and Slack tool is declared and described."""
        for tool in [*ALL_TOOLS, *SLACK_TOOLS]:
            assert f"- {tool['name']}:" in SYSTEM

    def test_identity_and_domain_sections_present(self):
        """The prompt carries identity, capabilities, QA strategy, and Slack rules."""
        assert "<identity>" in SYSTEM
        assert "<capabilities>" in SYSTEM
        assert "<tool_strategy>" in SYSTEM
        assert "<slack_context_tools>" in SYSTEM
        assert "reaction:" in SYSTEM

    def test_write_actions_match_the_access_registry(self):
        """Exactly the declared write tools appear in the Actions list."""
        actions = SYSTEM.split("Actions (the only ways you can change anything):")[1]
        actions = actions.split("\n\n")[0]
        for write_tool in ("add_reaction", "create_page", "update_page"):
            assert write_tool in actions
        assert "search_bookstack" not in actions
        assert "get_channel_history" not in actions
