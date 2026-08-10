"""SQLite cache + schema migrations.

One connection per thread (thread-local), all pointing at the same WAL-mode
file — WAL explicitly supports concurrent readers plus one writer across
connections. A single connection object shared across threads is NOT safe
even with check_same_thread=False: that flag only disables Python's own
same-thread guard, it does not make libsqlite3 safe for concurrent use of one
connection from multiple OS threads, and doing so has been observed to
segfault the whole process under real concurrent request load.

Schema versioning is intentionally simple: a `schema_migrations` table records
applied migrations by integer version. To add a migration, append a function to
MIGRATIONS in version order — never edit an existing one.
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

from constants import PROJECT_ROOT

DB_DIR = PROJECT_ROOT / "data"
DB_PATH = DB_DIR / "gmail_classifier.sqlite"

_local = threading.local()
_migrate_lock = threading.Lock()
_migrated = False


def _connect() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        DB_PATH,
        isolation_level=None,  # autocommit; we manage transactions explicitly
        detect_types=sqlite3.PARSE_DECLTYPES,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def get_conn() -> sqlite3.Connection:
    """Return this thread's connection, creating it (and migrating the schema,
    once process-wide) on first call from that thread."""
    global _migrated
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _connect()
        _local.conn = conn
        if not _migrated:
            with _migrate_lock:
                if not _migrated:
                    _migrate(conn)
                    _migrated = True
    return conn


@contextmanager
def transaction():
    """Use as: `with transaction() as conn: conn.execute(...)`. Rolls back on raise."""
    conn = get_conn()
    conn.execute("BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


# ── Migrations ─────────────────────────────────────────────────────────────

_M001_STATEMENTS = [
    """CREATE TABLE accounts (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        email          TEXT    NOT NULL UNIQUE,
        display        TEXT,
        is_default     INTEGER NOT NULL DEFAULT 0,
        created_at     TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_synced_at TEXT
    )""",
    """CREATE TABLE mailbox_state (
        account_id   INTEGER NOT NULL,
        mailbox      TEXT    NOT NULL,
        uidvalidity  INTEGER,
        last_uid     INTEGER NOT NULL DEFAULT 0,
        updated_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (account_id, mailbox),
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
    )""",
    """CREATE TABLE messages (
        account_id    INTEGER NOT NULL,
        uidvalidity   INTEGER NOT NULL,
        uid           INTEGER NOT NULL,
        mailbox       TEXT    NOT NULL,
        sender        TEXT    NOT NULL DEFAULT '',
        sender_addr   TEXT    NOT NULL DEFAULT '',
        domain        TEXT    NOT NULL DEFAULT '',
        subject       TEXT    NOT NULL DEFAULT '',
        internal_date TEXT,
        seen          INTEGER NOT NULL DEFAULT 0,
        in_inbox      INTEGER NOT NULL DEFAULT 1,
        fetched_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        removed_at    TEXT,
        PRIMARY KEY (account_id, uidvalidity, uid),
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
    )""",
    "CREATE INDEX idx_messages_domain   ON messages (account_id, domain)",
    "CREATE INDEX idx_messages_in_inbox ON messages (account_id, in_inbox, seen)",
    "CREATE INDEX idx_messages_fetched  ON messages (fetched_at)",
    """CREATE TABLE jobs (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id     INTEGER,
        kind           TEXT    NOT NULL,
        status         TEXT    NOT NULL DEFAULT 'pending',
        progress_total INTEGER NOT NULL DEFAULT 0,
        progress_done  INTEGER NOT NULL DEFAULT 0,
        phase          TEXT,
        params_json    TEXT,
        result_json    TEXT,
        error          TEXT,
        started_at     TEXT,
        finished_at    TEXT,
        created_at     TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL
    )""",
    "CREATE INDEX idx_jobs_kind_created ON jobs (kind, created_at DESC)",
    "CREATE INDEX idx_jobs_status       ON jobs (status)",
]


def _m001_init(conn: sqlite3.Connection) -> None:
    for stmt in _M001_STATEMENTS:
        conn.execute(stmt)


def _m002_seed_default_account(conn: sqlite3.Connection) -> None:
    """Seed a default account row from $GMAIL_EMAIL (or the legacy default)."""
    email = os.environ.get("GMAIL_EMAIL", "thomkav@gmail.com")
    cur = conn.execute("SELECT COUNT(*) FROM accounts")
    if cur.fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO accounts (email, is_default) VALUES (?, 1)",
            (email,),
        )


def _m003_password_env_var(conn: sqlite3.Connection) -> None:
    """Explicit app-password env var name per account, overriding the derived
    slug — accounts are often set up by hand with a human-chosen var name."""
    conn.execute("ALTER TABLE accounts ADD COLUMN password_env_var TEXT")


MIGRATIONS = [
    (1, "init", _m001_init),
    (2, "seed_default_account", _m002_seed_default_account),
    (3, "password_env_var", _m003_password_env_var),
]


def _migrate(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    for version, name, fn in MIGRATIONS:
        if version in applied:
            continue
        conn.execute("BEGIN")
        try:
            fn(conn)
            conn.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                (version, name),
            )
            conn.execute("COMMIT")
            print(f"[db] applied migration {version:03d} {name}", file=sys.stderr)
        except Exception:
            conn.execute("ROLLBACK")
            raise


# ── Account helpers ────────────────────────────────────────────────────────

def get_default_account_id() -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM accounts WHERE is_default = 1 LIMIT 1"
    ).fetchone()
    if row is None:
        # Legacy fallback — shouldn't happen after migration 002
        row = conn.execute("SELECT id FROM accounts ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise RuntimeError("No accounts configured. Run `task db:migrate`.")
    return int(row["id"])


def get_account(account_id: int) -> sqlite3.Row | None:
    return get_conn().execute(
        "SELECT * FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()


def list_accounts() -> list[sqlite3.Row]:
    return list(get_conn().execute("SELECT * FROM accounts ORDER BY id"))


def account_env_var(email: str) -> str:
    """Deterministic app-password env var name for an account, e.g.
    thomaskavanagh.dev@gmail.com -> GMAIL_APP_PASSWORD_THOMASKAVANAGH_DEV.
    """
    local_part = email.split("@", 1)[0]
    slug = re.sub(r"[^A-Za-z0-9]+", "_", local_part).strip("_").upper()
    return f"GMAIL_APP_PASSWORD_{slug}"


def get_account_password(account_id: int) -> str:
    """Resolve an account's app password: explicit password_env_var column first
    (accounts are often wired up by hand with a human-chosen var name), then the
    derived slug, then — for the default account only — the legacy unsuffixed
    $GMAIL_APP_PASSWORD for backward compatibility."""
    acct = get_account(account_id)
    if acct is None:
        raise RuntimeError(f"unknown account_id={account_id}")
    var = acct["password_env_var"] or account_env_var(acct["email"])
    password = os.environ.get(var, "")
    if not password and acct["is_default"]:
        password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not password:
        raise RuntimeError(
            f"No app password set for {acct['email']} — set ${var} in ~/.zsh_secrets"
        )
    return password


def add_account(
    email: str,
    display: str | None = None,
    make_default: bool = False,
    password_env_var: str | None = None,
) -> int:
    with transaction() as c:
        if make_default:
            c.execute("UPDATE accounts SET is_default = 0")
        cur = c.execute(
            "INSERT INTO accounts (email, display, is_default, password_env_var) VALUES (?, ?, ?, ?)",
            (email, display, 1 if make_default else 0, password_env_var),
        )
        rowid = cur.lastrowid
        if rowid is None:
            raise RuntimeError("insert failed: no lastrowid")
        return int(rowid)


def set_account_password_env_var(account_id: int, var_name: str) -> None:
    get_conn().execute(
        "UPDATE accounts SET password_env_var = ? WHERE id = ?", (var_name, account_id)
    )


# ── CLI entrypoint ─────────────────────────────────────────────────────────

def _cli() -> int:
    if len(sys.argv) < 2:
        print("usage: python3 db.py {migrate|status|reset|add-account|list-accounts}", file=sys.stderr)
        return 2
    cmd = sys.argv[1]
    if cmd == "add-account":
        if len(sys.argv) < 3:
            print("usage: python3 db.py add-account <email> [display] [--default] [--env-var NAME]", file=sys.stderr)
            return 2
        email = sys.argv[2]
        rest = sys.argv[3:]
        make_default = "--default" in rest
        env_var = None
        if "--env-var" in rest:
            i = rest.index("--env-var")
            env_var = rest[i + 1]
            rest = rest[:i] + rest[i + 2:]
        rest = [a for a in rest if a != "--default"]
        display = rest[0] if rest else None
        get_conn()
        account_id = add_account(email, display, make_default, env_var)
        var = env_var or account_env_var(email)
        print(f"[db] added account id={account_id} email={email}")
        print(f"[db] set ${var} in ~/.zsh_secrets to that account's Gmail app password")
        return 0
    if cmd == "set-account-env-var":
        if len(sys.argv) < 4:
            print("usage: python3 db.py set-account-env-var <account_id> <ENV_VAR_NAME>", file=sys.stderr)
            return 2
        get_conn()
        set_account_password_env_var(int(sys.argv[2]), sys.argv[3])
        print(f"[db] account {sys.argv[2]} now reads ${sys.argv[3]}")
        return 0
    if cmd == "list-accounts":
        get_conn()
        for a in list_accounts():
            default = " (default)" if a["is_default"] else ""
            var = a["password_env_var"] or account_env_var(a["email"])
            print(f"  id={a['id']}  {a['email']}{default}  env_var=${var}  last_synced_at={a['last_synced_at']}")
        return 0
    if cmd == "migrate":
        get_conn()
        print(f"[db] migrations up to date at {DB_PATH}")
        return 0
    if cmd == "status":
        conn = get_conn()
        rows = list(conn.execute("SELECT version, name, applied_at FROM schema_migrations ORDER BY version"))
        print(f"[db] {DB_PATH}")
        for r in rows:
            print(f"  {r['version']:03d}  {r['name']:<30}  {r['applied_at']}")
        msg_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        print(f"[db] messages: {msg_count:,}  jobs: {job_count:,}")
        return 0
    if cmd == "reset":
        if DB_PATH.exists():
            DB_PATH.unlink()
            for suffix in ("-wal", "-shm"):
                p = Path(str(DB_PATH) + suffix)
                if p.exists():
                    p.unlink()
        get_conn()
        print(f"[db] reset complete at {DB_PATH}")
        return 0
    print(f"[db] unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
