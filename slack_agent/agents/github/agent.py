"""GitHub QA agent: the shared tool loop bound to the GitHub tools."""

import json
from typing import Any, ClassVar

from ..toolloop import MessageHistory, ToolLoopAgent
from .auth import TokenProvider
from .client import GitHubClient
from .prompts import SYSTEM_PROMPT
from .tools import ALL_TOOLS, GITHUB_TOOL_NAMES, execute_tool

__all__ = ["GithubQAAgent", "MessageHistory"]

# Tools whose results carry a linkable source the reply UI attributes.
_SOURCE_TOOLS = frozenset({"get_repo", "get_file", "get_pull_request", "get_issue"})


class GithubQAAgent(ToolLoopAgent):
    """Answer questions about the GitHub org using Claude with tool use.

    All GitHub tools are read-only and pinned to one organization. See
    :class:`~slack_agent.agents.toolloop.ToolLoopAgent` for the loop
    machinery and the LLM backend parameters.

    Parameters
    ----------
    auth : TokenProvider
        Source of GitHub API tokens (App installation tokens or a PAT).
    org : str
        GitHub organization all lookups are pinned to.
    api_key, model, llm_base_url, llm_api_key
        LLM backend configuration, see :class:`ToolLoopAgent`.

    """

    DEFAULT_SYSTEM: ClassVar[str] = SYSTEM_PROMPT
    DEFAULT_TOOLS: ClassVar[list[Any]] = ALL_TOOLS
    native_tool_names: ClassVar[frozenset[str]] = GITHUB_TOOL_NAMES

    def __init__(
        self,
        auth: TokenProvider,
        org: str = "VectorInstitute",
        api_key: str | None = None,
        model: str | None = None,
        llm_base_url: str | None = None,
        llm_api_key: str | None = None,
    ) -> None:
        """Initialise the agent and its GitHub client."""
        super().__init__(
            api_key=api_key,
            model=model,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
        )
        self.github = GitHubClient(auth, org=org)

    def execute_native(
        self, name: str, tool_input: dict[str, Any], attribution: str = ""
    ) -> str:
        """Execute a GitHub tool call (read-only; attribution unused)."""
        return execute_tool(name, tool_input, self.github)

    def resolve_event(
        self, name: str, tool_input: dict[str, Any], result: str
    ) -> dict[str, Any] | None:
        """Attribute reads with the item's title and GitHub URL."""
        if name not in _SOURCE_TOOLS:
            return None
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        title = str(data.get("title") or data.get("name") or "")
        if name == "get_file" and title:
            title = f"{tool_input.get('repo', '')}/{data.get('path') or title}"
        elif name in {"get_pull_request", "get_issue"} and title:
            title = f"#{data.get('number', '?')} {title}"
        if not title:
            return None
        return {"page_title": title, "page_url": str(data.get("url") or "")}
