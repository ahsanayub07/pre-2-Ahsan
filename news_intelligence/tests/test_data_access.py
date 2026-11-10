import sys
import types

import pytest

import config
import data_access


def write_csv(path, header, rows):
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")


def test_ids_sorted(tmp_path):
    p = tmp_path / "m.csv"
    write_csv(p, "id,title", ["5,a", "2,b", "9,c"])
    assert data_access.load_ml_ready_ids(p) == [2, 5, 9]


def test_ids_bom_and_huge_field(tmp_path):
    p = tmp_path / "m.csv"
    p.write_bytes(b"\xef\xbb\xbfid,body\n1," + b"x" * 300_000 + b"\n2,y\n")
    assert data_access.load_ml_ready_ids(p) == [1, 2]


def test_ids_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        data_access.load_ml_ready_ids(tmp_path / "none.csv")
    p = tmp_path / "a.csv"
    write_csv(p, "x,y", ["1,2"])
    with pytest.raises(ValueError):
        data_access.load_ml_ready_ids(p)
    q = tmp_path / "b.csv"
    write_csv(q, "id", ["1", "1"])
    with pytest.raises(ValueError):
        data_access.load_ml_ready_ids(q)


def test_chunked():
    assert list(data_access.chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]
    assert list(data_access.chunked([], 3)) == []
    with pytest.raises(ValueError):
        list(data_access.chunked([1], 0))


class FakeCursor:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def fetchall(self):
        ids = self.log[-1][1][1]
        return [(i, f"https://www.Site{i % 2}.com/a", None if i == 3 else f"T{i}", f"lead{i}")
                for i in ids]


class FakeConn:
    def __init__(self):
        self.log = []

    def cursor(self):
        return FakeCursor(self.log)


def test_fetch_batches_and_fields():
    conn = FakeConn()
    arts = list(data_access.fetch_articles(conn, [3, 1, 2, 5, 4], lead_chars=100, batch=2))
    assert [a.id for a in arts] == [1, 2, 3, 4, 5]
    assert len(conn.log) == 3                       # 5 ids in batches of 2
    assert conn.log[0][1][0] == 100                 # lead length passed to LEFT()
    assert arts[0].domain == "site1.com"
    assert arts[2].title == ""                      # NULL title becomes ''
    sql = conn.log[0][0]
    assert sql.lstrip().upper().startswith("SELECT") and "LEFT(body" in sql


def test_connection_is_readonly(monkeypatch):
    calls = {}

    class C:
        def set_session(self, **kw):
            calls["session"] = kw

    def connect(**kw):
        calls["connect"] = kw
        return C()

    monkeypatch.setitem(sys.modules, "psycopg2", types.SimpleNamespace(connect=connect))
    s = config.load_db_settings({"DB_PASSWORD": "pw", "DB_HOST": "h"})
    data_access.get_readonly_connection(s)
    assert calls["session"] == {"isolation_level": "REPEATABLE READ", "readonly": True}
    assert calls["connect"]["host"] == "h" and calls["connect"]["connect_timeout"] == 10
