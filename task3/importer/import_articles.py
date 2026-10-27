"""Import articles from the CSV into PostgreSQL (batched COPY, safe to re-run).

Examples (run from the task3 folder):
    python -m importer.import_articles --dry-run
    python -m importer.import_articles --limit 1000
    python -m importer.import_articles
    python -m importer.import_articles --update
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

import psycopg

from importer import db
from importer.csv_reader import CsvFormatError, ReadStats, Rejection, iter_rows
from importer.settings import ConfigError, Settings, load_settings
from importer.transform import Record

log = logging.getLogger("importer")
IMPORTER_DIR = Path(__file__).parent
REJECT_FILE = IMPORTER_DIR / "rejected_rows.csv"
LOG_DIR = IMPORTER_DIR / "logs"
MAX_BATCH_BYTES = 50_000_000     # flush early if a batch of long bodies gets this big

COLUMNS = ("url", "source", "title", "author", "published_date", "published_time",
           "description", "tags", "language", "body", "word_count", "method")
COL_LIST = ", ".join(COLUMNS)
# Staging table: same columns, loaded by COPY, dropped automatically at COMMIT.
CREATE_STAGING = """
CREATE TEMP TABLE staging (
    url TEXT, source TEXT, title TEXT, author TEXT, published_date DATE,
    published_time TEXT, description TEXT, tags TEXT[], language TEXT,
    body TEXT, word_count INTEGER, method TEXT) ON COMMIT DROP"""
COPY_SQL = f"COPY staging ({COL_LIST}) FROM STDIN"
_SELECT = ("SELECT url, source, title, author, published_date, published_time::timetz, "
           "description, tags, language, body, word_count, method FROM staging")
INSERT_SKIP = f"INSERT INTO articles ({COL_LIST}) {_SELECT} ON CONFLICT (url) DO NOTHING"
_SET = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS if c != "url")
_CHANGED = ", ".join(f"articles.{c}" for c in COLUMNS if c != "url")
_NEW = ", ".join(f"EXCLUDED.{c}" for c in COLUMNS if c != "url")
INSERT_UPDATE = (f"INSERT INTO articles ({COL_LIST}) {_SELECT} ON CONFLICT (url) DO UPDATE "
                 f"SET {_SET} WHERE ({_CHANGED}) IS DISTINCT FROM ({_NEW}) "
                 "RETURNING (xmax = 0) AS inserted")


@dataclass
class ImportStats:
    rows_read: int = 0
    valid: int = 0
    rejected: int = 0
    inserted: int = 0
    updated: int = 0
    skipped_existing: int = 0     # valid rows whose URL is already in the table
    failed_rows: int = 0          # rows PostgreSQL refused (also counted in `rejected`)
    failed_batches: int = 0       # batches that failed once and were retried in halves


def setup_logging(level: str) -> Path:
    """Log to the console and to importer/logs/import_<time>.log (no secrets are logged)."""
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"import_{datetime.now():%Y%m%d_%H%M%S}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    root = logging.getLogger("importer")
    root.setLevel(level)
    root.handlers.clear()
    for handler in (logging.StreamHandler(), logging.FileHandler(path, encoding="utf-8")):
        handler.setFormatter(fmt)
        root.addHandler(handler)
    return path


def load_batch(conn: psycopg.Connection, batch: Sequence[Record], update: bool) -> tuple[int, int]:
    """Load one batch in ONE transaction. Returns (inserted, updated). Raises on failure."""
    with conn.transaction():                       # rolls back automatically on error
        with conn.cursor() as cur:
            cur.execute(CREATE_STAGING)
            with cur.copy(COPY_SQL) as copy:
                for rec in batch:
                    copy.write_row(rec.as_copy_row())
            if update:
                cur.execute(INSERT_UPDATE)
                flags = [row[0] for row in cur.fetchall()]
                return flags.count(True), flags.count(False)
            cur.execute(INSERT_SKIP)
            return cur.rowcount, 0


def load_isolating(conn: psycopg.Connection, batch: Sequence[Record], update: bool,
                   rejects, stats: "ImportStats", number: int) -> tuple[int, int]:
    """Load a batch; if it fails, split it in halves to find the bad row(s).

    Each attempt is its own transaction, so a failure never leaves partial data.
    Good rows still get imported; only the truly bad row is rejected.
    """
    try:
        return load_batch(conn, batch, update)
    except psycopg.Error as exc:
        reason = str(exc).strip().splitlines()[0]
        if len(batch) == 1:
            stats.failed_rows += 1
            stats.rejected += 1
            log.error("Row rejected by PostgreSQL (%s): %s", batch[0].url[:80], reason)
            rejects.writerow(["", batch[0].url, f"database error: {reason}"])
            return 0, 0
        stats.failed_batches += 1
        log.warning("Batch %d failed (%s). Rolled back; retrying in halves.", number, reason)
        mid = len(batch) // 2
        a = load_isolating(conn, batch[:mid], update, rejects, stats, number)
        b = load_isolating(conn, batch[mid:], update, rejects, stats, number)
        return a[0] + b[0], a[1] + b[1]


def batches(records: Iterable[Record], size: int) -> Iterable[list[Record]]:
    """Group records into lists of `size` (or fewer if the text gets very large)."""
    batch: list[Record] = []
    nbytes = 0
    for rec in records:
        batch.append(rec)
        nbytes += len(rec.body)
        if len(batch) >= size or nbytes >= MAX_BATCH_BYTES:
            yield batch
            batch, nbytes = [], 0
    if batch:
        yield batch


def existing_urls(conn: psycopg.Connection) -> set[str]:
    """All URLs already stored (used by the dry run to show what a real run would skip)."""
    if not db.table_exists(conn):
        return set()
    with conn.cursor(name="urls_cursor") as cur:   # server-side cursor: low memory
        cur.execute("SELECT url FROM articles")
        return {row[0] for row in cur}


def run_import(settings: Settings, *, dry_run: bool, update: bool,
               limit: int | None) -> tuple[ImportStats, ReadStats]:
    stats, rstats = ImportStats(), ReadStats()
    t0 = time.time()
    conn = None
    known: set[str] = set()
    try:
        try:
            conn = db.connect(settings)
        except ConnectionError as exc:
            if not dry_run:
                raise
            log.warning("Dry run without database: %s", exc)
        if conn and dry_run:
            conn.read_only = True
            known = existing_urls(conn)
            log.info("Dry run: %d URLs already in the table.", len(known))
        elif conn:
            db.apply_schema(conn)                  # make sure the table exists

        REJECT_FILE.parent.mkdir(exist_ok=True)
        with REJECT_FILE.open("w", encoding="utf-8", newline="") as rf:
            rejects = csv.writer(rf)
            rejects.writerow(["csv_line", "url", "reason"])

            def good_records() -> Iterable[Record]:
                for item in iter_rows(settings.csv_file_path, rstats):
                    if isinstance(item, Rejection):
                        rejects.writerow([item.line, item.url, item.reason])
                    else:
                        if limit is not None and rstats.valid > limit:
                            return
                        yield item

            for number, batch in enumerate(batches(good_records(), settings.batch_size), 1):
                if dry_run:
                    stats.skipped_existing += sum(r.url in known for r in batch)
                    continue
                before = stats.failed_rows
                ins, upd = load_isolating(conn, batch, update, rejects, stats, number)
                failed_now = stats.failed_rows - before
                stats.inserted += ins
                stats.updated += upd
                stats.skipped_existing += len(batch) - ins - upd - failed_now
                log.info("Batch %d: +%d new, %d updated, %d already there | total new %d | "
                         "%d rows read", number, ins, upd, len(batch) - ins - upd - failed_now,
                         stats.inserted, rstats.rows_read)
    finally:
        if conn:
            conn.close()
    stats.rows_read, stats.valid = rstats.rows_read, rstats.valid
    stats.rejected += rstats.rejected
    log.info("Finished in %.1f s", time.time() - t0)
    return stats, rstats


def print_report(stats: ImportStats, rstats: ReadStats, dry_run: bool) -> None:
    label = "DRY RUN (nothing written)" if dry_run else "IMPORT"
    print(f"\n===== {label} REPORT =====")
    print(f"Rows read from CSV : {stats.rows_read}")
    print(f"Valid rows         : {stats.valid}")
    print(f"Rejected rows      : {stats.rejected}  {dict(rstats.reject_reasons) or ''}")
    if dry_run:
        print(f"Already in table   : {stats.skipped_existing} (would be skipped)")
        print(f"Would be inserted  : {stats.valid - stats.skipped_existing}")
    else:
        print(f"Inserted           : {stats.inserted}")
        print(f"Updated            : {stats.updated}")
        print(f"Skipped (existing) : {stats.skipped_existing}")
        print(f"Rejected by database: {stats.failed_rows} rows | batches retried in halves: {stats.failed_batches}")
    print(f"Cleaned but kept   : {dict(rstats.fixes) or 'none'}")
    print(f"Rejected rows file : {REJECT_FILE}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Import the articles CSV into PostgreSQL.")
    p.add_argument("--dry-run", action="store_true", help="validate only, write nothing")
    p.add_argument("--update", action="store_true",
                   help="update rows whose URL already exists (default: skip them)")
    p.add_argument("--limit", type=int, help="only the first N valid rows (for a small test)")
    p.add_argument("--csv", type=Path, help="CSV path (default: CSV_FILE_PATH from .env)")
    p.add_argument("--batch-size", type=int, help="rows per transaction (default: BATCH_SIZE)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings = load_settings()
        overrides = {}
        if args.csv:
            overrides["csv_file_path"] = args.csv
        if args.batch_size:
            if args.batch_size < 1:
                raise ConfigError("--batch-size must be at least 1")
            overrides["batch_size"] = args.batch_size
        if overrides:
            from dataclasses import replace
            settings = replace(settings, **overrides)
        log_path = setup_logging(settings.log_level)
        log.info("Start | env=%s | %s | dry_run=%s update=%s limit=%s batch=%d",
                 settings.app_env, settings, args.dry_run, args.update, args.limit,
                 settings.batch_size)
        stats, rstats = run_import(settings, dry_run=args.dry_run, update=args.update,
                                   limit=args.limit)
    except (ConfigError, CsvFormatError, ConnectionError) as exc:
        print("PROBLEM:", exc)
        return 1
    print_report(stats, rstats, args.dry_run)
    print(f"Log file           : {log_path}")
    return 1 if stats.failed_rows else 0


if __name__ == "__main__":
    sys.exit(main())
    