"""In-process pub/sub for SSE.

Single broker. Subscribers register a queue, publishers push events. Events are
plain dicts; we dump them to JSON in the SSE handler. The broker is
thread-safe because asyncio.Queue.put_nowait works from any thread once the
loop is running, and we use a threading.Lock for the subscriber set.
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

_subscribers: set[asyncio.Queue] = set()
_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None


def attach_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Called once at startup so worker threads can schedule queue puts."""
    global _loop
    _loop = loop


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=256)
    with _lock:
        _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    with _lock:
        _subscribers.discard(q)


def publish(kind: str, payload: dict[str, Any]) -> None:
    """Fan out an event to all current subscribers. Safe to call from threads.

    The event always carries its `kind` (SSE event type) — payload keys cannot
    shadow it, even if the payload itself is named `kind` (e.g. a job kind goes
    into `job_kind` instead).
    """
    event = {**payload, "kind": kind}
    if _loop is None:
        return  # event broker not yet attached; drop the event silently

    def _fanout():
        with _lock:
            queues = list(_subscribers)
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # subscriber is slow; drop the event for them rather than blocking
                pass

    if threading.current_thread() is threading.main_thread() and _loop.is_running():
        try:
            _loop.call_soon_threadsafe(_fanout)
        except RuntimeError:
            pass
    else:
        try:
            _loop.call_soon_threadsafe(_fanout)
        except RuntimeError:
            pass


def format_sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"
