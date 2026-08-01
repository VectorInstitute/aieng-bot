"""Generic streaming tool-use loop shared by sub-agent LLM drivers.

Every specialist sub-agent (BookStack QA, GitHub QA, …) needs the same
machinery: LLM client construction (direct Anthropic or gateway), a
streaming turn handler that copes with thinking models, sequential tool
execution with the extra-executor convention, and multi-turn history
management. :class:`ToolLoopAgent` owns all of that once; a subclass
contributes only its native tool roster, executor, and (optionally) a
resolve hook for source attribution events.
"""

import asyncio
import logging
import os
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, ClassVar, cast

import anthropic
from anthropic.types import MessageParam  # used in cast() calls below

from aieng_bot.config import get_model_name

logger = logging.getLogger(__name__)

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


class ToolLoopAgent:
    """Multi-turn Claude tool-use loop with sync and streaming entry points.

    Subclasses declare their native tools and how to execute them:

    - :attr:`DEFAULT_TOOLS` / :attr:`DEFAULT_SYSTEM` — roster and system
      prompt used when the caller does not supply their own.
    - :attr:`native_tool_names` — tool names executed natively via
      :meth:`execute_native`; anything else is dispatched to the
      per-request ``extra_executor`` (e.g. the Slack context tools).
    - :meth:`resolve_event` — optional hook turning a tool result into a
      ``tool_resolve`` event (source titles/URLs for the reply UI).

    Provides two entry points:

    - :meth:`ask` — synchronous, for CLI use.
    - :meth:`ask_stream` — async generator, for streaming replies.
      Uses the Anthropic streaming API so text tokens are emitted as they
      are generated, enabling character-by-character rendering in the UI.

    Parameters
    ----------
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

    DEFAULT_SYSTEM: ClassVar[str] = ""
    DEFAULT_TOOLS: ClassVar[list[Any]] = []
    native_tool_names: ClassVar[frozenset[str]] = frozenset()

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        llm_base_url: str | None = None,
        llm_api_key: str | None = None,
    ) -> None:
        """Initialise the LLM clients (gateway or direct Anthropic)."""
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

        self.model = model or get_model_name()

    @property
    def async_client(self) -> "anthropic.AsyncAnthropic":
        """The async LLM client, shared with harness services (compaction)."""
        return self._async_client

    # ------------------------------------------------------------------
    # Subclass hooks
    # ------------------------------------------------------------------

    def execute_native(
        self, name: str, tool_input: dict[str, Any], attribution: str = ""
    ) -> str:
        """Execute one native tool call synchronously; subclasses implement.

        Parameters
        ----------
        name : str
            Tool name (guaranteed to be in :attr:`native_tool_names`).
        tool_input : dict
            Tool input as provided by the model.
        attribution : str, optional
            Who requested the run; used for write provenance where the
            domain supports it.

        Returns
        -------
        str
            Tool result content (JSON string or error message).

        """
        raise NotImplementedError

    def resolve_event(
        self, name: str, tool_input: dict[str, Any], result: str
    ) -> dict[str, Any] | None:
        """Return extra fields for a ``tool_resolve`` event, if any.

        Subclasses override this to attribute finished tool calls (e.g.
        a page or PR title and URL the reply UI can link); None means
        no event.
        """
        return None

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
                system=self.DEFAULT_SYSTEM,
                tools=self.DEFAULT_TOOLS,
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
                logger.info("tool: %s(%s)", tu.name, tu.input)
                ti = dict(tu.input) if isinstance(tu.input, dict) else {}
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": self.execute_native(tu.name, ti),
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        raise RuntimeError(f"Max tool-use turns ({self.MAX_TURNS}) exceeded")

    # ------------------------------------------------------------------
    # Async streaming path
    # ------------------------------------------------------------------

    async def _stream_llm_turn(
        self,
        messages: MessageHistory,
        state: _TurnState,
        tools: list[Any],
        system: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Run one LLM streaming call; yield ``text_chunk``/``text_clear`` events.

        Populates *state* with the accumulated answer text, whether ``</think>``
        was seen, and the final message object.
        """
        skip_leading_nl = False

        async with self._async_client.messages.stream(
            model=self.model,
            max_tokens=8192,
            system=system,
            tools=tools,
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
        extra_executor: Callable[[str, dict[str, Any]], Awaitable[str]] | None = None,
        write_attribution: str = "",
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Execute tool calls sequentially; yield ``tool_use`` / ``tool_resolve`` events.

        Appends ``tool_result`` dicts to *tool_results* as each call
        completes. Results are passed via the caller-owned list (rather than
        instance state) so one shared agent can serve concurrent requests.
        Tools outside :attr:`native_tool_names` are dispatched to
        *extra_executor*.
        """
        for tu in tool_uses:
            ti = dict(tu.input) if isinstance(tu.input, dict) else {}
            yield {"type": "tool_use", "tool": tu.name, "input": ti}
            if extra_executor is not None and tu.name not in self.native_tool_names:
                result = await extra_executor(tu.name, ti)
            else:
                result = await asyncio.to_thread(
                    self.execute_native, tu.name, ti, write_attribution
                )
            resolved = self.resolve_event(tu.name, ti, result)
            if resolved:
                yield {"type": "tool_resolve", "tool": tu.name, **resolved}
            tool_results.append(
                {"type": "tool_result", "tool_use_id": tu.id, "content": result}
            )

    async def ask_stream(
        self,
        question: str,
        history: MessageHistory | None = None,
        extra_tools: list[Any] | None = None,
        extra_executor: Callable[[str, dict[str, Any]], Awaitable[str]] | None = None,
        extra_system: str = "",
        system: str | None = None,
        write_attribution: str = "",
        tools: list[Any] | None = None,
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
        - ``{"type": "tool_resolve", "tool": "<name>", ...}``
          — source attribution for a finished call (see :meth:`resolve_event`).
        - ``{"type": "answer", "text": "<markdown>", "history": [...]}``
          — final answer; caller must persist ``history`` for the next turn.
        - ``{"type": "error", "message": "<msg>"}``

        Parameters
        ----------
        question : str
            The user's question.
        history : MessageHistory, optional
            Prior conversation turns.
        extra_tools : list, optional
            Additional Anthropic tool definitions to expose alongside the
            native tools.
        extra_executor : callable, optional
            Async ``executor(name, tool_input) -> str`` handling any tool
            outside the native set.
        extra_system : str, optional
            Text appended to the default system prompt (e.g. tool
            guidance). Ignored when *system* is given.
        system : str, optional
            Complete system prompt to use verbatim, replacing the
            default assembly. Callers with a harness-built prompt (the
            Slack sub-agents) pass it here.
        write_attribution : str, optional
            Who requested this run; forwarded to the native executor so
            writes carry provenance where the domain supports it.
        tools : list, optional
            Complete tool roster for this run, replacing the default
            assembly. The harness passes a per-principal roster here;
            the API rejects calls to tools outside it, which is the
            authorization boundary.

        Yields
        ------
        dict
            Structured event dictionaries.

        """
        messages: MessageHistory = list(history or [])
        messages.append({"role": "user", "content": question})
        if tools is None:
            tools = [*self.DEFAULT_TOOLS, *(extra_tools or [])]
        if system is None:
            system = self.DEFAULT_SYSTEM + extra_system

        try:
            for _ in range(self.MAX_TURNS):
                state = _TurnState()
                async for event in self._stream_llm_turn(
                    messages, state, tools, system
                ):
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
                async for event in self._execute_tool_calls(
                    tool_uses, tool_results, extra_executor, write_attribution
                ):
                    yield event
                messages.append({"role": "user", "content": tool_results})

            yield {
                "type": "error",
                "message": f"Max tool-use turns ({self.MAX_TURNS}) exceeded",
            }

        except Exception as e:  # noqa: BLE001
            yield {"type": "error", "message": str(e)}
