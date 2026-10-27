"""Streams the big CSV one row at a time (bounded memory) and validates every row."""
from __future__ import annotations

import csv
import logging
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Union

from importer.settings import ConfigError, load_settings
from importer.transform import EXPECTED_COLUMNS, Record, RowRejected, transform_row

log = logging.getLogger(__name__)
csv.field_size_limit(2**31 - 1)          # article bodies can be hundreds of KB


class CsvFormatError(Exception):
    """The file itself is wrong (missing file or missing columns)."""


@dataclass(slots=True)
class Rejection:
    line: int
    url: str
    reason: str


@dataclass
class ReadStats:
    rows_read: int = 0
    valid: int = 0
    rejected: int = 0
    duplicates_in_file: int = 0
    reject_reasons: Counter = field(default_factory=Counter)
    fixes: Counter = field(default_factory=Counter)


def iter_rows(path: Path, stats: ReadStats) -> Iterator[Union[Record, Rejection]]:
    """Yield a Record for each good row and a Rejection for each bad one.

    Duplicate URLs inside the file are rejected after the first copy. Only the
    set of URLs is kept in memory (about 100,000 short strings), not the rows.
    """
    if not path.is_file():
        raise CsvFormatError(f"CSV file not found: {path.resolve()}")
    seen: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in EXPECTED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise CsvFormatError(f"CSV is missing columns: {missing}")
        for row in reader:
            stats.rows_read += 1
            line = reader.line_num
            if None in row:                        # more fields than headers
                reason = "wrong number of columns"
            elif any(v is None for v in row.values()):   # fewer fields than headers
                reason = "wrong number of columns"
            else:
                try:
                    rec = transform_row(row)
                except RowRejected as exc:
                    reason = str(exc)
                else:
                    if rec.url in seen:
                        stats.duplicates_in_file += 1
                        reason = "duplicate url in file"
                    else:
                        seen.add(rec.url)
                        stats.valid += 1
                        for fix in rec.fixes:
                            stats.fixes[fix] += 1
                        yield rec
                        continue
            stats.rejected += 1
            stats.reject_reasons[reason] += 1
            yield Rejection(line, (row.get("url") or "")[:200], reason)


def main() -> int:
    """`python -m importer.csv_reader` : check the whole CSV, write nothing to the database."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        settings = load_settings()
        stats = ReadStats()
        for item in iter_rows(settings.csv_file_path, stats):
            if isinstance(item, Rejection) and stats.rejected <= 5:
                print(f"  rejected line {item.line}: {item.reason} | {item.url}")
            if stats.rows_read % 20000 == 0 and stats.rows_read:
                log.info("checked %d rows...", stats.rows_read)
    except (ConfigError, CsvFormatError) as exc:
        print("PROBLEM:", exc)
        return 1
    print(f"\nRows read: {stats.rows_read}")
    print(f"Valid: {stats.valid} | Rejected: {stats.rejected} "
          f"(duplicate URLs in file: {stats.duplicates_in_file})")
    print("Reject reasons:", dict(stats.reject_reasons) or "none")
    print("Cleaned (kept, but fixed):", dict(stats.fixes) or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
    