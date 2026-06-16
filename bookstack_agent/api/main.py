"""FastAPI backend for the BookStack QA agent.

Exposes a streaming endpoint that runs BookstackQAAgent and emits
Server-Sent Events so the Next.js frontend can render tool-use progress
and the final answer incrementally.

Concurrency model
-----------------
- The BookstackQAAgent is instantiated once at startup (via ``lifespan``)
  and shared across all requests. Its ``AsyncAnthropic`` client maintains
  its own connection pool and is safe for concurrent use.
- Each request gets its own isolated ``ask_stream`` coroutine with its own
  copy of the message history — no mutable state is shared between requests.
- BookStack HTTP calls inside tool execution run in a thread pool via
  ``asyncio.to_thread``, so they never block the event loop.

Session management
------------------
- Sessions are stored in memory (``app.state.sessions``) as a dict of
  ``{session_id: MessageHistory}``.
- Clients receive a ``session_id`` in the first SSE event and pass it back
  on subsequent requests to continue the conversation.
- A per-session ``asyncio.Lock`` prevents concurrent writes to the same
  session's history while still allowing different sessions to run in parallel.
- Sessions are pruned to ``MAX_SESSIONS`` (oldest-first) to bound memory use.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from collections import OrderedDict
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any, TypeAlias

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from aieng_bot.bookstack import BookstackQAAgent
from aieng_bot.bookstack.activity_logger import BookstackActivityLogger
from aieng_bot.bookstack.agent import MessageHistory

api_logger = logging.getLogger(__name__)

load_dotenv()

MAX_SESSIONS = 500  # prune oldest sessions beyond this limit


# ---------------------------------------------------------------------------
# Lifespan — build the shared agent once at startup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Create the BookstackQAAgent and session store at startup."""
    llm_base_url = os.environ.get("LLM_BASE_URL")
    llm_key_var = "LLM_API_KEY" if llm_base_url else "ANTHROPIC_API_KEY"
    missing = [
        v
        for v in (llm_key_var, "BOOKSTACK_TOKEN_ID", "BOOKSTACK_TOKEN_SECRET")
        if not os.environ.get(v)
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    application.state.agent = BookstackQAAgent(
        base_url=os.environ.get(
            "BOOKSTACK_URL", "https://bookstack.vectorinstitute.ai"
        ),
        token_id=os.environ["BOOKSTACK_TOKEN_ID"],
        token_secret=os.environ["BOOKSTACK_TOKEN_SECRET"],
        llm_base_url=llm_base_url,
    )

    # OrderedDict preserves insertion order for LRU-style eviction
    application.state.sessions = OrderedDict()
    application.state.session_locks = {}

    # Analytics logger — initialised lazily; failures are non-fatal
    application.state.activity_logger = BookstackActivityLogger()

    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="BookStack QA API", version="1.0.0", lifespan=lifespan)

