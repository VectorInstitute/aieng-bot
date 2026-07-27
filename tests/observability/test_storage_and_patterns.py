"""Tests for trace storage edge cases and tracer tool patterns."""

import json
import os
import re

from aieng_bot.observability.storage import TraceStorage
from aieng_bot.observability.tracer import AgentExecutionTracer


class TestSaveToFile:
    """Tests for TraceStorage.save_to_file."""

    def test_save_creates_parent_dirs(self, tmp_path):
        """Nested directories are created as needed."""
        filepath = str(tmp_path / "a" / "b" / "trace.json")
        TraceStorage.save_to_file({"k": "v"}, filepath)
        with open(filepath) as f:
            assert json.load(f) == {"k": "v"}

    def test_save_bare_filename(self, tmp_path, monkeypatch):
        """A filename with no directory component must not crash."""
        monkeypatch.chdir(tmp_path)
        TraceStorage.save_to_file({"k": "v"}, "trace.json")
        assert os.path.exists(tmp_path / "trace.json")


class TestToolPatterns:
    """Regression tests for the tracer's text-based tool patterns."""

    def test_read_pattern_captures_full_path(self):
        """The Read pattern must capture the whole file path, not one char."""
        match = re.search(
            AgentExecutionTracer.TOOL_PATTERNS["Read"],
            "Reading file src/aieng_bot/config.py",
        )
        assert match is not None
        assert match.group(1) == "src/aieng_bot/config.py"

    def test_bash_pattern_captures_full_command(self):
        """The Bash pattern must capture the whole command."""
        match = re.search(
            AgentExecutionTracer.TOOL_PATTERNS["Bash"],
            "Running `pytest -x tests/`",
        )
        assert match is not None
        assert match.group(1) == "pytest -x tests/"

    def test_skill_pattern(self):
        """The Skill pattern extracts the skill name."""
        match = re.search(
            AgentExecutionTracer.TOOL_PATTERNS["Skill"],
            "Launching skill: fix-lint-failures",
        )
        assert match is not None
        assert match.group(1) == "fix-lint-failures"


class TestTracerMetadata:
    """Tests for configurable tracer metadata."""

    def _make_tracer(self, **kwargs):
        return AgentExecutionTracer(
            pr_info={"repo": "o/r", "number": 1, "title": "t", "author": "a", "url": "u"},
            failure_info={"type": "lint", "checks": ["c"]},
            workflow_run_id="1",
            github_run_url="u",
            **kwargs,
        )

    def test_default_model_from_config(self, monkeypatch):
        """The trace records the configured model by default."""
        monkeypatch.setenv("CLAUDE_MODEL", "claude-test-model")
        tracer = self._make_tracer()
        assert tracer.trace["execution"]["model"] == "claude-test-model"

    def test_explicit_model_and_tools(self):
        """Explicit model and tool list are recorded in the trace."""
        tracer = self._make_tracer(model="my-model", allowed_tools=["Read", "Bash"])
        assert tracer.trace["execution"]["model"] == "my-model"
        assert tracer.trace["execution"]["tools_allowed"] == ["Read", "Bash"]
