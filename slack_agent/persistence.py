"""Durable per-session context snapshots.

Sessions previously lived only in process memory and died on every
redeploy. The archive writes one JSON snapshot per session key after
each turn and loads it lazily on the first access after a restart.

Locally the root is any directory; in production it is a Cloud Run
GCS volume mount, which needs no cloud SDK in the code path. The
service runs with ``max-instances=1`` (Socket Mode requires it), so
single-writer file semantics are safe.

Persistence is strictly best-effort: a failed read or write logs and
moves on, because losing a snapshot must never break answering.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_KEY_SAFE = re.compile(r"[^A-Za-z0-9_-]")


class ContextArchive:
    """File-backed store of per-session context snapshots.

    Parameters
    ----------
    root : str or Path
        Directory snapshots live in; created if missing.

    """

    def __init__(self, root: str | Path) -> None:
        """Create the archive directory if needed."""
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, channel: str, thread_ts: str) -> Path:
        key = _KEY_SAFE.sub("-", f"{channel}_{thread_ts}")
        return self._root / f"{key}.json"

    def load(self, channel: str, thread_ts: str) -> dict[str, Any] | None:
        """Return the stored snapshot for a session, or None.

        Corrupted or unreadable snapshots are treated as absent.
        """
        path = self._path(channel, thread_ts)
        try:
            data = json.loads(path.read_text())
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("ignoring unreadable snapshot %s: %s", path.name, exc)
            return None
        return data if isinstance(data, dict) else None

    def save(self, channel: str, thread_ts: str, payload: dict[str, Any]) -> None:
        """Write a session snapshot atomically (write to temp, then rename)."""
        path = self._path(channel, thread_ts)
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, default=str))
            os.replace(tmp, path)
        except OSError as exc:
            logger.warning("could not persist snapshot %s: %s", path.name, exc)
