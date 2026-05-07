import asyncio
import sys
from constants import API_DIR, SCRIPTS_DIR

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(API_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.audit import router as audit_router
from routes.domains import router as domains_router
from routes.autoarchive import router as autoarchive_router
from routes.decisions import router as decisions_router
from routes.classify import router as classify_router
from routes.jobs import router as jobs_router
from routes.llm import router as llm_router

# Register job handlers (decorator side effects)
import job_handlers  # noqa: F401

app = FastAPI(title="Gmail Classifier API")


@app.on_event("startup")
def _on_startup():
    """Apply migrations, attach event loop to broker, mark orphaned jobs."""
    from db import get_conn
    import events as events_mod
    import jobs as jobs_mod

    get_conn()
    events_mod.attach_loop(asyncio.get_event_loop())
    orphaned = jobs_mod.reset_orphaned()
    if orphaned:
        print(f"[startup] marked {orphaned} orphaned jobs as interrupted")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:45101"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(audit_router, prefix="/api")
app.include_router(domains_router, prefix="/api")
app.include_router(autoarchive_router, prefix="/api")
app.include_router(decisions_router, prefix="/api")
app.include_router(classify_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(llm_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
