"""Tests for model configuration."""

from aieng_bot.config import get_model_name


def test_default_model_is_sonnet_5_5(monkeypatch):
    """Test the default model when CLAUDE_MODEL is unset."""
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    assert get_model_name() == "claude-sonnet-5-5"


def test_model_override_from_env(monkeypatch):
    """Test CLAUDE_MODEL overrides the default model."""
    monkeypatch.setenv("CLAUDE_MODEL", "claude-opus-5-5")
    assert get_model_name() == "claude-opus-5-5"
