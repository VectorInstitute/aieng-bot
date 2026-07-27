"""Tests for content and tool info extraction utilities."""

from types import SimpleNamespace

from aieng_bot.observability.extractors import ContentExtractor, ToolInfoExtractor


class TestContentExtractor:
    """Tests for ContentExtractor."""

    def test_extract_from_tool_use_with_command(self):
        """Bash-style tool input renders as a shell command."""
        block = SimpleNamespace(name="Bash", input={"command": "ls -la"})
        assert ContentExtractor.extract_from_tool_use(block) == "$ ls -la"

    def test_extract_from_tool_use_with_edit(self):
        """Edit tool input renders as an edit description."""
        block = SimpleNamespace(
            name="Edit",
            input={"file_path": "/tmp/f.py", "old_string": "a", "new_string": "b"},
        )
        assert ContentExtractor.extract_from_tool_use(block) == "Edit file: /tmp/f.py"

    def test_extract_from_tool_use_with_read(self):
        """File path without old_string renders as a read."""
        block = SimpleNamespace(name="Read", input={"file_path": "/tmp/f.py"})
        assert ContentExtractor.extract_from_tool_use(block) == "Read: /tmp/f.py"

    def test_extract_from_tool_use_generic_input(self):
        """Unrecognized input patterns fall back to JSON."""
        block = SimpleNamespace(name="Glob", input={"pattern": "*.py"})
        result = ContentExtractor.extract_from_tool_use(block)
        assert result.startswith("Glob:")
        assert '"pattern"' in result

    def test_extract_from_tool_use_missing_attrs(self):
        """Blocks without name/input fall back to str()."""
        block = SimpleNamespace(name=None, input={})
        assert ContentExtractor.extract_from_tool_use(block) == str(block)

    def test_extract_from_tool_result_string_content(self):
        """String content is returned as-is."""
        block = SimpleNamespace(content="output text")
        assert ContentExtractor.extract_from_tool_result(block) == "output text"

    def test_extract_from_tool_result_non_string_content(self):
        """Non-string content is stringified."""
        block = SimpleNamespace(content=["a", "b"])
        assert ContentExtractor.extract_from_tool_result(block) == "['a', 'b']"

    def test_extract_from_tool_result_no_content_attr(self):
        """Blocks without content fall back to str()."""
        block = object()
        assert ContentExtractor.extract_from_tool_result(block) == str(block)

    def test_extract_from_text_block_with_text_attr(self):
        """Text attribute is returned directly."""
        block = SimpleNamespace(text="hello world")
        assert ContentExtractor.extract_from_text_block(block) == "hello world"

    def test_extract_from_text_block_string_fallback(self):
        """Text is parsed from the string representation when needed."""

        class FakeBlock:
            def __str__(self):
                return "TextBlock(text='some\\ncontent')"

        assert ContentExtractor.extract_from_text_block(FakeBlock()) == "some\ncontent"

    def test_extract_from_text_block_no_match(self):
        """Unparsable blocks fall back to str()."""

        class FakeBlock:
            def __str__(self):
                return "TextBlock(no text here)"

        block = FakeBlock()
        assert ContentExtractor.extract_from_text_block(block) == str(block)

    def test_extract_display_content_dispatches_by_class(self):
        """Dispatch selects the extractor matching the block class name."""
        tool_use = SimpleNamespace(name="Bash", input={"command": "pwd"})
        assert ContentExtractor.extract_display_content(tool_use, "ToolUseBlock") == (
            "$ pwd"
        )

        tool_result = SimpleNamespace(content="done")
        assert (
            ContentExtractor.extract_display_content(tool_result, "ToolResultBlock")
            == "done"
        )

        text = SimpleNamespace(text="hi")
        assert ContentExtractor.extract_display_content(text, "TextBlock") == "hi"

    def test_extract_display_content_unknown_class(self):
        """Unknown block classes fall back to str()."""
        block = SimpleNamespace(foo="bar")
        assert ContentExtractor.extract_display_content(block, "OtherBlock") == str(
            block
        )

    def test_extract_message_content_no_attr(self):
        """Messages without content return an empty string."""
        assert ContentExtractor.extract_message_content(object()) == ""

    def test_extract_message_content_string(self):
        """String content is returned as-is."""
        message = SimpleNamespace(content="plain string")
        assert ContentExtractor.extract_message_content(message) == "plain string"

    def test_extract_message_content_list_of_dicts(self):
        """List content joins dict text fields."""
        message = SimpleNamespace(content=[{"text": "part1"}, {"text": "part2"}])
        assert ContentExtractor.extract_message_content(message) == "part1 part2"

    def test_extract_message_content_list_mixed(self):
        """Non-dict list entries are stringified."""
        message = SimpleNamespace(content=[{"text": "part1"}, 42])
        assert ContentExtractor.extract_message_content(message) == "part1 42"

    def test_extract_message_content_other_type(self):
        """Non-str non-list content is stringified."""
        message = SimpleNamespace(content=123)
        assert ContentExtractor.extract_message_content(message) == "123"


