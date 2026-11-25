"""
Postgres access for the platform (SITE_NETWORK_PLAN.md §9).

  connect()   one connection (dict rows); use as a context manager, commits on success
  migrate()   applies app/migrations/NNN_*.sql in order, once each (table schema_migrations)

Plain SQL files instead of an ORM: the schema is small and the SQL stays readable. DATABASE_URL is
read at call time, so importing this module never needs a database.
"""

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from psycopg import Connection, connect as pg_connect
from psycopg.rows import dict_row

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


class DatabaseUnavailable(Exception):
    """No DATABASE_URL, or Postgres can't be reached; shown to users as 503."""


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise DatabaseUnavailable("Accounts need the database: DATABASE_URL is not set")
    return url


@contextmanager
def connect() -> Iterator[Connection]:
    try:
        conn = pg_connect(database_url(), row_factory=dict_row, connect_timeout=3)
    except DatabaseUnavailable:
        raise
    except Exception as e:  # psycopg.OperationalError and friends
        raise DatabaseUnavailable(f"Database unreachable: {e}") from e
    try:
        with conn:  # commit on success, roll back on error
            yield conn
    finally:
        conn.close()


def migrate() -> list[str]:
    """Apply pending migrations; returns the versions applied now."""
    applied_now = []
    with connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        # One migrator at a time (several API workers may start together)
        conn.execute("SELECT pg_advisory_xact_lock(7340001)")
        done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        for path in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")):
            version = path.stem
            if version in done:
                continue
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            applied_now.append(version)
    return applied_now
