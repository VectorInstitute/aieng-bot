"""Tests for the streaming reply renderer.

The native-engine tests guard against the production truncation bug:
``chat.update`` cannot rewrite a natively streamed message (Slack rejects
it with ``block_mismatch``), so the final answer must be delivered through
``chat.appendStream`` deltas plus ``chat.stopStream`` — never ``chat.update``.
"""

import pytest

from slack_agent import streaming
from slack_agent.streaming import StreamingReply, _stream_delta


class DeadStreamError(Exception):
    """Duck-typed slack_sdk error for a stream Slack already ended."""

    def __init__(self) -> None:
        """Carry the response payload slack_sdk errors expose."""
        super().__init__("streaming_mode_mismatch")
        self.response = {"ok": False, "error": "streaming_mode_mismatch"}


class FakeSlackClient:
    """Records chat_* calls; optionally fails selected methods."""

    def __init__(
        self,
        fail_methods: set[str] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        """Set up call recording, failing any method named in *fail_methods*.

        *errors* raises a specific exception per method instead of the
        generic RuntimeError.
        """
        self.calls: list[tuple[str, dict]] = []
        self.fail_methods = fail_methods or set()
        self.errors = errors or {}
        self._seq = 0

    def __getattr__(self, name: str):
        """Return an async recorder for any chat_*/reactions_* method."""
        if not name.startswith(("chat_", "reactions_")):
            raise AttributeError(name)

        async def _call(**kwargs):
            self.calls.append((name, kwargs))
            if name in self.errors:
                raise self.errors[name]
            if name in self.fail_methods:
                raise RuntimeError(f"{name} rejected")
            self._seq += 1
            return {"ok": True, "ts": f"100.{self._seq:04d}"}

        return _call

    def named(self, method: str) -> list[dict]:
        """Return the kwargs of every recorded call to *method*."""
        return [kwargs for name, kwargs in self.calls if name == method]

    def streamed_text(self) -> str:
        """Return all markdown delivered through the native stream, in order."""
        return "".join(
            kwargs["markdown_text"]
            for name, kwargs in self.calls
            if name in {"chat_appendStream", "chat_stopStream"}
            and "markdown_text" in kwargs
        )


@pytest.fixture(autouse=True)
def _reset_capability_flags():
    """Isolate the process-wide capability flags between tests."""
    original = dict(streaming._CAPS)
    streaming._CAPS.update(
        {"native_stream": True, "native_tasks": True, "native_plan_block": True}
    )
    yield
    streaming._CAPS.update(original)


def _native_reply(client, min_interval: float = 0.0) -> StreamingReply:
    return StreamingReply(
        client,
        "C123",
        anchor_ts="1000.0001",
        reply_thread_ts="1000.0001",
        native_allowed=True,
        recipient_user_id="U1",
        recipient_team_id="T1",
        min_interval=min_interval,
    )


class TestNativeFinalize:
    """Finalizing a natively streamed reply."""

    @pytest.mark.asyncio
    async def test_full_answer_survives_throttled_burst(self):
        """Regression: burst chunks beyond the first were lost in production.

        Only the first 20-char chunk beat the flush throttle, and the
        finalizing ``chat.update`` failed with ``block_mismatch``, leaving
        the reply frozen at "Hello Amrit! How can".
        """
        client = FakeSlackClient()
        reply = _native_reply(client, min_interval=60.0)
        await reply.start()

        answer = "Hello Amrit! How can I help you today? Ask me about the docs."
        for i in range(0, len(answer), 20):
            reply.append_text(answer[i : i + 20])
            await reply.flush()
        await reply.finalize(answer)

        assert client.streamed_text() == answer
        assert client.named("chat_update") == []
        assert len(client.named("chat_stopStream")) == 1

    @pytest.mark.asyncio
    async def test_signoff_line_never_reaches_slack(self):
        """The reaction sign-off line is protocol and must stay invisible."""
        client = FakeSlackClient()
        reply = _native_reply(client)
        await reply.start()

        raw = "Hi there! Great to meet you.\n\nreaction: wave"
        for i in range(0, len(raw), 10):
            reply.append_text(raw[i : i + 10])
            await reply.flush()
        await reply.finalize("Hi there! Great to meet you.")

        assert "reaction" not in client.streamed_text()
        assert client.streamed_text().strip() == "Hi there! Great to meet you."

    @pytest.mark.asyncio
    async def test_footer_travels_on_stop_stream(self):
        """The activity footer rides chat.stopStream as a context block."""
        client = FakeSlackClient()
        reply = _native_reply(client)
        await reply.start()
        reply.append_text("The answer.")
        await reply.finalize("The answer.", footer="aieng-bot searched BookStack")

        (stop,) = client.named("chat_stopStream")
        assert stop["blocks"][0]["type"] == "context"
        assert "searched BookStack" in stop["blocks"][0]["elements"][0]["text"]

    @pytest.mark.asyncio
    async def test_stop_failure_reposts_full_answer(self):
        """If stopStream rejects the payload, the answer is posted fresh."""
        client = FakeSlackClient(fail_methods={"chat_stopStream"})
        reply = _native_reply(client)
        await reply.start()
        reply.append_text("Partial ")
        await reply.flush()
        await reply.finalize("Partial answer, now complete.")

        assert len(client.named("chat_delete")) == 1
        (post,) = client.named("chat_postMessage")
        assert post["thread_ts"] == "1000.0001"
        assert "Partial answer, now complete." in post["text"]

    @pytest.mark.asyncio
    async def test_clear_text_starts_new_paragraph_without_duplication(self):
        """Retracted preamble is retired in place; the answer is not doubled."""
        client = FakeSlackClient()
        reply = _native_reply(client)
        await reply.start()
        reply.append_text("Let me check the docs.")
        await reply.flush()
        reply.clear_text()
        reply.append_text("Cluster access needs a VPN.")
        await reply.flush()
        await reply.finalize("Cluster access needs a VPN.")

        assert client.streamed_text() == (
            "Let me check the docs.\n\nCluster access needs a VPN."
        )

    @pytest.mark.asyncio
    async def test_running_step_completes_on_finalize(self):
        """A step still running at finalize is marked complete, not stuck."""
        client = FakeSlackClient()
        reply = _native_reply(client)
        await reply.start()
        reply.begin_step("Drafting answer", "Drafted answer")
        await reply.finalize("Done.")

        chunk_calls = [
            kwargs for kwargs in client.named("chat_appendStream") if "chunks" in kwargs
        ]
        statuses = [c["status"] for kwargs in chunk_calls for c in kwargs["chunks"]]
        assert statuses[-1] == "complete"


class TestNativeFail:
    """Error rendering on a natively streamed reply."""

    @pytest.mark.asyncio
    async def test_fail_stops_stream_with_error_text(self):
        """Errors end the stream via stopStream, never chat.update."""
        client = FakeSlackClient()
        reply = _native_reply(client)
        await reply.start()
        reply.append_text("Working on ")
        await reply.flush()
        await reply.fail("boom")

        (stop,) = client.named("chat_stopStream")
        assert "Something went wrong: boom" in stop["markdown_text"]
        assert client.named("chat_update") == []

    @pytest.mark.asyncio
    async def test_fail_never_raises_and_falls_back_to_post(self):
        """fail() swallows API errors and posts the error as a new message."""
        client = FakeSlackClient(fail_methods={"chat_stopStream"})
        reply = _native_reply(client)
        await reply.start()
        await reply.fail("boom")

        (post,) = client.named("chat_postMessage")
        assert "Something went wrong: boom" in post["text"]


class TestEditInPlace:
    """The edit-in-place engine (top-level DMs and fallback)."""

    @pytest.mark.asyncio
    async def test_finalize_converts_markdown_to_mrkdwn(self):
        """finalize() receives raw markdown and converts it for Block Kit."""
        client = FakeSlackClient()
        reply = StreamingReply(client, "D123", anchor_ts="1.0", native_allowed=False)
        await reply.start()
        await reply.finalize("**Bold** and [docs](https://wiki.example.com)")

        assert client.named("chat_postMessage")
        section = client.named("chat_update")[-1]["blocks"][0]["text"]["text"]
        assert "*Bold*" in section
        assert "<https://wiki.example.com|docs>" in section

    @pytest.mark.asyncio
    async def test_native_start_failure_falls_back_to_placeholder(self):
        """When startStream is unavailable, the reply degrades gracefully."""
        client = FakeSlackClient(fail_methods={"chat_startStream"})
        reply = _native_reply(client)
        await reply.start()
        reply.append_text("Answer text.")
        await reply.finalize("Answer text.")

        assert client.named("chat_postMessage")
        assert client.named("chat_stopStream") == []
        assert client.named("chat_update")[-1]["text"] == "Answer text."


class TestStreamDemotion:
    """A stream Slack ended server-side must not kill the run.

    Regression for the production failure: a long BookStack run outlived
    the native stream, every ``chat.appendStream`` then failed with
    ``streaming_mode_mismatch``, and the user got "unexpected internal
    error" instead of the finished answer.
    """

    @pytest.mark.asyncio
    async def test_dead_stream_demotes_and_answer_still_arrives(self):
        """flush() survives a dead stream and finalize() delivers the answer."""
        client = FakeSlackClient(errors={"chat_appendStream": DeadStreamError()})
        reply = _native_reply(client)
        await reply.start()
        dead_ts = client.named("chat_startStream") and reply._ts

        reply.begin_step("Searching", "Searched")
        reply.append_text("Partial answer")
        await reply.flush()

        # Demoted: dead message deleted, fresh placeholder posted, state
        # re-rendered via chat.update.
        assert client.named("chat_delete")[0]["ts"] == dead_ts
        assert client.named("chat_postMessage")
        assert client.named("chat_update")

        await reply.finalize("Full answer.", footer="footer")
        final = client.named("chat_update")[-1]
        assert final["text"] == "Full answer."

    @pytest.mark.asyncio
    async def test_fail_on_dead_stream_renders_error_via_update(self):
        """fail() demotes instead of stranding the half-streamed message."""
        client = FakeSlackClient(
            errors={
                "chat_appendStream": DeadStreamError(),
                "chat_stopStream": DeadStreamError(),
            }
        )
        reply = _native_reply(client)
        await reply.start()
        await reply.fail("boom")

        update = client.named("chat_update")[-1]
        assert "Something went wrong: boom" in update["text"]

    @pytest.mark.asyncio
    async def test_other_append_errors_still_raise(self):
        """Only dead-stream errors demote; real API failures propagate."""
        client = FakeSlackClient(fail_methods={"chat_appendStream"})
        reply = _native_reply(client)
        await reply.start()
        reply.append_text("hi")

        with pytest.raises(RuntimeError):
            await reply.flush()


class TestDmNativeStart:
    """Top-level DMs stream natively, inline when Slack allows it."""

    def _dm_reply(self, client) -> StreamingReply:
        return StreamingReply(
            client,
            "D123",
            anchor_ts="1000.0001",
            reply_thread_ts=None,
            native_allowed=True,
            recipient_user_id="U1",
            recipient_team_id="T1",
            min_interval=0.0,
        )

    @pytest.mark.asyncio
    async def test_dm_streams_inline_without_thread(self):
        """A top-level DM opens the stream without forcing a thread."""
        client = FakeSlackClient()
        reply = self._dm_reply(client)
        await reply.start()

        (start,) = client.named("chat_startStream")
        assert "thread_ts" not in start
        reply.append_text("Hello!")
        await reply.flush()
        assert client.streamed_text() == "Hello!"

    @pytest.mark.asyncio
    async def test_dm_falls_back_to_threaded_stream(self):
        """If Slack requires threads for streams, the DM threads once."""

        class ThreadRequiredClient(FakeSlackClient):
            def __getattr__(self, name):
                call = super().__getattr__(name)
                if name != "chat_startStream":
                    return call

                async def _start(**kwargs):
                    if "thread_ts" not in kwargs:
                        self.calls.append((name, kwargs))
                        raise RuntimeError("thread required")
                    return await call(**kwargs)

                return _start

        client = ThreadRequiredClient()
        reply = self._dm_reply(client)
        await reply.start()

        starts = client.named("chat_startStream")
        assert len(starts) == 2
        assert starts[1]["thread_ts"] == "1000.0001"
        assert streaming._CAPS["native_stream"] is True
        await reply.finalize("Answer.")
        assert client.named("chat_stopStream")


class TestStreamDelta:
    """Delta computation for immutable native-stream appends."""

    def test_extends_sent_prefix(self):
        """New text beyond the sent prefix is the delta."""
        assert _stream_delta("Hello", "Hello world") == " world"

    def test_no_change(self):
        """Identical sent and target text yields no delta."""
        assert _stream_delta("Hello", "Hello") == ""

    def test_shrunken_target_waits(self):
        """A masked tail that shrank (forming protocol line) sends nothing."""
        assert _stream_delta("Hello\nre", "Hello") == ""

    def test_divergent_target_never_duplicates(self):
        """Divergent content is never re-sent as a duplicate."""
        assert _stream_delta("Hello there", "Goodbye") == ""

    def test_whitespace_only_delta_deferred(self):
        """Pure-whitespace deltas wait until real content follows."""
        assert _stream_delta("Hello", "Hello\n\n") == ""
        assert _stream_delta("Hello", "Hello\n\nMore") == "\n\nMore"
