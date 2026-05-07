"""Job runner — persisted background work with progress updates.

Each job is a row in the `jobs` table. A worker thread executes the job's
function and writes progress back to the row; SSE events are fired on every
state change so subscribed UIs update in real time.

Survives server restart: on startup we mark any `running` rows as `interrupted`
so the UI can flag them rather than waiting forever for progress that won't come.
"""
from __future__ import annotations

import json
import threading
import traceback
from datetime import datetime, timezone
from typing import Callable

from db import get_conn
from events import publish

# Registered job kinds → handler function. Handlers receive (job_id, params, ctx).
_HANDLERS: dict[str, Callable[..., dict]] = {}


def register(kind: str):
    """Decorator: register a handler for a job kind."""
    def deco(fn):
        _HANDLERS[kind] = fn
        return fn
    return deco


# ── DB helpers ─────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_job(kind: str, params: dict | None = None, account_id: int | None = None) -> int:
    cur = get_conn().execute(
        """
        INSERT INTO jobs (account_id, kind, status, params_json, created_at)
        VALUES (?, ?, 'pending', ?, CURRENT_TIMESTAMP)
        """,
        (account_id, kind, json.dumps(params or {})),
    )
    job_id = int(cur.lastrowid)
    publish("job.created", {"id": job_id, "job_kind": kind, "status": "pending"})
    return job_id


def _row_to_dict(row) -> dict:
    if row is None:
        return None  # type: ignore[return-value]
    out = dict(row)
    for key in ("params_json", "result_json"):
        if out.get(key):
            try:
                out[key.replace("_json", "")] = json.loads(out[key])
            except Exception:
                out[key.replace("_json", "")] = None
        else:
            out[key.replace("_json", "")] = None
        out.pop(key, None)
    return out


def get_job(job_id: int) -> dict | None:
    row = get_conn().execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_dict(row)


def list_jobs(kind: str | None = None, limit: int = 20) -> list[dict]:
    if kind:
        rows = get_conn().execute(
            "SELECT * FROM jobs WHERE kind=? ORDER BY id DESC LIMIT ?",
            (kind, limit),
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def latest_job(kind: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM jobs WHERE kind=? ORDER BY id DESC LIMIT 1", (kind,)
    ).fetchone()
    return _row_to_dict(row)


def _set_status(job_id: int, status: str, **fields) -> None:
    set_clauses = ["status = ?"]
    params: list = [status]
    for k, v in fields.items():
        set_clauses.append(f"{k} = ?")
        params.append(v)
    params.append(job_id)
    get_conn().execute(
        f"UPDATE jobs SET {', '.join(set_clauses)} WHERE id = ?", params
    )


# ── Progress reporter ─────────────────────────────────────────────────────


class JobContext:
    """Passed to handlers. Lets them report progress and set phase."""

    def __init__(self, job_id: int):
        self.job_id = job_id
        self._last_emit = 0.0
        self._lock = threading.Lock()

    def progress(self, done: int, total: int, phase: str | None = None, *, force: bool = False) -> None:
        """Update progress. Throttled SSE emissions — at most ~5/sec per job."""
        import time
        now = time.time()
        with self._lock:
            updates = {"progress_done": done, "progress_total": total}
            if phase is not None:
                updates["phase"] = phase
            cols = ", ".join(f"{k} = ?" for k in updates)
            get_conn().execute(
                f"UPDATE jobs SET {cols} WHERE id = ?",
                (*updates.values(), self.job_id),
            )
            should_emit = force or (now - self._last_emit) > 0.2 or done == total
            if should_emit:
                self._last_emit = now
                publish("job.progress", {
                    "id": self.job_id,
                    "done": done,
                    "total": total,
                    "phase": phase,
                })

    def update_phase(self, phase: str) -> None:
        get_conn().execute("UPDATE jobs SET phase = ? WHERE id = ?", (phase, self.job_id))
        publish("job.progress", {"id": self.job_id, "phase": phase})


# ── Runner ────────────────────────────────────────────────────────────────


def _run(job_id: int) -> None:
    job = get_job(job_id)
    if job is None:
        return
    handler = _HANDLERS.get(job["kind"])
    if handler is None:
        _set_status(job_id, "error", error=f"no handler for kind={job['kind']}", finished_at=_now())
        publish("job.error", {"id": job_id, "error": f"no handler for kind={job['kind']}"})
        return

    _set_status(job_id, "running", started_at=_now())
    publish("job.progress", {"id": job_id, "job_kind": job["kind"], "status": "running"})

    ctx = JobContext(job_id)
    try:
        result = handler(job_id, job.get("params") or {}, ctx)
        result_json = json.dumps(result) if result is not None else None
        _set_status(job_id, "done", result_json=result_json, finished_at=_now())
        publish("job.done", {"id": job_id, "job_kind": job["kind"], "result": result})
    except Exception as e:
        tb = traceback.format_exc()
        _set_status(job_id, "error", error=f"{e}\n{tb}", finished_at=_now())
        publish("job.error", {"id": job_id, "error": str(e)})


def enqueue(kind: str, params: dict | None = None, account_id: int | None = None) -> int:
    """Create a job row and start its worker thread immediately. Returns job_id."""
    if kind not in _HANDLERS:
        raise ValueError(f"unknown job kind: {kind}")
    job_id = create_job(kind, params, account_id)
    t = threading.Thread(target=_run, args=(job_id,), daemon=True, name=f"job-{job_id}-{kind}")
    t.start()
    return job_id


def reset_orphaned() -> int:
    """Mark `running` jobs as `interrupted` on startup. Returns count."""
    cur = get_conn().execute(
        "UPDATE jobs SET status='interrupted', finished_at=CURRENT_TIMESTAMP, error='process restarted' WHERE status='running'"
    )
    return cur.rowcount or 0
