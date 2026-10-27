"""Tests for streaming CSV validation and batching (no database needed)."""
import csv

import pytest

from importer.csv_reader import CsvFormatError, ReadStats, Rejection, iter_rows
from importer.import_articles import batches
from importer.transform import EXPECTED_COLUMNS, Record


def write_csv(path, rows, header=EXPECTED_COLUMNS):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def row(url, title="T", body="one two three"):
    return ["a.com", url, title, "", "2026-10-24", "", "", "", "", body, "3", "http"]


def test_reader_counts_good_bad_and_duplicate_rows(tmp_path):
    f = tmp_path / "a.csv"
    write_csv(f, [row("https://a.com/1"), row("https://a.com/2", title=""),
                  row("https://a.com/1"), row("https://a.com/3")])
    stats = ReadStats()
    items = list(iter_rows(f, stats))
    good = [i for i in items if isinstance(i, Record)]
    bad = [i for i in items if isinstance(i, Rejection)]
    assert [r.url for r in good] == ["https://a.com/1", "https://a.com/3"]
    assert len(bad) == 2
    assert (stats.rows_read, stats.valid, stats.rejected, stats.duplicates_in_file) == (4, 2, 2, 1)


def test_wrong_column_count_is_rejected_not_crashed(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text(",".join(EXPECTED_COLUMNS) + "\na.com,https://a.com/1,short\n", encoding="utf-8")
    stats = ReadStats()
    list(iter_rows(f, stats))
    assert stats.reject_reasons["wrong number of columns"] == 1


def test_missing_file_and_missing_columns_raise(tmp_path):
    with pytest.raises(CsvFormatError):
        list(iter_rows(tmp_path / "nope.csv", ReadStats()))
    f = tmp_path / "b.csv"
    write_csv(f, [], header=["url", "title"])
    with pytest.raises(CsvFormatError):
        list(iter_rows(f, ReadStats()))


def test_huge_article_body_is_read(tmp_path):
    f = tmp_path / "big.csv"
    write_csv(f, [row("https://a.com/1", body="word " * 200_000)])
    stats = ReadStats()
    rec = next(iter_rows(f, stats))
    assert rec.word_count == 3 and len(rec.body) > 900_000      # word_count comes from the CSV


def test_batches_split_by_count_and_by_size():
    def rec(n, size=5):
        return Record(url=f"https://a.com/{n}", source="a", title="t", author=None,
                      published_date=None, published_time=None, description=None, tags=[],
                      language=None, body="x" * size, word_count=1, method=None)
    sizes = [len(b) for b in batches((rec(i) for i in range(7)), 3)]
    assert sizes == [3, 3, 1]
    big = [rec(i, size=30_000_000) for i in range(3)]          # 30 MB each, 50 MB cap
    assert [len(b) for b in batches(iter(big), 100)] == [2, 1]
    