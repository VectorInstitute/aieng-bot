"""Result message parsing for agent execution traces.

This module provides utilities for parsing ResultMessage objects from
Claude Agent SDK, extracting execution metrics, token usage, and result text.
"""

from __future__ import annotations

import ast
import re
from typing import Any, Callable


class ResultMessageParser:
    """Parse ResultMessage objects and extract execution metrics."""

    @staticmethod
    def parse(message: Any) -> tuple[str, dict[str, Any] | None]:
        """Parse ResultMessage and extract execution metrics.

        Parameters
        ----------
        message : Any
            ResultMessage from Agent SDK.

        Returns
        -------
        tuple[str, dict[str, Any] | None]
            Tuple of (formatted_content, metrics_dict).
            formatted_content is human-readable summary.
            metrics_dict contains extracted performance metrics.

        """
        msg_str = str(message)

        # Extract structured fields
        metrics = ResultMessageParser._extract_scalar_fields(msg_str)
        metrics["usage"] = ResultMessageParser._extract_usage(msg_str)
        result_text = ResultMessageParser._extract_result_text(msg_str)

        # Create formatted content for display
        formatted_content = ResultMessageParser._format_metrics(metrics, result_text)

        return formatted_content, metrics if metrics else None

    @staticmethod
    def _extract_scalar_fields(msg_str: str) -> dict[str, Any]:
        """Extract scalar fields from ResultMessage string.

        Parameters
        ----------
        msg_str : str
            String representation of ResultMessage.

        Returns
        -------
        dict[str, Any]
            Dictionary of extracted scalar fields.

        """
        metrics: dict[str, Any] = {}
        field_configs: list[tuple[str, type, Callable[[str], Any]]] = [
            ("subtype", str, lambda x: x),
            ("duration_ms", int, lambda x: int(x) if x.isdigit() else None),
            (
                "duration_api_ms",
                int,
                lambda x: int(x) if x.isdigit() else None,
            ),
            ("is_error", bool, lambda x: x == "True"),
            ("num_turns", int, lambda x: int(x) if x.isdigit() else None),
            ("session_id", str, lambda x: x),
            ("total_cost_usd", float, lambda x: _safe_float(x)),
        ]

        for field, _, converter in field_configs:
            pattern = rf"{field}=([^,\)]+)"
            match = re.search(pattern, msg_str)
            if match:
                value_str = match.group(1).strip("'\"")
                try:
                    metrics[field] = converter(value_str)
                except (ValueError, AttributeError):
                    metrics[field] = None

        return metrics

    @staticmethod
    def _extract_usage(msg_str: str) -> dict[str, Any]:
        """Extract usage dict (tokens) from ResultMessage string.

        Parameters
        ----------
        msg_str : str
            String representation of ResultMessage.

        Returns
        -------
        dict[str, Any]
            Dictionary containing token usage metrics.

        """
        usage_start = msg_str.find("usage={")
        if usage_start == -1:
            return {}

        # Extract content with balanced braces
        usage_str = ResultMessageParser._extract_balanced_braces(
            msg_str, usage_start + 6
        )
        if not usage_str:
            return {}

        try:
            # Use ast.literal_eval for safe Python dict evaluation
            return ast.literal_eval(usage_str)
        except (ValueError, SyntaxError):
            # Fallback: extract key metrics manually
            return ResultMessageParser._extract_token_fields(usage_str)

    @staticmethod
    def _extract_balanced_braces(text: str, start_pos: int) -> str | None:
        """Extract text within balanced braces.

        Parameters
        ----------
        text : str
            Text to extract from.
        start_pos : int
            Starting position (should point to opening brace).

        Returns
        -------
        str or None
            Extracted text including braces, or None if not balanced.

        """
        brace_count = 0
        for i in range(start_pos, len(text)):
            if text[i] == "{":
                brace_count += 1
            elif text[i] == "}":
                brace_count -= 1
                if brace_count == 0:
                    return text[start_pos : i + 1]
        return None

    @staticmethod
    def _extract_token_fields(usage_str: str) -> dict[str, int]:
        """Extract token fields manually from usage string.

        Parameters
        ----------
        usage_str : str
            Usage dictionary string.

        Returns
        -------
        dict[str, int]
            Dictionary of token counts.

        """
        usage = {}
        token_fields = [
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        ]

        for field in token_fields:
            token_match = re.search(rf"'{field}':\s*(\d+)", usage_str)
            if token_match:
                usage[field] = int(token_match.group(1))

        return usage

    @staticmethod
    def _extract_result_text(msg_str: str) -> str:
        """Extract result text from ResultMessage string.

        Parameters
        ----------
        msg_str : str
            String representation of ResultMessage.

        Returns
        -------
        str
            Extracted and unescaped result text.

        """
        # Try single-quoted result first
        result_match = re.search(r"result='([^']*(?:''[^']*)*)'", msg_str, re.DOTALL)
        if not result_match:
            # Try double-quoted result
            result_match = re.search(
                r'result="([^"]*(?:""[^"]*)*)"', msg_str, re.DOTALL
            )

        if not result_match:
            return ""

        result_text = result_match.group(1)
        # Unescape escaped quotes and newlines
        result_text = result_text.replace("\\'", "'").replace('\\"', '"')
        return result_text.replace("\\n", "\n")

    @staticmethod
    def _format_metrics(metrics: dict[str, Any], result_text: str) -> str:
        """Format result metrics into human-readable content.

        Parameters
        ----------
        metrics : dict[str, Any]
            Extracted metrics dictionary.
        result_text : str
            Result text to append.

        Returns
        -------
        str
            Formatted content string.

        """
        status_emoji = "✓" if metrics.get("subtype") == "success" else "✗"
        formatted_parts = [
            f"{status_emoji} Agent Execution Complete",
            f"Duration: {metrics.get('duration_ms', 0) / 1000:.1f}s",
            f"API Time: {metrics.get('duration_api_ms', 0) / 1000:.1f}s",
            f"Turns: {metrics.get('num_turns', 0)}",
            f"Cost: ${metrics.get('total_cost_usd', 0):.4f}",
        ]

        # Add token usage summary if available
        usage = metrics.get("usage", {})
        if usage:
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cache_read = usage.get("cache_read_input_tokens", 0)
            formatted_parts.append(
                f"Tokens: {input_tokens:,} in / {output_tokens:,} out / {cache_read:,} cached"
            )

        formatted_content = "\n".join(formatted_parts)

        # Add result summary if available and not too long
        if result_text:
            truncated_text = (
                f"{result_text[:500]}..." if len(result_text) > 500 else result_text
            )
            formatted_content += f"\n\nResult: {truncated_text}"

        return formatted_content


def _safe_float(value_str: str) -> float | None:
    """Safely convert string to float.

    Parameters
    ----------
    value_str : str
        String to convert.

    Returns
    -------
    float or None
        Converted float or None if conversion fails.

    """
    try:
        return float(value_str)
    except ValueError:
        return None
