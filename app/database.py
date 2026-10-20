"""SiteScout AI - SQLite database helpers."""
import sqlite3
from contextlib import contextmanager

from app import config


def get_connection() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT,
    country TEXT,
    city TEXT,
    phone TEXT,
    website TEXT,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'discovered',
    priority TEXT NOT NULL DEFAULT 'normal',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lead_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    note TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lead_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    event TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Columns added after the first release. Each is added only if missing.
EXTRA_LEAD_COLUMNS = {
    "email": "TEXT",
    "address": "TEXT",
    "source_url": "TEXT",
    "website_status": "TEXT NOT NULL DEFAULT 'unchecked'",
    "demo_url": "TEXT",
    "followup_date": "TEXT",
    "do_not_contact": "INTEGER NOT NULL DEFAULT 0",
}


def init_db() -> None:
    with db() as conn:
        conn.executescript(SCHEMA)
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(leads)")}
        for column, definition in EXTRA_LEAD_COLUMNS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE leads ADD COLUMN {column} {definition}")
