"""Unit tests for GitHub tool definitions and execution."""

import base64
import json
from unittest.mock import MagicMock, patch

from slack_agent.agents.github.agent import GithubQAAgent
from slack_agent.agents.github.tools import (
    ALL_TOOLS,
    GITHUB_TOOL_NAMES,
    TOOL_ACCESS,
    execute_tool,
)

# ---------------------------------------------------------------------------
# Registry invariants
# ---------------------------------------------------------------------------


def test_every_tool_declares_read_access() -> None:
    """All GitHub tools are read-level; a write tool here must be a choice."""
    assert set(TOOL_ACCESS) == GITHUB_TOOL_NAMES
    assert set(TOOL_ACCESS.values()) == {"read"}


def test_tool_names_are_unique() -> None:
    """Duplicate tool names would silently shadow each other."""
    names = [str(t["name"]) for t in ALL_TOOLS]
    assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# execute_tool
# ---------------------------------------------------------------------------


def test_list_repos_trims_fields() -> None:
    """Repo listings keep only the fields the model needs."""
    client = MagicMock()
    client.list_repos.return_value = [
        {
            "name": "aieng-bot",
            "description": "bot",
            "language": "Python",
            "archived": False,
            "pushed_at": "2026-07-01T00:00:00Z",
            "html_url": "https://github.com/VectorInstitute/aieng-bot",
            "ssh_url": "git@github.com:VectorInstitute/aieng-bot.git",
        }
    ]

    result = json.loads(execute_tool("list_repos", {"limit": 5}, client))

    client.list_repos.assert_called_once_with(limit=5)
    assert result[0]["name"] == "aieng-bot"
    assert "ssh_url" not in result[0]


def test_get_file_decodes_base64_content() -> None:
    """File contents arrive base64-encoded and are decoded for the model."""
    client = MagicMock()
    client.get_file.return_value = {
        "name": "README.md",
        "path": "README.md",
        "html_url": "https://github.com/x",
        "content": base64.b64encode(b"# aieng-bot\n").decode(),
    }

    result = json.loads(
        execute_tool("get_file", {"repo": "aieng-bot", "path": "README.md"}, client)
    )

    assert result["content"] == "# aieng-bot\n"
    assert result["url"] == "https://github.com/x"


def test_get_file_reports_directories() -> None:
    """A directory path returns its entries instead of failing."""
    client = MagicMock()
    client.get_file.return_value = [{"path": "src/a.py"}, {"path": "src/b.py"}]

    result = json.loads(
        execute_tool("get_file", {"repo": "aieng-bot", "path": "src"}, client)
    )

    assert result["entries"] == ["src/a.py", "src/b.py"]


def test_list_issues_filters_pull_requests() -> None:
    """GitHub's issues API interleaves PRs; only true issues survive."""
    client = MagicMock()
    client.list_issues.return_value = [
        {"number": 1, "title": "Real issue", "labels": [], "user": {"login": "a"}},
        {
            "number": 2,
            "title": "Actually a PR",
            "labels": [],
            "user": {"login": "b"},
            "pull_request": {"url": "..."},
        },
    ]

    result = json.loads(execute_tool("list_issues", {"repo": "aieng-bot"}, client))

    assert [i["number"] for i in result] == [1]


def test_get_pull_request_combines_meta_files_and_comments() -> None:
    """One tool call returns the PR, its files, and recent discussion."""
    client = MagicMock()
    client.get_pull_request.return_value = {
        "number": 12,
        "title": "Bump httpx",
        "user": {"login": "dependabot[bot]"},
        "state": "open",
        "body": "Bumps httpx.",
        "base": {"ref": "main"},
        "head": {"ref": "dependabot/httpx"},
        "html_url": "https://github.com/x/pull/12",
    }
    client.list_pull_request_files.return_value = [
        {"filename": "pyproject.toml", "status": "modified"}
    ]
    client.list_issue_comments.return_value = [
        {"user": {"login": "amrit110"}, "body": "LGTM", "created_at": "t"}
    ]

    result = json.loads(
        execute_tool("get_pull_request", {"repo": "aieng-bot", "number": 12}, client)
    )

    assert result["files"] == [{"path": "pyproject.toml", "status": "modified"}]
    assert result["comments"][0]["author"] == "amrit110"
    assert result["base"] == "main"


def test_get_ci_status_defaults_to_default_branch() -> None:
    """Omitting the ref resolves the repository's default branch first."""
    client = MagicMock()
    client.get_repo.return_value = {"default_branch": "develop"}
    client.get_check_runs.return_value = {
        "check_runs": [
            {"name": "pytest", "status": "completed", "conclusion": "success"},
            {"name": "mypy", "status": "completed", "conclusion": "failure"},
        ]
    }

    result = json.loads(execute_tool("get_ci_status", {"repo": "aieng-bot"}, client))

    client.get_check_runs.assert_called_once_with("aieng-bot", "develop")
    assert result["ref"] == "develop"
    assert result["summary"] == {"success": 1, "failure": 1}


def test_unknown_tool_and_errors_are_reported_not_raised() -> None:
    """The executor degrades to error strings the model can react to."""
    client = MagicMock()
    client.get_repo.side_effect = RuntimeError("boom")

    assert execute_tool("frobnicate", {}, client) == "Unknown tool: frobnicate"
    assert execute_tool("get_repo", {"repo": "x"}, client).startswith(
        "Error executing get_repo"
    )


# ---------------------------------------------------------------------------
# Source attribution (resolve_event)
# ---------------------------------------------------------------------------


def _agent() -> GithubQAAgent:
    with (
        patch("slack_agent.agents.toolloop.anthropic.Anthropic"),
        patch("slack_agent.agents.toolloop.anthropic.AsyncAnthropic"),
        patch("slack_agent.agents.github.agent.GitHubClient"),
    ):
        return GithubQAAgent(auth=MagicMock(), api_key="sk-ant-test")


def test_resolve_event_links_pull_requests() -> None:
    """PR reads surface a numbered title and the GitHub URL."""
    agent = _agent()
    result = json.dumps(
        {"number": 12, "title": "Bump httpx", "url": "https://github.com/x/pull/12"}
    )

    resolved = agent.resolve_event("get_pull_request", {}, result)

    assert resolved == {
        "page_title": "#12 Bump httpx",
        "page_url": "https://github.com/x/pull/12",
    }


def test_resolve_event_links_files_with_repo_prefix() -> None:
    """File reads are attributed as repo/path."""
    agent = _agent()
    result = json.dumps(
        {"name": "README.md", "path": "docs/README.md", "url": "https://github.com/y"}
    )

    resolved = agent.resolve_event("get_file", {"repo": "aieng-bot"}, result)

    assert resolved is not None
    assert resolved["page_title"] == "aieng-bot/docs/README.md"


def test_resolve_event_ignores_list_tools_and_bad_json() -> None:
    """Only detail reads produce attribution events."""
    agent = _agent()

    assert agent.resolve_event("list_repos", {}, "[]") is None
    assert agent.resolve_event("get_repo", {}, "Error executing get_repo") is None