class TestToolInfoExtractorContent:
    """Tests for ToolInfoExtractor.extract_from_content."""

    def setup_method(self):
        """Create an extractor with simple patterns."""
        self.extractor = ToolInfoExtractor(
            {"Bash": r"\$\s+(.+)", "Read": r"Read:\s+(.+)"}
        )

    def test_non_tool_call_event_returns_none(self):
        """Only TOOL_CALL events are extracted."""
        assert self.extractor.extract_from_content("$ ls", "REASONING") is None

    def test_tool_name_must_appear_in_content(self):
        """A pattern match without the tool name in the content is skipped."""
        assert self.extractor.extract_from_content("$ ls -la", "TOOL_CALL") is None

    def test_extracts_read_tool(self):
        """Tool name in content plus pattern match yields parameters."""
        result = self.extractor.extract_from_content("Read: /tmp/file.py", "TOOL_CALL")
        assert result == {
            "tool": "Read",
            "parameters": {"target": "/tmp/file.py"},
            "result_summary": None,
        }

    def test_no_match_returns_none(self):
        """Content matching no pattern returns None."""
        assert self.extractor.extract_from_content("nothing here", "TOOL_CALL") is None


class TestToolInfoExtractorBlock:
    """Tests for ToolInfoExtractor block-based extraction."""

    def setup_method(self):
        """Create an extractor."""
        self.extractor = ToolInfoExtractor({})

    def test_extract_from_tool_use_block_with_attrs(self):
        """Attributes are used directly when present."""
        block = SimpleNamespace(name="Bash", input={"command": "ls"}, id="tu_1")
        result = self.extractor.extract_from_tool_use_block(block)
        assert result == {
            "tool": "Bash",
            "parameters": {"command": "ls"},
            "tool_use_id": "tu_1",
        }

    def test_extract_from_tool_use_block_string_fallback(self):
        """Missing attributes fall back to string parsing."""

        class FakeBlock:
            name = None
            input: dict = {}
            id = None

            def __str__(self):
                return "ToolUseBlock(id='tu_9', name='Bash', input={'command': 'pwd'})"

        result = self.extractor.extract_from_tool_use_block(FakeBlock())
        assert result["tool"] == "Bash"
        assert result["parameters"] == {"command": "pwd"}
        assert result["tool_use_id"] == "tu_9"

    def test_extract_from_tool_use_block_unparsable(self):
        """Completely unparsable blocks yield Unknown/empty values."""

        class FakeBlock:
            name = None
            input: dict = {}
            id = None

            def __str__(self):
                return "opaque object"

        result = self.extractor.extract_from_tool_use_block(FakeBlock())
        assert result == {"tool": "Unknown", "parameters": {}, "tool_use_id": None}

    def test_extract_tool_name_without_quotes(self):
        """name=Bash without quotes is parsed."""

        class FakeBlock:
            def __str__(self):
                return "ToolUseBlock(name=Bash)"

        assert ToolInfoExtractor._extract_tool_name_from_string(FakeBlock()) == "Bash"

    def test_extract_tool_input_no_input_marker(self):
        """Strings without input= yield an empty dict."""

        class FakeBlock:
            def __str__(self):
                return "ToolUseBlock(name='Bash')"

        assert ToolInfoExtractor._extract_tool_input_from_string(FakeBlock()) == {}

    def test_extract_tool_input_malformed_falls_back_to_key_fields(self):
        """Malformed dicts still yield key fields via regex fallback."""

        class FakeBlock:
            def __str__(self):
                return (
                    "ToolUseBlock(input={'file_path': '/tmp/x.py', "
                    "'content': unparsable{)"
                )

        result = ToolInfoExtractor._extract_tool_input_from_string(FakeBlock())
        assert result == {}  # unbalanced braces -> no balanced content

    def test_extract_tool_input_key_fields_fallback(self):
        """Non-JSON but balanced input falls back to key-field extraction."""

        class FakeBlock:
            def __str__(self):
                return (
                    "ToolUseBlock(input={'file_path': '/tmp/x.py', "
                    "'other': object_repr})"
                )

        result = ToolInfoExtractor._extract_tool_input_from_string(FakeBlock())
        assert result == {"file_path": "/tmp/x.py"}

    def test_extract_tool_input_raw_fallback(self):
        """Balanced but fully unparsable input is stored raw."""

        class FakeBlock:
            def __str__(self):
                return "ToolUseBlock(input={unparsable: object})"

        result = ToolInfoExtractor._extract_tool_input_from_string(FakeBlock())
        assert result == {"raw": "{unparsable: object}"}

    def test_extract_balanced_braces_simple(self):
        """Balanced braces are extracted including nesting."""
        text = "input={'a': {'b': 1}} trailing"
        result = ToolInfoExtractor._extract_balanced_braces(text, 6)
        assert result == "{'a': {'b': 1}}"

    def test_extract_balanced_braces_invalid_start(self):
        """Positions not at an opening brace return None."""
        assert ToolInfoExtractor._extract_balanced_braces("abc", 0) is None
        assert ToolInfoExtractor._extract_balanced_braces("abc", 10) is None

    def test_extract_balanced_braces_ignores_braces_in_strings(self):
        """Braces inside quoted strings do not affect depth."""
        text = "{'cmd': 'echo }'}"
        result = ToolInfoExtractor._extract_balanced_braces(text, 0)
        assert result == "{'cmd': 'echo }'}"

    def test_extract_balanced_braces_handles_escapes(self):
        """Escaped quotes inside strings are skipped."""
        text = "{'cmd': 'say \\'hi\\''}"
        result = ToolInfoExtractor._extract_balanced_braces(text, 0)
        assert result == text

    def test_extract_balanced_braces_unbalanced(self):
        """Unbalanced input returns None."""
        assert ToolInfoExtractor._extract_balanced_braces("{'a': 1", 0) is None

    def test_extract_key_fields_command(self):
        """Command fields are extracted for Bash tools."""
        content = "{'command': 'ls -la', 'timeout': broken}"
        assert ToolInfoExtractor._extract_key_fields(content) == {"command": "ls -la"}

    def test_extract_key_fields_none(self):
        """No recognizable fields returns None."""
        assert ToolInfoExtractor._extract_key_fields("{'x': 1}") is None

    def test_extract_tool_id_from_string(self):
        """id='...' is parsed from string representation."""

        class FakeBlock:
            def __str__(self):
                return "ToolUseBlock(id='toolu_123')"

        assert (
            ToolInfoExtractor._extract_tool_id_from_string(FakeBlock()) == "toolu_123"
        )

    def test_extract_tool_use_id_attr(self):
        """tool_use_id attribute is read from result blocks."""
        block = SimpleNamespace(tool_use_id="tu_5")
        assert ToolInfoExtractor.extract_tool_use_id(block) == "tu_5"
        assert ToolInfoExtractor.extract_tool_use_id(object()) is None

    def test_is_error_result_attr_true(self):
        """is_error=True attribute marks an error."""
        assert ToolInfoExtractor.is_error_result(SimpleNamespace(is_error=True))

    def test_is_error_result_attr_false(self):
        """is_error=False attribute is not an error."""
        assert not ToolInfoExtractor.is_error_result(SimpleNamespace(is_error=False))

    def test_is_error_result_string_fallback(self):
        """Missing attribute falls back to string matching."""

        class FakeBlock:
            def __str__(self):
                return "ToolResultBlock(is_error=True)"

        assert ToolInfoExtractor.is_error_result(FakeBlock())

    def test_is_error_result_negative(self):
        """Blocks with no error markers are not errors."""
        assert not ToolInfoExtractor.is_error_result(object())
