"""Tests for client-side history compaction."""

from types import SimpleNamespace

import pytest

from slack_agent.agents.compaction import HistoryCompactor, _render_transcript
from slack_agent.agents.history import history_tokens


class FakeLLM:
    """Anthropic-shaped async client returning a canned summary."""

    def __init__(self, summary: str = "- summary", fail: bool = False) -> None:
        """Record calls; optionally raise instead of answering."""
        self.calls: list[dict] = []
        self._summary = summary
        self._fail = fail
        self.messages = self

    async def create(self, **kwargs):
        """Stand-in for ``client.messages.create``."""
        self.calls.append(kwargs)
        if self._fail:
            raise RuntimeError("llm unavailable")
        block = SimpleNamespace(type="text", text=self._summary)
        return SimpleNamespace(content=[block])


def _history(turns: int, filler: int = 4000) -> list[dict]:
    entries: list[dict] = []
    for i in range(turns):
        entries += [
            {"role": "user", "content": f"question {i}"},
            {"role": "assistant", "content": f"answer {i} " + "x" * filler},
        ]
    return entries


class TestHistoryCompactor:
    """Compaction triggering, folding, and failure fallback."""

    @pytest.mark.asyncio
    async def test_under_budget_is_untouched(self):
        """No compaction call happens below the trigger threshold."""
        llm = FakeLLM()
        compactor = HistoryCompactor(llm, "m", context_window=1_000_000)
        history = _history(3)
        assert await compactor.compact(history) is history
        assert llm.calls == []

    @pytest.mark.asyncio
    async def test_over_budget_folds_summary_plus_tail(self):
        """Over the trigger, the head becomes a summary and the tail stays."""
        llm = FakeLLM(summary="- earlier turns summarized")
        compactor = HistoryCompactor(llm, "m", context_window=20_000)
        history = _history(10)
        compacted = await compactor.compact(history)

        assert "<conversation_summary>" in compacted[0]["content"]
        assert "- earlier turns summarized" in compacted[0]["content"]
        assert compacted[-1] == history[-1]
        assert history_tokens(compacted) < history_tokens(history)
        assert llm.calls[0]["model"] == "m"

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_hard_trim(self):
        """A failed summary call trims instead of growing without bound."""
        compactor = HistoryCompactor(FakeLLM(fail=True), "m", context_window=20_000)
        history = _history(10)
        compacted = await compactor.compact(history)

        assert history_tokens(compacted) <= compactor.trigger_tokens
        assert all("<conversation_summary>" not in str(e) for e in compacted)

    @pytest.mark.asyncio
    async def test_compaction_is_cumulative(self):
        """A previous summary is part of the head of the next compaction."""
        llm = FakeLLM(summary="- second summary")
        compactor = HistoryCompactor(llm, "m", context_window=20_000)
        first = await compactor.compact(_history(10))
        second = await compactor.compact(first + _history(10, filler=4000))

        transcript = llm.calls[-1]["messages"][0]["content"]
        assert "<conversation_summary>" in transcript
        assert "- second summary" in second[0]["content"]


class TestTranscript:
    """Transcript rendering for the summarization request."""

    def test_condenses_tool_blocks(self):
        """Tool calls and results appear condensed, not verbatim."""
        head = [
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "get_page",
                        "input": {"page_id": 7},
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "content": "z" * 9000}],
            },
        ]
        transcript = _render_transcript(head)
        assert "get_page" in transcript
        assert len(transcript) < 3000
