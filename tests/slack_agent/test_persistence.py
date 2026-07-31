"""Tests for durable session snapshots."""

from slack_agent.context import ContextStore
from slack_agent.persistence import ContextArchive


class TestContextArchive:
    """Snapshot round-trips and fault tolerance."""

    def test_round_trip(self, tmp_path):
        """A saved snapshot loads back identically."""
        archive = ContextArchive(tmp_path)
        payload = {"messages": [{"user": "U1", "text": "hi"}], "agent_history": []}
        archive.save("C1", "100.1", payload)
        assert archive.load("C1", "100.1") == payload

    def test_missing_snapshot_is_none(self, tmp_path):
        """Unknown sessions load as None."""
        assert ContextArchive(tmp_path).load("C1", "1.0") is None

    def test_corrupted_snapshot_is_ignored(self, tmp_path):
        """A truncated or garbage file is treated as absent, not fatal."""
        archive = ContextArchive(tmp_path)
        archive.save("C1", "100.1", {"messages": []})
        next(tmp_path.glob("*.json")).write_text("{not json")
        assert archive.load("C1", "100.1") is None

    def test_keys_are_filesystem_safe(self, tmp_path):
        """Slack timestamps with dots map to safe, distinct filenames."""
        archive = ContextArchive(tmp_path)
        archive.save("C1", "100.1", {"a": 1})
        archive.save("C1", "100.2", {"a": 2})
        assert archive.load("C1", "100.1") == {"a": 1}
        assert archive.load("C1", "100.2") == {"a": 2}


class TestContextStoreRestore:
    """Store integration: sessions survive a process restart."""

    def test_context_restored_after_restart(self, tmp_path):
        """A persisted context comes back with messages and history."""
        archive = ContextArchive(tmp_path)
        store = ContextStore(archive=archive)
        context = store.get("C1", "100.1")
        context.messages.append({"user": "U1", "text": "how do I get access?"})
        context.agent_history = [{"role": "user", "content": "how do I get access?"}]
        store.persist(context)

        fresh_store = ContextStore(archive=ContextArchive(tmp_path))
        restored = fresh_store.get("C1", "100.1")
        assert restored.messages == context.messages
        assert restored.agent_history == context.agent_history

    def test_memory_only_store_still_works(self):
        """Without an archive the store behaves as before."""
        store = ContextStore()
        context = store.get("C1", "1.0")
        store.persist(context)
        assert store.get("C1", "1.0") is context
