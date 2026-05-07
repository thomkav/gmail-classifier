from pathlib import Path

API_DIR        = Path(__file__).resolve().parent   # web/api/
PROJECT_ROOT   = API_DIR.parent.parent             # gmail-classifier/
SCRIPTS_DIR    = PROJECT_ROOT / "scripts"
CONFIG_JSON    = PROJECT_ROOT / "config.json"
UNSUB_LOG      = PROJECT_ROOT / ".unsubscribe_log.json"
DECISIONS_JSON = PROJECT_ROOT / "domain_decisions.json"
