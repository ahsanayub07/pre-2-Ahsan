"""Database connection and schema management (PostgreSQL via psycopg 3)."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import psycopg

from importer.settings import ConfigError, Settings, load_settings

log = logging.getLogger(__name__)
SCHEMA_FILE = Path(__file__).with_name("schema.sql")
TABLE = "articles"          # fixed by the design, so it is a code constant, not a .env value


def connect(settings: Settings) -> psycopg.Connection:
    """Open a connection. Errors are re-raised without the password."""
    try:
        return psycopg.connect(**settings.conninfo())
    except psycopg.OperationalError as exc:
        # The message from the server never contains the password; keep it short.
        raise ConnectionError(
            f"Cannot connect to {settings.db_user}@{settings.db_host}:"
            f"{settings.db_port}/{settings.db_name}: {str(exc).strip()}") from None


def apply_schema(conn: psycopg.Connection) -> None:
    """Create the table and indexes if they do not exist yet (one transaction)."""
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    with conn.transaction():
        conn.execute(sql)
    log.info("Schema is ready.")


def table_exists(conn: psycopg.Connection) -> bool:
    row = conn.execute("SELECT to_regclass(%s)", (f"public.{TABLE}",)).fetchone()
    return row[0] is not None


def row_count(conn: psycopg.Connection) -> int:
    # TABLE is a constant from this file, never user input.
    return conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]


def main() -> int:
    """`python -m importer.db` : test the connection and create the table."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        settings = load_settings()
        with connect(settings) as conn:
            print("Connected:", conn.execute("SELECT version()").fetchone()[0][:40], "...")
            print("Logged in as:", conn.execute("SELECT current_user").fetchone()[0])
            apply_schema(conn)
            print(f"Table '{TABLE}' exists: {table_exists(conn)} | rows: {row_count(conn)}")
    except (ConfigError, ConnectionError) as exc:
        print("PROBLEM:", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
    