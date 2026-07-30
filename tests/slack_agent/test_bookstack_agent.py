"""Unit tests for BookstackQAAgent — sync and async paths."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from slack_agent.agents.bookstack.agent import BookstackQAAgent, MessageHistory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_tool_use_block(
    name: str, tool_id: str, tool_input: dict[str, Any]
) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = tool_input
    return block


def _make_sync_response(content: list[MagicMock]) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    return resp


def _make_text_delta_event(text: str) -> MagicMock:
    """Build a fake content_block_delta event with a text_delta."""
    delta = MagicMock()
    delta.type = "text_delta"
    delta.text = text

    event = MagicMock()
    event.type = "content_block_delta"
    event.delta = delta
    return event


def _make_tool_use_block_start_event(name: str) -> MagicMock:
    """Build a fake content_block_start event with a tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = name

    event = MagicMock()
    event.type = "content_block_start"
    event.content_block = block
    return event


def _make_stream_ctx(
    events: list[MagicMock],
    final_message: MagicMock,
) -> MagicMock:
    """Build a MagicMock that behaves as an async context manager and async iterable.

    Required by ``async with client.messages.stream() as s: async for e in s:``.
    """
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=ctx)
    ctx.__aexit__ = AsyncMock(return_value=False)
    ctx.get_final_message = AsyncMock(return_value=final_message)

    # async for requires __aiter__ returning an object with __anext__
    async def _aiter() -> Any:
        for ev in events:
            yield ev

    ctx.__aiter__ = MagicMock(return_value=_aiter())
    return ctx


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def agent() -> BookstackQAAgent:
    """Return an agent with all external clients mocked."""
    with (
        patch("slack_agent.agents.bookstack.agent.anthropic.Anthropic"),
        patch("slack_agent.agents.bookstack.agent.anthropic.AsyncAnthropic"),
        patch("slack_agent.agents.bookstack.agent.BookStackClient"),
    ):
        return BookstackQAAgent(
            base_url="https://bookstack.example.com",
            token_id="id",
            token_secret="secret",
            api_key="sk-ant-test",
        )


# ---------------------------------------------------------------------------
# Sync path
# ---------------------------------------------------------------------------


class TestAskSync:
    """Tests for BookstackQAAgent.ask()."""

    def test_ask_no_tools(self, agent: BookstackQAAgent) -> None:
        """Single-turn Q&A with no tool calls returns answer directly."""
        response = _make_sync_response([_make_text_block("Paris is the capital.")])
        agent._sync_client.messages.create.return_value = response  # type: ignore[attr-defined]

        answer, history = agent.ask("What is the capital of France?")

        assert answer == "Paris is the capital."
        assert history[-1] == {"role": "assistant", "content": "Paris is the capital."}

    def test_ask_prepends_history(self, agent: BookstackQAAgent) -> None:
        """Prior conversation history is prepended before the new question."""
        prior: MessageHistory = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        response = _make_sync_response([_make_text_block("Answer.")])
        agent._sync_client.messages.create.return_value = response  # type: ignore[attr-defined]

        agent.ask("Follow-up?", history=prior)

        call_kwargs = agent._sync_client.messages.create.call_args.kwargs  # type: ignore[attr-defined]
        msgs = call_kwargs["messages"]
        assert msgs[0] == {"role": "user", "content": "Hi"}
        assert msgs[1] == {"role": "assistant", "content": "Hello!"}
        assert msgs[2] == {"role": "user", "content": "Follow-up?"}

    def test_ask_with_one_tool_call(self, agent: BookstackQAAgent) -> None:
        """Agent executes a tool call then produces a final answer."""
        tool_resp = _make_sync_response(
            [_make_tool_use_block("search_bookstack", "tu_1", {"query": "onboarding"})]
        )
        final_resp = _make_sync_response([_make_text_block("Onboarding info here.")])
        agent._sync_client.messages.create.side_effect = [tool_resp, final_resp]  # type: ignore[attr-defined]

        with patch(
            "slack_agent.agents.bookstack.agent.execute_tool",
            return_value=json.dumps({"data": [], "total": 0}),
        ):
            answer, _ = agent.ask("What is the onboarding process?")

        assert answer == "Onboarding info here."
        assert agent._sync_client.messages.create.call_count == 2  # type: ignore[attr-defined]

    def test_ask_raises_after_max_turns(self, agent: BookstackQAAgent) -> None:
        """ask() raises RuntimeError if tool-use loop exceeds MAX_TURNS."""
        tool_resp = _make_sync_response(
            [_make_tool_use_block("search_bookstack", "tu_1", {"query": "q"})]
        )
        agent._sync_client.messages.create.return_value = tool_resp  # type: ignore[attr-defined]

        with (
            patch("slack_agent.agents.bookstack.agent.execute_tool", return_value="{}"),
            pytest.raises(RuntimeError, match="Max tool-use turns"),
        ):
            agent.ask("Loop forever?")

    def test_ask_missing_api_key_raises(self) -> None:
        """Constructing the agent without an API key raises ValueError."""
        with (
            patch("os.environ.get", return_value=None),
            pytest.raises(ValueError, match="ANTHROPIC_API_KEY"),
        ):
            BookstackQAAgent(
                base_url="https://example.com",
                token_id="id",
                token_secret="secret",
                api_key=None,
            )


