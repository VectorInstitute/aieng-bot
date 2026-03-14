"""BookStack QA agent — sync and async (streaming) interfaces."""

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from typing import Any, cast

import anthropic
from anthropic.types import MessageParam  # used in cast() calls below

from ..config import get_model_name
from ..utils.logging import log_info
from .client import BookStackClient
from .prompts import SYSTEM_PROMPT
from .tools import ALL_TOOLS, execute_tool

# Full Anthropic message list — includes interleaved user/assistant/tool turns.
# Typed as list[Any] because intermediate turns contain ToolUseBlockParam /
# ToolResultBlockParam whose dict representations don't satisfy Pyright's strict
# MessageParam[content] constraints; cast to list[MessageParam] at call sites.
MessageHistory = list[Any]


class BookstackQAAgent:
    """Answer questions from the BookStack wiki using Claude with tool use.

    Supports multi-turn conversations by accepting and returning a
    ``MessageHistory`` (the Anthropic message list including tool-use rounds).
    Callers are responsible for persisting history between turns.

    Provides two entry points:

    - :meth:`ask` — synchronous, for CLI use.
    - :meth:`ask_stream` — async generator, for SSE streaming API responses.
      Uses the Anthropic streaming API so text tokens are emitted as they are
      generated, enabling character-by-character rendering in the UI.

    Parameters
    ----------
    base_url : str
        Root URL of the BookStack instance.
    token_id : str
        BookStack API token ID.
    token_secret : str
        BookStack API token secret.
    api_key : str, optional
        Anthropic API key. Defaults to ``ANTHROPIC_API_KEY`` env var.
    model : str, optional
        Claude model name. Defaults to :func:`~aieng_bot.config.get_model_name`.

    """

    MAX_TURNS = 16

    def __init__(
        self,
        base_url: str,
        token_id: str,
        token_secret: str,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        """Initialise the agent."""
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

        self._sync_client = anthropic.Anthropic(api_key=resolved_key)
        self._async_client = anthropic.AsyncAnthropic(api_key=resolved_key)
        self.bookstack = BookStackClient(base_url, token_id, token_secret)
        self.model = model or get_model_name()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _content_from_response(response: Any) -> list[dict[str, Any]]:
        """Convert a model response content list into serialisable dicts."""
        result: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "text":
                result.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                result.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
        return result

    @staticmethod
    def _extract_text(response: Any) -> str:
        return "".join(b.text for b in response.content if hasattr(b, "text")).strip()

    # ------------------------------------------------------------------
    # Sync path (CLI)
    # ------------------------------------------------------------------

    def ask(
        self,
        question: str,
        history: MessageHistory | None = None,
    ) -> tuple[str, MessageHistory]:
        """Answer a question synchronously, returning answer + updated history.

        Parameters
        ----------
        question : str
            The user's question.
        history : MessageHistory, optional
            Prior conversation turns for multi-turn support.

        Returns
        -------
        tuple[str, MessageHistory]
            ``(answer_markdown, updated_history)``

        Raises
        ------
        RuntimeError
            If the tool-use loop exceeds :attr:`MAX_TURNS`.

        """
        messages: MessageHistory = list(history or [])
        messages.append({"role": "user", "content": question})

        for _ in range(self.MAX_TURNS):
            response = self._sync_client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=ALL_TOOLS,
                messages=cast(list[MessageParam], messages),
            )

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                answer = self._extract_text(response)
                messages.append({"role": "assistant", "content": answer})
                return answer, messages

            messages.append(
                {"role": "assistant", "content": self._content_from_response(response)}
            )

            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses:
                log_info(f"  tool: {tu.name}({tu.input})")
                ti = dict(tu.input) if isinstance(tu.input, dict) else {}
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": execute_tool(tu.name, ti, self.bookstack),
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        raise RuntimeError(f"Max tool-use turns ({self.MAX_TURNS}) exceeded")

    # ------------------------------------------------------------------
    # Async streaming path (API)
    # ------------------------------------------------------------------

    async def ask_stream(
        self,
        question: str,
        history: MessageHistory | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Answer a question, yielding structured SSE events as they occur.

        Uses the Anthropic streaming API so final-answer text tokens are
        forwarded to the client as they are generated.

        Event types (dict with ``type`` key):

        - ``{"type": "tool_use", "tool": "<name>", "input": {...}}``
          — emitted before each tool call (clears any in-progress text in UI).
        - ``{"type": "text_chunk", "chunk": "<text>"}``
          — incremental text token from the current turn's response.
          When a ``tool_use`` event follows, the UI should discard these
          (they were planning/thinking text, not the final answer).
        - ``{"type": "answer", "text": "<markdown>", "history": [...]}``
          — emitted once at the end confirming the complete answer and updated
          history. The caller must persist ``history`` for the next turn.
        - ``{"type": "error", "message": "<msg>"}``

        Parameters
        ----------
        question : str
            The user's question.
        history : MessageHistory, optional
            Prior conversation turns.

        Yields
        ------
        dict
            Structured event dictionaries.

        """
        messages: MessageHistory = list(history or [])
        messages.append({"role": "user", "content": question})

        try:
            for _ in range(self.MAX_TURNS):
                accumulated_text = ""
                final_response: Any = None

                # Use the streaming API so text tokens flow to the client immediately
                async with self._async_client.messages.stream(
                    model=self.model,
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    tools=ALL_TOOLS,
                    messages=cast(list[MessageParam], messages),
                ) as stream:
                    async for event in stream:
                        # Yield text tokens as they arrive (only TextDelta has .text)
                        if (
                            getattr(event, "type", None) == "content_block_delta"
                            and getattr(getattr(event, "delta", None), "type", None)
                            == "text_delta"
                        ):
                            chunk: str = event.delta.text  # type: ignore[union-attr]
                            accumulated_text += chunk
                            yield {"type": "text_chunk", "chunk": chunk}

                    final_response = await stream.get_final_message()

                tool_uses = [b for b in final_response.content if b.type == "tool_use"]

                if not tool_uses:
                    # Final answer — text was already streamed chunk-by-chunk above
                    answer = accumulated_text.strip() or self._extract_text(
                        final_response
                    )
                    messages.append({"role": "assistant", "content": answer})
                    yield {"type": "answer", "text": answer, "history": messages}
                    return

                # Tool-use turn: persist content and execute tools
                messages.append(
                    {
                        "role": "assistant",
                        "content": self._content_from_response(final_response),
                    }
                )

                tool_results: list[dict[str, Any]] = []
                for tu in tool_uses:
                    ti = dict(tu.input) if isinstance(tu.input, dict) else {}
                    # Signal UI to clear any in-progress text and show tool status
                    yield {"type": "tool_use", "tool": tu.name, "input": ti}
                    result = await asyncio.to_thread(
                        execute_tool, tu.name, ti, self.bookstack
                    )
                    # For get_page, emit the resolved page title so the UI can
                    # display it instead of the raw numeric ID.
                    if tu.name == "get_page":
                        try:
                            page_data = json.loads(result)
                            page_title = str(page_data.get("name") or "")
                            if page_title:
                                yield {
                                    "type": "tool_resolve",
                                    "page_id": ti.get("page_id"),
                                    "page_title": page_title,
                                }
                        except (json.JSONDecodeError, KeyError, ValueError):
                            pass
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": tu.id, "content": result}
                    )

                messages.append({"role": "user", "content": tool_results})

            yield {
                "type": "error",
                "message": f"Max tool-use turns ({self.MAX_TURNS}) exceeded",
            }

        except Exception as e:  # noqa: BLE001
            yield {"type": "error", "message": str(e)}
