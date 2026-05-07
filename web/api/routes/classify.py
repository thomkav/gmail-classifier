import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Module-level progress state — updated by the classify thread, read by GET /classify/progress
_progress: dict = {
    "running": False,
    "total": 0,
    "completed": 0,
    "results_so_far": {},
}

VALID_CATEGORIES = {"newsletter", "promotion", "receipt", "notification", "personal", "unknown"}

_CATEGORY_DEFAULT_ACTION = {
    "newsletter": "review",
    "promotion": "archive",
    "receipt": "archive",
    "notification": "keep",
    "personal": "keep",
    "unknown": "review",
}


class ManualClassifyRequest(BaseModel):
    domain: str
    category: str


@router.get("/classify/progress")
async def classify_progress():
    """Poll this while /classify/unknown is running to get live batch progress."""
    return _progress


@router.post("/classify/unknown")
async def classify_unknown():
    """Classify all unknown domains using the local LLM. Reads the audit view fresh
    from SQLite each time so it works without depending on a previous /api/audit call."""
    from routes.audit import _build_audit_view
    from db import get_default_account_id
    account_id = get_default_account_id()
    try:
        cache = await asyncio.to_thread(_build_audit_view, account_id, True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not build audit view: {e}")

    unknown_domains = [
        d for d in cache["domains"]
        if not d.get("classification") or d["classification"]["category"] == "unknown"
    ]

    if not unknown_domains:
        return {"classified": 0, "results": {}}

    domain_subjects = {
        d["domain"]: [e["subject"] for e in d.get("emails", []) if e.get("subject")]
        for d in unknown_domains
    }

    total = len(domain_subjects)
    _progress["running"] = True
    _progress["total"] = total
    _progress["completed"] = 0
    _progress["results_so_far"] = {}

    def on_batch_done(batch_results: dict):
        _progress["completed"] += len(batch_results)
        for domain, r in batch_results.items():
            cat = r.get("category", "unknown")
            if cat == "personal":
                cat = "unknown"
            _progress["results_so_far"][domain] = {
                "category": cat,
                "confidence": r.get("confidence", 0),
                "reasoning": r.get("reasoning", ""),
                "tier": None,
                "suggested_action": _CATEGORY_DEFAULT_ACTION.get(cat, "review"),
                "source": "llm",
            }

    try:
        raw = await asyncio.to_thread(_do_classify_llm, domain_subjects, on_batch_done)
    except Exception as e:
        _progress["running"] = False
        raise HTTPException(status_code=500, detail=str(e))

    _progress["running"] = False

    results = {}
    for domain, r in raw.items():
        category = r.get("category", "unknown")
        if category == "personal":
            category = "unknown"
        results[domain] = {
            "category": category,
            "confidence": r.get("confidence", 0),
            "reasoning": r.get("reasoning", ""),
            "tier": None,
            "suggested_action": _CATEGORY_DEFAULT_ACTION.get(category, "review"),
            "source": "llm",
        }

    newly_classified = sum(1 for r in results.values() if r["category"] != "unknown")
    return {"classified": newly_classified, "results": results}


@router.post("/domains/classify")
async def classify_domain_manual(req: ManualClassifyRequest):
    """Manually set a domain's classification category."""
    if req.category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}",
        )
    try:
        await asyncio.to_thread(_do_set_manual, req.domain, req.category)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    category = req.category
    if category == "personal":
        category = "unknown"

    return {
        "ok": True,
        "domain": req.domain,
        "category": category,
        "confidence": 100,
        "reasoning": f"Manual: {req.category}",
        "tier": None,
        "suggested_action": _CATEGORY_DEFAULT_ACTION.get(req.category, "review"),
        "source": "manual",
    }


@router.delete("/domains/classify/{domain}")
async def clear_domain_classification(domain: str):
    """Remove a manual classification override for a domain."""
    try:
        await asyncio.to_thread(_do_clear_manual, domain)
        return {"ok": True, "domain": domain}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _do_classify_llm(domain_subjects: dict, on_batch_done=None) -> dict:
    from llm_classifier import classify_domains_llm
    return classify_domains_llm(domain_subjects, on_batch_done=on_batch_done)


def _do_set_manual(domain: str, category: str) -> None:
    from llm_classifier import set_manual_classification
    set_manual_classification(domain, category)


def _do_clear_manual(domain: str) -> None:
    from llm_classifier import clear_manual_classification
    clear_manual_classification(domain)
