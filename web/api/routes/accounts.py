from fastapi import APIRouter

router = APIRouter()


@router.get("/accounts")
def list_accounts():
    from db import list_accounts as _list_accounts
    return [
        {
            "id": a["id"],
            "email": a["email"],
            "display": a["display"],
            "is_default": bool(a["is_default"]),
            "last_synced_at": a["last_synced_at"],
        }
        for a in _list_accounts()
    ]
