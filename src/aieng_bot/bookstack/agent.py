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

# Thinking models (Qwen3, DeepSeek-R1, …) embed chain-of-thought reasoning in
# the text stream before this marker.  Text before it is buffered silently;
# only what follows is forwarded as answer content.
_THINK_END = "</think>"


class _TurnState:
    """Mutable container for the results of one LLM streaming turn."""

    __slots__ = ("accumulated_text", "thinking_done", "text_streamed", "final_response")

    def __init__(self) -> None:
        self.accumulated_text: str = ""
        self.thinking_done: bool = False
        self.text_streamed: bool = False
        self.final_response: Any = None


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
        API key for the LLM backend. Defaults to ``ANTHROPIC_API_KEY`` env var.
    model : str, optional
        Model name. Defaults to :func:`~aieng_bot.config.get_model_name`.
    llm_base_url : str, optional
        Base URL for the LLM backend. Set to point at a gateway (e.g.
        ``https://proxy.vectorinstitute.ai``) instead of the Anthropic API
        directly. Defaults to ``LLM_BASE_URL`` env var, or the Anthropic API
        if unset.
    llm_api_key : str, optional
        Bearer token for the LLM gateway. Required when ``llm_base_url`` is
        set; ignored otherwise. The gateway expects ``Authorization: Bearer``
        rather than the Anthropic ``x-api-key`` header. Defaults to
        ``LLM_API_KEY`` env var.

    """

    MAX_TURNS = 16

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
        """Initialise the agent."""
        resolved_llm_base_url = llm_base_url or os.environ.get("LLM_BASE_URL")

        if resolved_llm_base_url:
            # Gateway mode: the gateway requires Authorization: Bearer, not x-api-key.
            # LLM_API_KEY is the gateway-issued bearer token; ANTHROPIC_API_KEY is not used.
            resolved_llm_api_key = llm_api_key or os.environ.get("LLM_API_KEY")
            if not resolved_llm_api_key:
                raise ValueError(
                    "LLM_API_KEY must be set when LLM_BASE_URL is configured"
                )
            self._sync_client = anthropic.Anthropic(
                api_key=resolved_llm_api_key,
                base_url=resolved_llm_base_url,
                default_headers={"Authorization": f"Bearer {resolved_llm_api_key}"},
            )
            self._async_client = anthropic.AsyncAnthropic(
                api_key=resolved_llm_api_key,
                base_url=resolved_llm_base_url,
                default_headers={"Authorization": f"Bearer {resolved_llm_api_key}"},
            )
        else:
            # Direct Anthropic mode: standard x-api-key authentication.
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
                max_tokens=8192,
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

    async def _stream_llm_turn(
        self,
        messages: MessageHistory,
        state: _TurnState,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Run one LLM streaming call; yield ``text_chunk``/``text_clear`` events.

        Populates *state* with the accumulated answer text, whether ``</think>``
        was seen, and the final message object.
        """
        skip_leading_nl = False

        async with self._async_client.messages.stream(
            model=self.model,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            messages=cast(list[MessageParam], messages),
        ) as stream:
            async for event in stream:
                event_type = getattr(event, "type", None)

                if (
                    event_type == "content_block_delta"
                    and getattr(getattr(event, "delta", None), "type", None)
                    == "text_delta"
                ):
                    chunk: str = event.delta.text  # type: ignore[union-attr]
                    if not state.thinking_done:
                        state.accumulated_text += chunk
                        idx = state.accumulated_text.find(_THINK_END)
                        if idx >= 0:
                            state.thinking_done = True
                            skip_leading_nl = True
                            post = state.accumulated_text[
                                idx + len(_THINK_END) :
                            ].lstrip("\n")
                            state.accumulated_text = post
                            if post:
                                skip_leading_nl = False
                                yield {"type": "text_chunk", "chunk": post}
                                state.text_streamed = True
                    else:
                        if skip_leading_nl:
                            chunk = chunk.lstrip("\n")
                            if not chunk:
                                continue
                            skip_leading_nl = False
                        state.accumulated_text += chunk
                        yield {"type": "text_chunk", "chunk": chunk}
                        state.text_streamed = True

                elif event_type == "content_block_start":
                    block = getattr(event, "content_block", None)
                    if getattr(block, "type", None) == "tool_use":
                        if state.text_streamed:
                            yield {"type": "text_clear"}
                            state.text_streamed = False
                        state.accumulated_text = ""
                        state.thinking_done = False
                        skip_leading_nl = False

            state.final_response = await stream.get_final_message()

    async def _execute_tool_calls(
        self,
        tool_uses: list[Any],
        tool_results: list[dict[str, Any]],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Execute tool calls sequentially; yield ``tool_use`` / ``tool_resolve`` events.

        Appends ``tool_result`` dicts to *tool_results* as each call
        completes. Results are passed via the caller-owned list (rather than
        instance state) so one shared agent can serve concurrent requests.
        """
        for tu in tool_uses:
            ti = dict(tu.input) if isinstance(tu.input, dict) else {}
            yield {"type": "tool_use", "tool": tu.name, "input": ti}
            result = await asyncio.to_thread(execute_tool, tu.name, ti, self.bookstack)
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

    async def ask_stream(
        self,
        question: str,
        history: MessageHistory | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Answer a question, yielding structured SSE events as they occur.

        Handles thinking models (e.g. Qwen3) that embed reasoning inside
        ``</think>`` tags in the regular text stream.  Text before ``</think>``
        is silently discarded; text after it streams token-by-token.  Models
        that never emit ``</think>`` (Claude, GPT) have their text buffered
        and emitted as fast chunks once the response is complete.

        Event types (dict with ``type`` key):

        - ``{"type": "text_chunk", "chunk": "<text>"}``
          — incremental text token (post-think, or burst-emit for non-thinking
          models).
        - ``{"type": "text_clear"}``
          — discard streamed text; only emitted if post-think text was already
          streamed and a tool call follows.
        - ``{"type": "tool_use", "tool": "<name>", "input": {...}}``
          — emitted before each tool call.
        - ``{"type": "answer", "text": "<markdown>", "history": [...]}``
          — final answer; caller must persist ``history`` for the next turn.
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
                state = _TurnState()
                async for event in self._stream_llm_turn(messages, state):
                    yield event

                final_response = state.final_response
                tool_uses = [b for b in final_response.content if b.type == "tool_use"]

                if not tool_uses:
                    if state.thinking_done:
                        answer = state.accumulated_text.strip() or self._extract_text(
                            final_response
                        )
                    else:
                        # Non-thinking model: burst-emit buffer in small chunks.
                        raw = state.accumulated_text or self._extract_text(
                            final_response
                        )
                        answer = raw.strip()
                        chunk_size = 20
                        for i in range(0, len(answer), chunk_size):
                            yield {
                                "type": "text_chunk",
                                "chunk": answer[i : i + chunk_size],
                            }
                            await asyncio.sleep(0)
                    messages.append({"role": "assistant", "content": answer})
                    yield {"type": "answer", "text": answer, "history": messages}
                    return

                messages.append(
                    {
                        "role": "assistant",
                        "content": self._content_from_response(final_response),
                    }
                )
                tool_results: list[dict[str, Any]] = []
                async for event in self._execute_tool_calls(tool_uses, tool_results):
                    yield event
                messages.append({"role": "user", "content": tool_results})

            yield {
                "type": "error",
                "message": f"Max tool-use turns ({self.MAX_TURNS}) exceeded",
            }

        except Exception as e:  # noqa: BLE001
            yield {"type": "error", "message": str(e)}
