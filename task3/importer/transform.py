"""Pure functions that validate and clean one CSV row (no file or database access)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

EXPECTED_COLUMNS = ["source", "url", "title", "author", "date", "time", "description",
                    "tags", "language", "body", "word_count", "method"]
MAX_LEN = {"source": 100, "language": 10, "method": 20}      # match schema.sql

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(Z|[+-]\d{2}:?\d{2})?$")


class RowRejected(Exception):
    """The row cannot be imported. The message is the reason shown in the report."""


@dataclass(slots=True)
class Record:
    url: str
    source: str
    title: str
    author: Optional[str]
    published_date: Optional[date]
    published_time: Optional[str]      # e.g. '14:15:00+00:00' (PostgreSQL TIMETZ text)
    description: Optional[str]
    tags: list[str]
    language: Optional[str]
    body: str
    word_count: int
    method: Optional[str]
    fixes: list[str] = field(default_factory=list)   # what was cleaned, for the report

    def as_copy_row(self) -> tuple:
        """Values in the same order as the COPY column list in the importer."""
        return (self.url, self.source, self.title, self.author, self.published_date,
                self.published_time, self.description, self.tags, self.language,
                self.body, self.word_count, self.method)


def clean_text(value: str | None) -> str:
    """Trim spaces and remove NUL characters (PostgreSQL cannot store them)."""
    return (value or "").replace("\x00", "").strip()


def parse_date(raw: str) -> Optional[date]:
    """'2026-10-24' -> date. Empty or invalid -> None (checked by the caller)."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_time(raw: str) -> Optional[str]:
    """'14:15:00 +0000' -> '14:15:00+00:00'. No offset is treated as UTC."""
    m = _TIME_RE.match(raw)
    if not m:
        return None
    hh, mm, ss, tz = int(m[1]), int(m[2]), int(m[3] or 0), m[4]
    if hh > 23 or mm > 59 or ss > 59:
        return None
    if not tz or tz == "Z":
        tz = "+0000"
    tz = tz.replace(":", "")
    return f"{hh:02d}:{mm:02d}:{ss:02d}{tz[:3]}:{tz[3:]}"


def parse_tags(raw: str) -> list[str]:
    """'a, b,a' -> ['a', 'b'] (trimmed, no empties, no repeats, order kept)."""
    seen: dict[str, None] = {}
    for part in raw.split(","):
        part = part.strip()
        if part:
            seen.setdefault(part, None)
    return list(seen)


def transform_row(row: dict[str, str]) -> Record:
    """Validate and clean one row. Raises RowRejected if it cannot be imported."""
    fixes: list[str] = []
    r = {k: clean_text(row.get(k)) for k in EXPECTED_COLUMNS}

    if not r["url"]:
        raise RowRejected("missing url")
    if not r["url"].lower().startswith(("http://", "https://")):
        raise RowRejected("url does not start with http(s)")
    for name in ("source", "title", "body"):
        if not r[name]:
            raise RowRejected(f"missing {name}")
    for name, limit in MAX_LEN.items():
        if len(r[name]) > limit:
            raise RowRejected(f"{name} longer than {limit} characters")

    published_date = parse_date(r["date"])
    if r["date"] and published_date is None:
        fixes.append("invalid date set to NULL")
    published_time = parse_time(r["time"]) if r["time"] else None
    if r["time"] and published_time is None:
        fixes.append("invalid time set to NULL")
    elif published_time and not re.search(r"[+-]\d{2}:?\d{2}$|Z$", r["time"]):
        fixes.append("time without offset treated as UTC")

    words = len(r["body"].split())
    try:
        word_count = int(r["word_count"])
        if word_count < 0:
            raise ValueError
    except ValueError:
        word_count = words
        fixes.append("word_count recalculated from body")

    return Record(
        url=r["url"], source=r["source"], title=r["title"],
        author=r["author"] or None, published_date=published_date,
        published_time=published_time, description=r["description"] or None,
        tags=parse_tags(r["tags"]), language=r["language"] or None,
        body=r["body"], word_count=word_count, method=r["method"] or None, fixes=fixes)
