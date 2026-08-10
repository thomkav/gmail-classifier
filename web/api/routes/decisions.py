from fastapi import APIRouter
from decision_store import load_decisions

router = APIRouter()


@router.get("/decisions")
def get_decisions(account_id: int | None = None):
    return load_decisions(account_id)


@router.get("/decisions/summary")
def get_decisions_summary(account_id: int | None = None):
    decisions = load_decisions(account_id)
    summary: dict[str, int] = {}
    for entry in decisions.values():
        state = entry.get("state", "unknown")
        summary[state] = summary.get(state, 0) + 1
    return summary
