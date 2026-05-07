import json
from datetime import date

from constants import DECISIONS_JSON


def load_decisions() -> dict:
    if not DECISIONS_JSON.exists():
        return {}
    return json.loads(DECISIONS_JSON.read_text())


def save_decision(domain: str, state: str, email_count: int) -> None:
    save_decisions_bulk([(domain, state, email_count)])


def save_decisions_bulk(entries: list) -> None:
    decisions = load_decisions()
    today = date.today().isoformat()
    for domain, state, email_count in entries:
        decisions[domain] = {
            "state": state,
            "decided_at": today,
            "email_count": email_count,
        }
    DECISIONS_JSON.write_text(json.dumps(decisions, indent=2) + "\n")
