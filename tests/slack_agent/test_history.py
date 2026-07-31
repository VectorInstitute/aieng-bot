"""Tests for token-aware history bookkeeping."""

from slack_agent.agents.history import (
    estimate_tokens,
    fold_summary,
    hard_trim,
    history_tokens,
    is_plain_user_turn,
    split_for_compaction,
)


def _turn(question: str, answer: str, filler: int = 0) -> list[dict]:
    """One user question plus assistant tool round-trip and answer."""
    return [
        {"role": "user", "content": question},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t1", "name": "search", "input": {}}
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": "x" * filler,
                }
            ],
        },
        {"role": "assistant", "content": answer},
    ]


class TestEstimator:
    """Token estimates."""

    def test_scales_with_content_size(self):
        """Bigger entries cost more tokens; empty entries still cost one."""
        small = estimate_tokens({"role": "user", "content": "hi"})
        large = estimate_tokens({"role": "user", "content": "hi" * 4000})
        assert 1 <= small < large
        assert large >= 2000

    def test_history_tokens_sums_entries(self):
        """The history total is the sum of per-entry estimates."""
        history = _turn("q", "a")
        assert history_tokens(history) == sum(estimate_tokens(e) for e in history)


class TestSplit:
    """Compaction split boundaries."""

    def test_never_separates_tool_pairs(self):
        """The cut always lands on a plain user turn, keeping pairs intact."""
        history = _turn("q1", "a1", filler=4000) + _turn("q2", "a2", filler=4000)
        head, tail = split_for_compaction(history, keep_tokens=1500)
        assert head + tail == history
        assert tail and is_plain_user_turn(tail[0])
        assert tail[0]["content"] == "q2"

    def test_everything_fits_yields_empty_head(self):
        """Under-budget history is untouched (whole history is the tail)."""
        history = _turn("q1", "a1")
        head, tail = split_for_compaction(history, keep_tokens=10_000)
        assert head == []
        assert tail == history

    def test_no_boundary_puts_everything_in_head(self):
        """Without a safe cut point the whole history gets summarized."""
        history = _turn("q1", "a1", filler=8000)[1:]  # starts mid-turn
        head, tail = split_for_compaction(history, keep_tokens=10)
        assert head == history
        assert tail == []


class TestHardTrim:
    """The no-LLM fallback."""

    def test_drops_oldest_groups_until_under_budget(self):
        """Old turn groups go first; the newest question survives."""
        history = _turn("q1", "a1", filler=4000) + _turn("q2", "a2")
        trimmed = hard_trim(history, max_tokens=500)
        assert trimmed[0]["content"] == "q2"
        assert history_tokens(trimmed) <= 500

    def test_single_oversized_group_returned_intact(self):
        """One un-splittable group is kept whole, never corrupted."""
        history = _turn("q1", "a1", filler=8000)
        assert hard_trim(history, max_tokens=10) == history


class TestFold:
    """Summary folding."""

    def test_summary_leads_and_tail_follows(self):
        """Folded history opens with the tagged summary then the tail."""
        tail = [{"role": "user", "content": "q2"}]
        folded = fold_summary("- user asked about GPUs", tail)
        assert folded[0]["role"] == "user"
        assert "<conversation_summary>" in folded[0]["content"]
        assert "- user asked about GPUs" in folded[0]["content"]
        assert folded[1:] == tail