_ALLOWED_ORIGINS = [
    "https://bookstack.vectorinstitute.ai",
    "http://localhost:3001",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_agent() -> BookstackQAAgent:
    """Return the shared BookstackQAAgent."""
    agent: BookstackQAAgent | None = getattr(app.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialised")
    return agent


AgentDep: TypeAlias = Annotated[BookstackQAAgent, Depends(get_agent)]


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def _get_or_create_session(session_id: str | None) -> tuple[str, MessageHistory]:
    """Return ``(session_id, history)`` — creating a new session if needed."""
    sessions: OrderedDict[str, MessageHistory] = app.state.sessions

    if session_id and session_id in sessions:
        # Move to end (most-recently-used)
        sessions.move_to_end(session_id)
        return session_id, list(sessions[session_id])

    new_id = session_id or str(uuid.uuid4())
    sessions[new_id] = []

    # Evict oldest sessions if over limit
    while len(sessions) > MAX_SESSIONS:
        oldest = next(iter(sessions))
        sessions.pop(oldest)
        app.state.session_locks.pop(oldest, None)

    return new_id, []


def _save_session(session_id: str, history: MessageHistory) -> None:
    """Persist updated history and refresh LRU position."""
    sessions: OrderedDict[str, MessageHistory] = app.state.sessions
    sessions[session_id] = history
    sessions.move_to_end(session_id)


def _get_session_lock(session_id: str) -> asyncio.Lock:
    """Return (or create) the per-session write lock."""
    locks: dict[str, asyncio.Lock] = app.state.session_locks
    if session_id not in locks:
        locks[session_id] = asyncio.Lock()
    return locks[session_id]


# ---------------------------------------------------------------------------
# Analytics helpers
# ---------------------------------------------------------------------------


async def _log_query_bg(
    activity_logger: BookstackActivityLogger,
    session_id: str,
    question: str,
    tool_calls: list[dict[str, Any]],
    answer: str,
    duration_seconds: float,
    status: str,
    user_email: str | None,
) -> None:
    """Run analytics logging in a thread pool (non-blocking)."""
    try:
        await asyncio.to_thread(
            activity_logger.log_query,
            session_id,
            question,
            tool_calls,
            answer,
            duration_seconds,
            status,
            user_email,
        )
    except Exception as exc:  # noqa: BLE001
        api_logger.warning("Analytics logging failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
    """Request body for POST /api/ask."""

    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = Field(
        default=None,
        description="Opaque session token returned by a previous response. "
        "Omit to start a new conversation.",
    )
    user_email: str | None = Field(
        default=None,
        description="Email of the authenticated user. Injected by the Next.js "
        "proxy from the server-side session; ignored if sent directly.",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/api/ask")
async def ask(request: AskRequest, agent: AgentDep) -> StreamingResponse:
    """Stream an answer to a BookStack question as Server-Sent Events.

    SSE event types (each ``data:`` line is a JSON object):

    - ``{"type": "session", "session_id": "<id>"}``
      — first event; pass ``session_id`` back on subsequent requests.
    - ``{"type": "tool_use", "tool": "<name>", "input": {...}}``
      — emitted before each tool call.
    - ``{"type": "answer", "text": "<markdown>"}``
      — final answer (markdown-formatted).
    - ``{"type": "error", "message": "<msg>"}``
      — unrecoverable error.

    The stream ends with ``data: [DONE]``.
    """

    async def event_stream() -> AsyncGenerator[str, None]:
        sid, history = _get_or_create_session(request.session_id)
        lock = _get_session_lock(sid)

        # Analytics accumulators
        start_time = time.monotonic()
        query_tool_calls: list[dict[str, Any]] = []
        final_answer = ""
        final_status = "error"

        # Emit the session ID immediately so the client can store it
        yield f"data: {json.dumps({'type': 'session', 'session_id': sid})}\n\n"

        # Serialize within the same session; different sessions run concurrently
        async with lock:
            updated_history: MessageHistory = history
            async for event in agent.ask_stream(request.question, history=history):
                event_type = event.get("type")

                if event_type == "tool_use":
                    query_tool_calls.append(
                        {
                            "tool": event.get("tool", ""),
                            "input": dict(event.get("input", {})),
                        }
                    )
                    yield f"data: {json.dumps(event)}\n\n"

                elif event_type == "tool_resolve":
                    # Enrich the matching get_page tool call with the resolved title
                    page_id = event.get("page_id")
                    page_title = event.get("page_title")
                    if page_id is not None and page_title:
                        for tc in reversed(query_tool_calls):
                            if (
                                tc["tool"] == "get_page"
                                and tc["input"].get("page_id") == page_id
                                and "page_title" not in tc["input"]
                            ):
                                tc["input"]["page_title"] = page_title
                                break
                    yield f"data: {json.dumps(event)}\n\n"

                elif event_type == "answer":
                    updated_history = event.pop("history", history)
                    final_answer = event.get("text", "")
                    final_status = "success"
                    yield f"data: {json.dumps(event)}\n\n"

                elif event_type == "error":
                    final_status = "error"
                    yield f"data: {json.dumps(event)}\n\n"

                else:
                    yield f"data: {json.dumps(event)}\n\n"

            _save_session(sid, updated_history)

        # Fire analytics logging asynchronously — does not block the stream
        duration = time.monotonic() - start_time
        activity_logger: BookstackActivityLogger = app.state.activity_logger
        asyncio.create_task(
            _log_query_bg(
                activity_logger=activity_logger,
                session_id=sid,
                question=request.question,
                tool_calls=query_tool_calls,
                answer=final_answer,
                duration_seconds=duration,
                status=final_status,
                user_email=request.user_email,
            )
        )

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.delete("/api/session/{session_id}")
async def clear_session(session_id: str) -> dict[str, str]:
    """Delete a session and its conversation history.

    Parameters
    ----------
    session_id : str
        The session ID to clear.

    Returns
    -------
    dict
        Confirmation message.

    """
    sessions: OrderedDict[str, Any] = app.state.sessions
    sessions.pop(session_id, None)
    app.state.session_locks.pop(session_id, None)
    return {"status": "cleared", "session_id": session_id}
