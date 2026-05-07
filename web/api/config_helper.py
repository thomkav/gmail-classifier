"""
Helpers for reading and writing preferences in config.json.
"""

import json
from datetime import date

from constants import CONFIG_JSON


def _load() -> dict:
    if not CONFIG_JSON.exists():
        return {"preferences": {}}
    return json.loads(CONFIG_JSON.read_text())


def _save(cfg: dict) -> None:
    CONFIG_JSON.write_text(json.dumps(cfg, indent=2) + "\n")


def load_preference_list(pref_key: str) -> list[str]:
    """Return the list stored under preferences.<pref_key>."""
    cfg = _load()
    return list(cfg.get("preferences", {}).get(pref_key, []))


def append_to_preference_list(pref_key: str, new_values: list[str]) -> None:
    """Append new_values to preferences.<pref_key>, skipping duplicates."""
    if not new_values:
        return
    cfg = _load()
    prefs = cfg.setdefault("preferences", {})
    existing = set(prefs.get(pref_key, []))
    to_add = [v for v in new_values if v not in existing]
    if not to_add:
        return
    prefs.setdefault(pref_key, []).extend(to_add)
    _save(cfg)


def remove_from_preference_list(pref_key: str, values: list[str]) -> None:
    """Remove values from preferences.<pref_key>."""
    if not values:
        return
    cfg = _load()
    prefs = cfg.get("preferences", {})
    to_remove = set(values)
    prefs[pref_key] = [v for v in prefs.get(pref_key, []) if v not in to_remove]
    _save(cfg)
