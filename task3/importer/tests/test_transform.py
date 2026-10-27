"""Tests for row cleaning (no database needed)."""
import datetime as dt

import pytest

from importer.transform import (RowRejected, parse_date, parse_tags, parse_time,
                                transform_row)


def make_row(**over):
    row = {"source": "a.com", "url": "https://a.com/x", "title": "Title", "author": "Bob",
           "date": "2026-10-24", "time": "14:15:00 +0000", "description": "", "tags": "a, b",
           "language": "", "body": "one two three", "word_count": "3", "method": "http"}
    row.update(over)
    return row


def test_good_row_is_cleaned():
    rec = transform_row(make_row())
    assert rec.published_date == dt.date(2026, 10, 24)
    assert rec.published_time == "14:15:00+00:00"
    assert rec.tags == ["a", "b"]
    assert rec.description is None and rec.language is None
    assert rec.word_count == 3 and rec.fixes == []


@pytest.mark.parametrize("field", ["url", "title", "body", "source"])
def test_missing_required_field_is_rejected(field):
    with pytest.raises(RowRejected):
        transform_row(make_row(**{field: "  "}))


def test_bad_url_scheme_is_rejected():
    with pytest.raises(RowRejected):
        transform_row(make_row(url="ftp://a.com/x"))


def test_too_long_source_is_rejected():
    with pytest.raises(RowRejected):
        transform_row(make_row(source="a" * 101))


def test_nul_characters_are_removed():
    assert "\x00" not in transform_row(make_row(body="hello\x00 world")).body


def test_invalid_date_and_time_become_null_but_row_is_kept():
    rec = transform_row(make_row(date="2026-13-45", time="25:99"))
    assert rec.published_date is None and rec.published_time is None
    assert "invalid date set to NULL" in rec.fixes


def test_word_count_is_recalculated_when_invalid():
    for bad in ("abc", "-4", ""):
        rec = transform_row(make_row(word_count=bad, body="a b c d"))
        assert rec.word_count == 4


def test_time_without_offset_is_utc_and_reported():
    rec = transform_row(make_row(time="06:00:00"))
    assert rec.published_time == "06:00:00+00:00"
    assert "time without offset treated as UTC" in rec.fixes


@pytest.mark.parametrize("raw,expected", [
    ("14:15:00 +0000", "14:15:00+00:00"), ("09:30:00 -0500", "09:30:00-05:00"),
    ("09:30", "09:30:00+00:00"), ("09:30:00Z", "09:30:00+00:00"),
    ("", None), ("noon", None), ("24:00:00", None)])
def test_parse_time(raw, expected):
    assert parse_time(raw) == expected


def test_parse_date_and_tags():
    assert parse_date("2026-10-24") == dt.date(2026, 10, 24)
    assert parse_date("") is None and parse_date("nope") is None
    assert parse_tags(" a, b ,,a,c") == ["a", "b", "c"]
    assert parse_tags("") == []
    