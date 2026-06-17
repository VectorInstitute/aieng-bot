"""Unit tests for BookstackActivityLogger."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from aieng_bot.bookstack.activity_logger import (
    BookstackActivityLogger,
    _PreconditionFailed,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def logger() -> BookstackActivityLogger:
    """Return a BookstackActivityLogger configured with a test bucket."""
    return BookstackActivityLogger(
        bucket="test-bucket",
        log_path="data/test_bookstack_activity_log.json",
    )


@pytest.fixture
def mock_gcs_client() -> MagicMock:
    """Return a mock google.cloud.storage.Client."""
    return MagicMock()


@pytest.fixture
def sample_log() -> dict[str, Any]:
    """Return an existing activity log with one entry."""
    return {
        "activities": [
            {
                "session_id": "existing01",
                "timestamp": "2026-03-01T10:00:00Z",
                "question": "How do I access the VPN?",
                "tools_used": ["search_bookstack"],
                "tool_call_counts": {"search_bookstack": 1},
                "num_tool_calls": 1,
                "answer_length": 400,
                "duration_seconds": 3.5,
                "status": "success",
                "trace_path": "data/bookstack/traces/2026-03-01/existing01-100000.json",
            }
        ],
        "last_updated": "2026-03-01T10:00:00Z",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _attach_mock_client(
    logger: BookstackActivityLogger, mock_client: MagicMock
) -> None:
    """Inject a mock GCS client into the logger."""
    logger._client = mock_client


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestInit:
    """BookstackActivityLogger initialisation."""

    def test_defaults(self) -> None:
        """Verify default bucket and log path values."""
        lg = BookstackActivityLogger()
        assert lg.bucket == "bot-dashboard-vectorinstitute"
        assert lg.log_path == "data/bookstack_activity_log.json"

    def test_custom_values(self) -> None:
        """Verify custom bucket and log path are stored correctly."""
        lg = BookstackActivityLogger(bucket="my-bucket", log_path="custom/path.json")
        assert lg.bucket == "my-bucket"
        assert lg.log_path == "custom/path.json"

    def test_client_starts_as_none(self, logger: BookstackActivityLogger) -> None:
        """Verify GCS client is lazily initialised."""
        assert logger._client is None


# ---------------------------------------------------------------------------
# _load_activity_log
# ---------------------------------------------------------------------------


class TestLoadActivityLog:
    """_load_activity_log GCS read behaviour."""

    def test_load_existing_log(
        self,
        logger: BookstackActivityLogger,
        mock_gcs_client: MagicMock,
        sample_log: dict[str, Any],
    ) -> None:
        """Return (log_data, generation) when blob exists."""
        blob = MagicMock()
        blob.exists.return_value = True
        blob.download_as_text.return_value = json.dumps(sample_log)
        blob.generation = 42
        mock_gcs_client.bucket.return_value.blob.return_value = blob
        _attach_mock_client(logger, mock_gcs_client)

        result = logger._load_activity_log()

        assert result is not None
        log_data, generation = result
        assert log_data == sample_log
        assert len(log_data["activities"]) == 1
        assert generation == 42

    def test_load_returns_empty_when_blob_not_found(
        self,
        logger: BookstackActivityLogger,
        mock_gcs_client: MagicMock,
    ) -> None:
        """Return (empty structure, generation=0) when the log file does not yet exist."""
        blob = MagicMock()
        blob.exists.return_value = False
        mock_gcs_client.bucket.return_value.blob.return_value = blob
        _attach_mock_client(logger, mock_gcs_client)

        result = logger._load_activity_log()

        assert result is not None
        log_data, generation = result
        assert log_data == {"activities": [], "last_updated": None}
        assert generation == 0

    def test_load_returns_none_on_gcs_error(
        self,
        logger: BookstackActivityLogger,
        mock_gcs_client: MagicMock,
    ) -> None:
        """Return None when GCS raises (caller must abort write)."""
        mock_gcs_client.bucket.side_effect = Exception("permission denied")
        _attach_mock_client(logger, mock_gcs_client)

        result = logger._load_activity_log()

        assert result is None

    def test_load_returns_none_on_invalid_json(
        self,
        logger: BookstackActivityLogger,
        mock_gcs_client: MagicMock,
    ) -> None:
        """Return None when the blob contains malformed JSON."""
        blob = MagicMock()
        blob.exists.return_value = True
        blob.download_as_text.return_value = "not valid json {"
        mock_gcs_client.bucket.return_value.blob.return_value = blob
        _attach_mock_client(logger, mock_gcs_client)

        result = logger._load_activity_log()

        assert result is None


# ---------------------------------------------------------------------------
# _save_activity_log
# ---------------------------------------------------------------------------


class TestSaveActivityLog:
    """_save_activity_log GCS write behaviour."""

    def test_save_success(
        self,
        logger: BookstackActivityLogger,
        mock_gcs_client: MagicMock,
        sample_log: dict[str, Any],
    ) -> None:
        """Return True, upload JSON with correct content-type and generation precondition."""
        blob = MagicMock()
        mock_gcs_client.bucket.return_value.blob.return_value = blob
        _attach_mock_client(logger, mock_gcs_client)

        result = logger._save_activity_log(sample_log, if_generation_match=99)

        assert result is True
        blob.upload_from_string.assert_called_once()
        call_kwargs = blob.upload_from_string.call_args
        assert call_kwargs.kwargs["content_type"] == "application/json"
        assert call_kwargs.kwargs["if_generation_match"] == 99
        saved = json.loads(call_kwargs.args[0])
        assert saved == sample_log

    def test_save_returns_false_on_gcs_error(
        self,
        logger: BookstackActivityLogger,
        mock_gcs_client: MagicMock,
        sample_log: dict[str, Any],
    ) -> None:
        """Return False when the GCS upload raises a non-CAS error."""
        blob = MagicMock()
        blob.upload_from_string.side_effect = Exception("upload failed")
        mock_gcs_client.bucket.return_value.blob.return_value = blob
        _attach_mock_client(logger, mock_gcs_client)

        result = logger._save_activity_log(sample_log, if_generation_match=0)

        assert result is False

    def test_save_raises_on_precondition_failed(
        self,
        logger: BookstackActivityLogger,
        mock_gcs_client: MagicMock,
        sample_log: dict[str, Any],
    ) -> None:
        """Re-raise PreconditionFailed so the caller can retry."""
        blob = MagicMock()
        blob.upload_from_string.side_effect = _PreconditionFailed("conflict")
        mock_gcs_client.bucket.return_value.blob.return_value = blob
        _attach_mock_client(logger, mock_gcs_client)

        with pytest.raises(_PreconditionFailed):
            logger._save_activity_log(sample_log, if_generation_match=5)


# ---------------------------------------------------------------------------
# _save_trace
# ---------------------------------------------------------------------------


class TestSaveTrace:
    """_save_trace uploads individual trace files."""

    def test_save_trace_success(
        self,
        logger: BookstackActivityLogger,
        mock_gcs_client: MagicMock,
    ) -> None:
        """Return True when trace upload succeeds."""
        blob = MagicMock()
        mock_gcs_client.bucket.return_value.blob.return_value = blob
        _attach_mock_client(logger, mock_gcs_client)

        trace = {"session_id": "abc", "question": "Q", "tool_calls": [], "answer": "A"}
        result = logger._save_trace(
            trace, "data/bookstack/traces/2026-03-14/abc-120000.json"
        )

        assert result is True
        blob.upload_from_string.assert_called_once()

    def test_save_trace_returns_false_on_error(
        self,
        logger: BookstackActivityLogger,
        mock_gcs_client: MagicMock,
    ) -> None:
        """Return False when the GCS upload raises."""
        blob = MagicMock()
        blob.upload_from_string.side_effect = Exception("network error")
        mock_gcs_client.bucket.return_value.blob.return_value = blob
        _attach_mock_client(logger, mock_gcs_client)

        result = logger._save_trace(
            {}, "data/bookstack/traces/2026-03-14/abc-120000.json"
        )

        assert result is False


# ---------------------------------------------------------------------------
# log_query
# ---------------------------------------------------------------------------


class TestLogQuery:
    """log_query end-to-end behaviour."""

    def test_log_query_success(
        self,
        logger: BookstackActivityLogger,
        mock_gcs_client: MagicMock,
    ) -> None:
        """Return True and perform two GCS uploads (trace + activity log)."""
        blob = MagicMock()
        blob.exists.return_value = False  # new log
        mock_gcs_client.bucket.return_value.blob.return_value = blob
        _attach_mock_client(logger, mock_gcs_client)

        result = logger.log_query(
            session_id="sess1234",
            question="What is the offboarding process?",
            tool_calls=[
                {"tool": "search_bookstack", "input": {"query": "offboarding"}},
                {"tool": "get_page", "input": {"page_id": 10}},
            ],
            answer="The offboarding process involves...",
            duration_seconds=5.2,
            status="success",
        )

        assert result is True
        # upload_from_string called twice: once for trace, once for activity log
        assert blob.upload_from_string.call_count == 2

    def test_log_query_records_correct_activity_fields(
        self,
        logger: BookstackActivityLogger,
        mock_gcs_client: MagicMock,
    ) -> None:
        """Verify all activity fields are populated with correct values."""
        blob = MagicMock()
        blob.exists.return_value = False
        mock_gcs_client.bucket.return_value.blob.return_value = blob
        _attach_mock_client(logger, mock_gcs_client)

        with patch.object(
            logger, "_save_activity_log", wraps=logger._save_activity_log
        ) as spy:
            logger.log_query(
                session_id="sess5678",
                question="How do I request compute?",
                tool_calls=[
                    {"tool": "search_bookstack", "input": {"query": "compute"}},
                    {"tool": "search_bookstack", "input": {"query": "GPU request"}},
                    {"tool": "get_page", "input": {"page_id": 7}},
                ],
                answer="Submit a compute request via...",
                duration_seconds=9.1,
                status="success",
            )

            saved = spy.call_args[0][0]
            activity = saved["activities"][0]

        assert activity["session_id"] == "sess5678"
        assert activity["question"] == "How do I request compute?"
        assert activity["num_tool_calls"] == 3
        assert activity["tool_call_counts"] == {"search_bookstack": 2, "get_page": 1}
        assert set(activity["tools_used"]) == {"search_bookstack", "get_page"}
        assert activity["status"] == "success"
        assert activity["duration_seconds"] == 9.1
        assert activity["answer_length"] == len("Submit a compute request via...")

    def test_log_query_truncates_question_in_activity(
        self,
        logger: BookstackActivityLogger,
        mock_gcs_client: MagicMock,
    ) -> None:
        """Truncate questions longer than 300 chars in the activity log."""
        blob = MagicMock()
        blob.exists.return_value = False
        mock_gcs_client.bucket.return_value.blob.return_value = blob
        _attach_mock_client(logger, mock_gcs_client)

        long_question = "A" * 500

        with patch.object(
            logger, "_save_activity_log", wraps=logger._save_activity_log
        ) as spy:
            logger.log_query(
                session_id="sess9999",
                question=long_question,
                tool_calls=[],
                answer="Answer",
                duration_seconds=1.0,
                status="success",
            )
            saved = spy.call_args[0][0]

        assert len(saved["activities"][0]["question"]) == 300

    def test_log_query_appends_to_existing_log(
        self,
        logger: BookstackActivityLogger,
        mock_gcs_client: MagicMock,
        sample_log: dict[str, Any],
    ) -> None:
        """Append new entry to an existing log without overwriting old entries."""
        blob = MagicMock()
        blob.exists.return_value = True
        blob.download_as_text.return_value = json.dumps(sample_log)
        blob.generation = 77
        mock_gcs_client.bucket.return_value.blob.return_value = blob
        _attach_mock_client(logger, mock_gcs_client)

        with patch.object(
            logger, "_save_activity_log", wraps=logger._save_activity_log
        ) as spy:
            logger.log_query(
                session_id="newentry",
                question="New question",
                tool_calls=[{"tool": "list_books", "input": {}}],
                answer="New answer",
                duration_seconds=2.0,
                status="success",
            )
            saved = spy.call_args[0][0]

        assert len(saved["activities"]) == 2
        assert saved["activities"][0]["session_id"] == "existing01"
        assert saved["activities"][1]["session_id"] == "newentry"
        assert spy.call_args.kwargs["if_generation_match"] == 77

    def test_log_query_returns_false_when_load_fails(
        self,
        logger: BookstackActivityLogger,
    ) -> None:
        """Return False and abort write when the GCS load returns None."""
        with patch.object(logger, "_load_activity_log", return_value=None):
            result = logger.log_query(
                session_id="sess0000",
                question="Q",
                tool_calls=[],
                answer="A",
                duration_seconds=1.0,
                status="success",
            )

        assert result is False

    def test_log_query_error_status(
        self,
        logger: BookstackActivityLogger,
        mock_gcs_client: MagicMock,
    ) -> None:
        """Record error status correctly in the activity log."""
        blob = MagicMock()
        blob.exists.return_value = False
        mock_gcs_client.bucket.return_value.blob.return_value = blob
        _attach_mock_client(logger, mock_gcs_client)

        with patch.object(
            logger, "_save_activity_log", wraps=logger._save_activity_log
        ) as spy:
            logger.log_query(
                session_id="errorsess",
                question="A failing query",
                tool_calls=[],
                answer="",
                duration_seconds=0.5,
                status="error",
            )
            saved = spy.call_args[0][0]

        assert saved["activities"][0]["status"] == "error"

    def test_log_query_deduplicates_tools_used(
        self,
        logger: BookstackActivityLogger,
        mock_gcs_client: MagicMock,
    ) -> None:
        """List each tool once in tools_used while counting all calls in tool_call_counts."""
        blob = MagicMock()
        blob.exists.return_value = False
        mock_gcs_client.bucket.return_value.blob.return_value = blob
        _attach_mock_client(logger, mock_gcs_client)

        with patch.object(
            logger, "_save_activity_log", wraps=logger._save_activity_log
        ) as spy:
            logger.log_query(
                session_id="dedupsess",
                question="Q",
                tool_calls=[
                    {"tool": "search_bookstack", "input": {"query": "a"}},
                    {"tool": "search_bookstack", "input": {"query": "b"}},
                    {"tool": "search_bookstack", "input": {"query": "c"}},
                ],
                answer="A",
                duration_seconds=3.0,
                status="success",
            )
            saved = spy.call_args[0][0]

        # tools_used should list each tool only once
        assert saved["activities"][0]["tools_used"] == ["search_bookstack"]
        assert saved["activities"][0]["num_tool_calls"] == 3

    def test_log_query_retries_on_cas_conflict(
        self,
        logger: BookstackActivityLogger,
    ) -> None:
        """Retry the append+save loop on a 412 PreconditionFailed and succeed on the second attempt."""
        save_attempts: list[int] = []

        def mock_save(_log_data: dict[str, Any], *, if_generation_match: int) -> bool:
            save_attempts.append(if_generation_match)
            if len(save_attempts) == 1:
                raise _PreconditionFailed("concurrent write")
            return True

        empty_snapshot = ({"activities": [], "last_updated": None}, 0)

        with (
            patch.object(logger, "_save_trace", return_value=True),
            patch.object(logger, "_load_activity_log", return_value=empty_snapshot),
            patch.object(logger, "_save_activity_log", side_effect=mock_save),
        ):
            result = logger.log_query(
                session_id="sess_cas",
                question="Will this retry?",
                tool_calls=[],
                answer="Yes",
                duration_seconds=1.0,
                status="success",
            )

        assert result is True
        assert len(save_attempts) == 2  # failed once, succeeded on retry

    def test_log_query_gives_up_after_max_cas_retries(
        self,
        logger: BookstackActivityLogger,
    ) -> None:
        """Return False when all CAS retry attempts are exhausted."""
        empty_snapshot = ({"activities": [], "last_updated": None}, 0)

        with (
            patch.object(logger, "_save_trace", return_value=True),
            patch.object(logger, "_load_activity_log", return_value=empty_snapshot),
            patch.object(
                logger,
                "_save_activity_log",
                side_effect=_PreconditionFailed("persistent conflict"),
            ),
        ):
            result = logger.log_query(
                session_id="sess_exhaust",
                question="Will this exhaust retries?",
                tool_calls=[],
                answer="No",
                duration_seconds=1.0,
                status="success",
            )

        assert result is False
