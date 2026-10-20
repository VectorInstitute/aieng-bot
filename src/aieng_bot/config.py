"""Configuration for aieng-bot."""

import os


def get_model_name() -> str:
    """Get the Claude model name used by the agent.

    Returns the model configured via CLAUDE_MODEL environment variable,
    or defaults to the latest Claude Sonnet 5.5 model.

    Returns
    -------
    str
        The full model identifier (e.g., "claude-sonnet-5-5").

    """
    return os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
