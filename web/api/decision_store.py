import json
from datetime import date

from constants import decisions_json_for
from db import get_default_account_id


def load_decisions(account_id: int | None = None) -> dict:
    path = decisions_json_for(account_id or get_default_account_id())
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_decision(domain: str, state: str, email_count: int, account_id: int | None = None) -> None:
    save_decisions_bulk([(domain, state, email_count)], account_id)


def save_decisions_bulk(entries: list, account_id: int | None = None) -> None:
    account_id = account_id or get_default_account_id()
    decisions = load_decisions(account_id)
    today = date.today().isoformat()
    for domain, state, email_count in entries:
        decisions[domain] = {
            "state": state,
            "decided_at": today,
            "email_count": email_count,
        }
    decisions_json_for(account_id).write_text(json.dumps(decisions, indent=2) + "\n")
