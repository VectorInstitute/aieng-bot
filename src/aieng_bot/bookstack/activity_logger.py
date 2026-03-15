"""Activity logger for BookStack QA analytics — writes query records to GCS."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

try:
    from google.cloud import storage as _gcs_storage

    _GCS_AVAILABLE = True
except ImportError:
    _gcs_storage = None
    _GCS_AVAILABLE = False

logger = logging.getLogger(__name__)

BUCKET = "bot-dashboard-vectorinstitute"
ACTIVITY_LOG_PATH = "data/bookstack_activity_log.json"
TRACES_PREFIX = "data/bookstack/traces"


class BookstackActivityLogger:
    """Log BookStack QA query analytics to Google Cloud Storage.

    Each query is recorded in a unified activity log (for list/chart views)
    and as an individual trace file (for detailed per-query inspection).

    Uses the ``google-cloud-storage`` Python library with Application Default
    Credentials (ADC).  In GKE this is satisfied automatically via Workload
    Identity; locally, run ``gcloud auth application-default login``.

    Parameters
    ----------
    bucket : str
        GCS bucket name (default ``bot-dashboard-vectorinstitute``).
    log_path : str
        Path to the activity log JSON inside the bucket.

    """

    def __init__(
        self,
        bucket: str = BUCKET,
        log_path: str = ACTIVITY_LOG_PATH,
    ) -> None:
        """Initialise the logger."""
        self.bucket = bucket
        self.log_path = log_path
        self._client: Any = None

    # ------------------------------------------------------------------
    # GCS helpers (lazy client init so imports happen at runtime)
    # ------------------------------------------------------------------

    def _get_client(self) -> Any:
        """Return (and lazily create) the GCS client."""
        if self._client is None:
            if not _GCS_AVAILABLE or _gcs_storage is None:
                raise RuntimeError(
                    "google-cloud-storage is required for analytics logging. "
                    "Install it with: pip install google-cloud-storage"
                )
            self._client = _gcs_storage.Client()
        return self._client

    def _load_activity_log(self) -> dict[str, Any] | None:
        """Download the current activity log from GCS.

        Returns
        -------
        dict
            Parsed log with ``activities`` list and ``last_updated`` key.
            Returns an empty structure if the log does not yet exist.
            Returns ``None`` on any read error (caller must abort write).

        """
        try:
            client = self._get_client()
            bucket = client.bucket(self.bucket)
            blob = bucket.blob(self.log_path)
            if not blob.exists():
                return {"activities": [], "last_updated": None}
            data = blob.download_as_text()
            return json.loads(data)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse bookstack activity log: %s", exc)
            return None
        except Exception as exc:
            logger.error(
                "Failed to load bookstack activity log from GCS "
                "(aborting write to protect existing data): %s",
                exc,
            )
            return None

    def _save_activity_log(self, log_data: dict[str, Any]) -> bool:
        """Upload the activity log to GCS.

        Parameters
        ----------
        log_data : dict
            Updated activity log to persist.

        Returns
        -------
        bool
            ``True`` on success, ``False`` on failure.

        """
        try:
            client = self._get_client()
            bucket = client.bucket(self.bucket)
            blob = bucket.blob(self.log_path)
            blob.upload_from_string(
                json.dumps(log_data, indent=2),
                content_type="application/json",
            )
            return True
        except Exception as exc:
            logger.error("Failed to upload bookstack activity log to GCS: %s", exc)
            return False

    def _save_trace(self, trace: dict[str, Any], trace_path: str) -> bool:
        """Upload an individual query trace to GCS.

        Parameters
        ----------
        trace : dict
            Full trace data for one query.
        trace_path : str
            Destination path inside the bucket.

        Returns
        -------
        bool
            ``True`` on success, ``False`` on failure.

        """
        try:
            client = self._get_client()
            bucket = client.bucket(self.bucket)
            blob = bucket.blob(trace_path)
            blob.upload_from_string(
                json.dumps(trace, indent=2),
                content_type="application/json",
            )
            return True
        except Exception as exc:
            logger.error(
                "Failed to upload bookstack trace to GCS (%s): %s", trace_path, exc
            )
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_query(
        self,
        session_id: str,
        question: str,
        tool_calls: list[dict[str, Any]],
        answer: str,
        duration_seconds: float,
        status: str,
    ) -> bool:
        """Record a completed BookStack QA query to GCS.

        Saves two objects:

        1. An entry appended to the unified activity log (for aggregate views).
        2. A per-query trace file (for detailed inspection / recent queries).

        This method is synchronous and is intended to be called via
        ``asyncio.to_thread`` from async contexts so it does not block the
        event loop.

        Parameters
        ----------
        session_id : str
            Opaque session identifier from the API session store.
        question : str
            The user's raw question text.
        tool_calls : list[dict]
            Ordered list of ``{"tool": <name>, "input": {...}}`` dicts
            collected during the agent's tool-use loop.
        answer : str
            The agent's final answer (markdown).
        duration_seconds : float
            Wall-clock time from question receipt to answer emission.
        status : str
            ``"success"`` or ``"error"``.

        Returns
        -------
        bool
            ``True`` if both the trace and the activity log were saved
            successfully, ``False`` otherwise.

        """
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()

        # ------------------------------------------------------------------
        # 1. Build and save the per-query trace
        # ------------------------------------------------------------------
        trace: dict[str, Any] = {
            "session_id": session_id,
            "timestamp": timestamp,
            "question": question,
            "tool_calls": [
                {"seq": i + 1, "tool": tc["tool"], "input": tc.get("input", {})}
                for i, tc in enumerate(tool_calls)
            ],
            "answer": answer,
            "duration_seconds": round(duration_seconds, 3),
            "status": status,
        }

        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H%M%S")
        safe_sid = session_id[:8]
        trace_path = f"{TRACES_PREFIX}/{date_str}/{safe_sid}-{time_str}.json"

        trace_saved = self._save_trace(trace, trace_path)

        # ------------------------------------------------------------------
        # 2. Append to the unified activity log
        # ------------------------------------------------------------------
        tools_used = list(
            dict.fromkeys(tc["tool"] for tc in tool_calls)
        )  # preserve order, deduplicate

        # Per-tool call counts for accurate analytics
        tool_call_counts: dict[str, int] = {}
        for tc in tool_calls:
            tool_name = tc["tool"]
            tool_call_counts[tool_name] = tool_call_counts.get(tool_name, 0) + 1

        activity: dict[str, Any] = {
            "session_id": session_id,
            "timestamp": timestamp,
            "question": question[:300],  # keep activity log compact
            "tools_used": tools_used,
            "tool_call_counts": tool_call_counts,
            "num_tool_calls": len(tool_calls),
            "answer_length": len(answer),
            "duration_seconds": round(duration_seconds, 3),
            "status": status,
            "trace_path": trace_path,
        }

        log_data = self._load_activity_log()
        if log_data is None:
            logger.error(
                "Aborting bookstack activity log write for session %s "
                "to prevent overwriting existing data after a GCS read failure",
                session_id[:8],
            )
            return False

        log_data["activities"].append(activity)
        log_data["last_updated"] = timestamp

        log_saved = self._save_activity_log(log_data)

        if log_saved:
            logger.info(
                "Bookstack query logged (status=%s, tools=%s, session=%s)",
                status,
                tools_used,
                session_id[:8],
            )

        return trace_saved and log_saved
