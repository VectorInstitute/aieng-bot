"""BookStack QA agent: the shared tool loop bound to the BookStack tools."""

import json
from typing import Any, ClassVar

from ..toolloop import MessageHistory, ToolLoopAgent
from .client import BookStackClient
from .prompts import SYSTEM_PROMPT
from .tools import ALL_TOOLS, BOOKSTACK_TOOL_NAMES, execute_tool

__all__ = ["BookstackQAAgent", "MessageHistory"]

# Tools whose results carry a page the reply UI should attribute/link.
_PAGE_TOOLS = frozenset({"get_page", "create_page", "update_page"})


class BookstackQAAgent(ToolLoopAgent):
    """Answer questions from the BookStack wiki using Claude with tool use.

    Supports multi-turn conversations by accepting and returning a
    ``MessageHistory`` (the Anthropic message list including tool-use rounds).
    Callers are responsible for persisting history between turns. See
    :class:`~slack_agent.agents.toolloop.ToolLoopAgent` for the loop
    machinery and the LLM backend parameters.

    Parameters
    ----------
    base_url : str
        Root URL of the BookStack instance.
    token_id : str
        BookStack API token ID.
    token_secret : str
        BookStack API token secret.
    api_key, model, llm_base_url, llm_api_key
        LLM backend configuration, see :class:`ToolLoopAgent`.

    """

    DEFAULT_SYSTEM: ClassVar[str] = SYSTEM_PROMPT
    DEFAULT_TOOLS: ClassVar[list[Any]] = ALL_TOOLS
    native_tool_names: ClassVar[frozenset[str]] = BOOKSTACK_TOOL_NAMES

    def __init__(
        self,
        base_url: str,
        token_id: str,
        token_secret: str,
        api_key: str | None = None,
        model: str | None = None,
        llm_base_url: str | None = None,
        llm_api_key: str | None = None,
    ) -> None:
        """Initialise the agent and its BookStack client."""
        super().__init__(
            api_key=api_key,
            model=model,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
        )
        self.bookstack = BookStackClient(base_url, token_id, token_secret)

    def execute_native(
        self, name: str, tool_input: dict[str, Any], attribution: str = ""
    ) -> str:
        """Execute a BookStack tool call; writes carry *attribution*."""
        return execute_tool(name, tool_input, self.bookstack, attribution)

    def resolve_event(
        self, name: str, tool_input: dict[str, Any], result: str
    ) -> dict[str, Any] | None:
        """Attribute page reads/writes with the page title and URL."""
        if name not in _PAGE_TOOLS:
            return None
        try:
            page_data = json.loads(result)
        except json.JSONDecodeError:
            return None
        if not isinstance(page_data, dict):
            return None
        page_title = str(page_data.get("name") or "")
        if not page_title:
            return None
        return {
            "page_id": tool_input.get("page_id"),
            "page_title": page_title,
            "page_url": str(page_data.get("url") or ""),
        }
