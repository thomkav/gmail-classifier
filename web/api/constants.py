from pathlib import Path

API_DIR        = Path(__file__).resolve().parent   # web/api/
PROJECT_ROOT   = API_DIR.parent.parent             # gmail-classifier/
SCRIPTS_DIR    = PROJECT_ROOT / "scripts"

# Legacy single-account paths — still used directly by the CLI scripts under
# scripts/, which remain single-account (default account) only.
CONFIG_JSON    = PROJECT_ROOT / "config.json"
UNSUB_LOG      = PROJECT_ROOT / ".unsubscribe_log.json"
DECISIONS_JSON = PROJECT_ROOT / "domain_decisions.json"


def _account_dir(account_id: int) -> Path:
    """Per-account state directory. The default account keeps using the legacy
    root-level files (no migration needed for existing data); every other
    account gets its own directory under data/accounts/<id>/."""
    from db import get_default_account_id
    if account_id == get_default_account_id():
        return PROJECT_ROOT
    d = PROJECT_ROOT / "data" / "accounts" / str(account_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_json_for(account_id: int) -> Path:
    """Per-account config.json. `categories` (the classifier's receipt/newsletter/
    promotion pattern rules) is shared static config rather than personal
    preference data, so a brand-new account's file is seeded from the default
    account's categories on first access instead of starting empty."""
    from db import get_default_account_id
    default_id = get_default_account_id()
    path = _account_dir(account_id) / "config.json"
    if account_id != default_id and not path.exists():
        _seed_categories(path, default_id)
    return path


def _seed_categories(path: Path, default_account_id: int) -> None:
    import json
    default_path = _account_dir(default_account_id) / "config.json"
    categories = {}
    if default_path.exists():
        try:
            categories = json.loads(default_path.read_text()).get("categories", {})
        except (json.JSONDecodeError, OSError):
            categories = {}
    path.write_text(json.dumps({"categories": categories, "preferences": {}}, indent=2) + "\n")


def unsub_log_for(account_id: int) -> Path:
    return _account_dir(account_id) / ".unsubscribe_log.json"


def decisions_json_for(account_id: int) -> Path:
    return _account_dir(account_id) / "domain_decisions.json"
