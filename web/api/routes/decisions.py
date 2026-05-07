from fastapi import APIRouter
from decision_store import load_decisions

router = APIRouter()


@router.get("/decisions")
def get_decisions():
    return load_decisions()


@router.get("/decisions/summary")
def get_decisions_summary():
    decisions = load_decisions()
    summary: dict[str, int] = {}
    for entry in decisions.values():
        state = entry.get("state", "unknown")
        summary[state] = summary.get(state, 0) + 1
    return summary