# ---------------------------------------------------------------------------
# Async streaming path
# ---------------------------------------------------------------------------


class TestAskStream:
    """Tests for BookstackQAAgent.ask_stream()."""

    @pytest.mark.asyncio
    async def test_stream_direct_answer_yields_text_chunks_and_answer(
        self, agent: BookstackQAAgent
    ) -> None:
        """ask_stream() yields text_chunk events then a final answer event."""
        text_event = _make_text_delta_event("Paris.")
        final_msg = _make_sync_response([_make_text_block("Paris.")])
        ctx = _make_stream_ctx([text_event], final_msg)

        agent._async_client.messages.stream.return_value = ctx  # type: ignore[attr-defined]

        events = []
        async for evt in agent.ask_stream("Capital of France?"):
            events.append(evt)

        types = [e["type"] for e in events]
        assert "text_chunk" in types
        assert types[-1] == "answer"
        assert events[-1]["text"] == "Paris."
        assert "history" in events[-1]

    @pytest.mark.asyncio
    async def test_stream_tool_use_then_answer(self, agent: BookstackQAAgent) -> None:
        """ask_stream() yields tool_use events then the final answer."""
        # Turn 1: no text events, final message has a tool_use block
        tool_final = _make_sync_response(
            [_make_tool_use_block("search_bookstack", "tu_1", {"query": "policy"})]
        )
        ctx1 = _make_stream_ctx([], tool_final)

        # Turn 2: text event, final message has just text
        answer_text_event = _make_text_delta_event("The policy says…")
        answer_final = _make_sync_response([_make_text_block("The policy says…")])
        ctx2 = _make_stream_ctx([answer_text_event], answer_final)

        agent._async_client.messages.stream.side_effect = [ctx1, ctx2]  # type: ignore[attr-defined]

        with patch(
            "slack_agent.agents.bookstack.agent.execute_tool",
            return_value=json.dumps({"data": [], "total": 0}),
        ):
            events = []
            async for evt in agent.ask_stream("What is the leave policy?"):
                events.append(evt)

        types = [e["type"] for e in events]
        assert "tool_use" in types
        assert types[-1] == "answer"
        assert events[-1]["text"] == "The policy says…"

    @pytest.mark.asyncio
    async def test_stream_yields_error_on_exception(
        self, agent: BookstackQAAgent
    ) -> None:
        """ask_stream() yields an error event when an unexpected exception occurs."""
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("API down"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        agent._async_client.messages.stream.return_value = ctx  # type: ignore[attr-defined]

        events = []
        async for evt in agent.ask_stream("Will this fail?"):
            events.append(evt)

        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "API down" in events[0]["message"]

    @pytest.mark.asyncio
    async def test_stream_history_returned_in_answer_event(
        self, agent: BookstackQAAgent
    ) -> None:
        """The answer event must include updated history for the next turn."""
        final_msg = _make_sync_response([_make_text_block("Done.")])
        ctx = _make_stream_ctx([], final_msg)
        agent._async_client.messages.stream.return_value = ctx  # type: ignore[attr-defined]

        prior: MessageHistory = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        events = []
        async for evt in agent.ask_stream("Next question?", history=prior):
            events.append(evt)

        answer_event = next(e for e in events if e["type"] == "answer")
        history = answer_event["history"]

        assert history[0] == {"role": "user", "content": "Hello"}
        assert history[1] == {"role": "assistant", "content": "Hi there!"}
        assert history[2] == {"role": "user", "content": "Next question?"}

    @pytest.mark.asyncio
    async def test_stream_get_page_emits_tool_resolve(
        self, agent: BookstackQAAgent
    ) -> None:
        """get_page tool call emits a tool_resolve event with the page title."""
        tool_final = _make_sync_response(
            [_make_tool_use_block("get_page", "tu_1", {"page_id": 7})]
        )
        ctx1 = _make_stream_ctx([], tool_final)

        answer_final = _make_sync_response(
            [_make_text_block("See the onboarding page.")]
        )
        ctx2 = _make_stream_ctx([], answer_final)

        agent._async_client.messages.stream.side_effect = [ctx1, ctx2]  # type: ignore[attr-defined]

        page_result = json.dumps(
            {"id": 7, "name": "Onboarding Guide", "markdown": "# Hi"}
        )
        with patch(
            "slack_agent.agents.bookstack.agent.execute_tool", return_value=page_result
        ):
            events = []
            async for evt in agent.ask_stream("What is onboarding?"):
                events.append(evt)

        resolve_events = [e for e in events if e["type"] == "tool_resolve"]
        assert len(resolve_events) == 1
        assert resolve_events[0]["page_id"] == 7
        assert resolve_events[0]["page_title"] == "Onboarding Guide"

    @pytest.mark.asyncio
    async def test_stream_no_history_starts_fresh(
        self, agent: BookstackQAAgent
    ) -> None:
        """With no prior history the first message is the user question."""
        final_msg = _make_sync_response([_make_text_block("Answer.")])
        ctx = _make_stream_ctx([], final_msg)
        agent._async_client.messages.stream.return_value = ctx  # type: ignore[attr-defined]

        events = []
        async for evt in agent.ask_stream("Fresh start?"):
            events.append(evt)

        answer_event = next(e for e in events if e["type"] == "answer")
        history = answer_event["history"]
        assert history[0] == {"role": "user", "content": "Fresh start?"}

    @pytest.mark.asyncio
    async def test_stream_thinking_text_buffered_not_emitted_before_tool_call(
        self, agent: BookstackQAAgent
    ) -> None:
        """Text before </think> is buffered silently — no text_chunk or text_clear emitted."""
        # Qwen3 pattern: turn 1 has thinking text + </think> + (empty) + tool_use block
        think_event = _make_text_delta_event("Let me search.\n</think>\n\n")
        tool_start_event = _make_tool_use_block_start_event("search_bookstack")
        tool_final = _make_sync_response(
            [_make_tool_use_block("search_bookstack", "tu_1", {"query": "policy"})]
        )
        ctx1 = _make_stream_ctx([think_event, tool_start_event], tool_final)

        # Turn 2: actual answer (no thinking)
        answer_final = _make_sync_response([_make_text_block("The policy says…")])
        ctx2 = _make_stream_ctx([], answer_final)

        agent._async_client.messages.stream.side_effect = [ctx1, ctx2]  # type: ignore[attr-defined]

        with patch(
            "slack_agent.agents.bookstack.agent.execute_tool",
            return_value=json.dumps({"data": [], "total": 0}),
        ):
            events = []
            async for evt in agent.ask_stream("What is the leave policy?"):
                events.append(evt)

        types = [e["type"] for e in events]
        # Thinking text must never appear as a text_chunk
        assert "text_clear" not in types, (
            "no text was streamed so text_clear is unnecessary"
        )
        assert "tool_use" in types
        assert types[-1] == "answer"

    @pytest.mark.asyncio
    async def test_stream_thinking_model_final_answer_streams_post_think(
        self, agent: BookstackQAAgent
    ) -> None:
        """For a thinking model, only text after </think> is emitted as text_chunk."""
        # </think> splits from thinking; answer follows in real time
        think_chunk = _make_text_delta_event("Thinking...\n</think>\n\n")
        answer_chunk = _make_text_delta_event("Paris.")
        final_msg = _make_sync_response([_make_text_block("Paris.")])
        ctx = _make_stream_ctx([think_chunk, answer_chunk], final_msg)
        agent._async_client.messages.stream.return_value = ctx  # type: ignore[attr-defined]

        events = []
        async for evt in agent.ask_stream("Capital of France?"):
            events.append(evt)

        types = [e["type"] for e in events]
        chunks = [e["chunk"] for e in events if e["type"] == "text_chunk"]
        # Only post-think text should appear
        assert all("think" not in c.lower() for c in chunks)
        assert "Paris." in chunks
        assert types[-1] == "answer"
        assert events[-1]["text"] == "Paris."

    @pytest.mark.asyncio
    async def test_stream_text_clear_emitted_when_post_think_text_precedes_tool_call(
        self, agent: BookstackQAAgent
    ) -> None:
        """text_clear fires only when text *after* </think> was already streamed."""
        # Model generates thinking + </think> + "Let me search." + tool_use
        think_event = _make_text_delta_event("Thinking...\n</think>\n\n")
        bridge_event = _make_text_delta_event("Let me search.")
        tool_start = _make_tool_use_block_start_event("search_bookstack")
        tool_final = _make_sync_response(
            [_make_tool_use_block("search_bookstack", "tu_1", {"query": "policy"})]
        )
        ctx1 = _make_stream_ctx([think_event, bridge_event, tool_start], tool_final)

        answer_final = _make_sync_response([_make_text_block("The policy says…")])
        ctx2 = _make_stream_ctx([], answer_final)
        agent._async_client.messages.stream.side_effect = [ctx1, ctx2]  # type: ignore[attr-defined]

        with patch(
            "slack_agent.agents.bookstack.agent.execute_tool",
            return_value=json.dumps({"data": [], "total": 0}),
        ):
            events = []
            async for evt in agent.ask_stream("What is the leave policy?"):
                events.append(evt)

        types = [e["type"] for e in events]
        assert "text_chunk" in types  # "Let me search." was streamed
        assert "text_clear" in types  # then discarded when tool_use detected
        assert "tool_use" in types
        assert types[-1] == "answer"
