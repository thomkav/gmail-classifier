"""
Helpers for reading and writing preferences in config.json.
"""

import json
from datetime import date

from constants import config_json_for
from db import get_default_account_id


def _load(account_id: int) -> dict:
    path = config_json_for(account_id)
    if not path.exists():
        return {"preferences": {}}
    return json.loads(path.read_text())


def _save(cfg: dict, account_id: int) -> None:
    config_json_for(account_id).write_text(json.dumps(cfg, indent=2) + "\n")


def load_preference_list(pref_key: str, account_id: int | None = None) -> list[str]:
    """Return the list stored under preferences.<pref_key>."""
    cfg = _load(account_id or get_default_account_id())
    return list(cfg.get("preferences", {}).get(pref_key, []))


def append_to_preference_list(pref_key: str, new_values: list[str], account_id: int | None = None) -> None:
    """Append new_values to preferences.<pref_key>, skipping duplicates."""
    if not new_values:
        return
    account_id = account_id or get_default_account_id()
    cfg = _load(account_id)
    prefs = cfg.setdefault("preferences", {})
    existing = set(prefs.get(pref_key, []))
    to_add = [v for v in new_values if v not in existing]
    if not to_add:
        return
    prefs.setdefault(pref_key, []).extend(to_add)
    _save(cfg, account_id)


def remove_from_preference_list(pref_key: str, values: list[str], account_id: int | None = None) -> None:
    """Remove values from preferences.<pref_key>."""
    if not values:
        return
    account_id = account_id or get_default_account_id()
    cfg = _load(account_id)
    prefs = cfg.get("preferences", {})
    to_remove = set(values)
    prefs[pref_key] = [v for v in prefs.get(pref_key, []) if v not in to_remove]
    _save(cfg, account_id)
