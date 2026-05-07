"""Jobs and event-stream endpoints."""
import asyncio
import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import jobs as jobs_mod
import events as events_mod

router = APIRouter()


class EnqueueRequest(BaseModel):
    kind: str
    params: dict | None = None


@router.post("/jobs")
def enqueue_job(req: EnqueueRequest):
    try:
        job_id = jobs_mod.enqueue(req.kind, req.params or {})
        return {"id": job_id, "kind": req.kind}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/jobs")
def list_jobs(kind: str | None = None, limit: int = 20):
    return {"jobs": jobs_mod.list_jobs(kind, limit)}


@router.get("/jobs/latest")
def latest_job(kind: str):
    job = jobs_mod.latest_job(kind)
    if job is None:
        raise HTTPException(status_code=404, detail=f"no jobs for kind={kind}")
    return job


@router.get("/jobs/{job_id}")
def get_job(job_id: int):
    job = jobs_mod.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"no job with id={job_id}")
    return job


# ── SSE event stream ──────────────────────────────────────────────────────


@router.get("/events")
async def events_stream(request: Request):
    """Subscribe to live events. Emits a `hello` event immediately, then a
    keep-alive comment every 15 s so proxies don't close the connection."""
    queue = events_mod.subscribe()

    async def gen():
        try:
            yield events_mod.format_sse({"kind": "hello"})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield events_mod.format_sse(event)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            events_mod.unsubscribe(queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disables proxy buffering when present
            "Connection": "keep-alive",
        },
    )
