"""Optional: runs only when NI_TEST_DB_* variables point at a throwaway PostgreSQL that holds
SYNTHETIC rows in public.articles and public.articles_cleaned. Skipped otherwise."""
import os

import pytest

import config
import data_access

pytestmark = pytest.mark.skipif(not os.getenv("NI_TEST_DB_NAME"), reason="no test database set")


@pytest.fixture
def conn():
    s = config.load_db_settings({
        "DB_HOST": os.environ["NI_TEST_DB_HOST"], "DB_PORT": os.environ["NI_TEST_DB_PORT"],
        "DB_NAME": os.environ["NI_TEST_DB_NAME"], "DB_USER": os.environ["NI_TEST_DB_USER"],
        "DB_PASSWORD": os.environ["NI_TEST_DB_PASSWORD"]})
    c = data_access.get_readonly_connection(s)
    yield c
    c.close()


def test_fetch_lead_is_truncated(conn):
    arts = list(data_access.fetch_articles(conn, [1, 2, 3], lead_chars=50))
    assert [a.id for a in arts] == [1, 2, 3]
    assert all(len(a.lead) == 50 for a in arts)
    assert arts[0].domain == "site1.com"


def test_missing_ids_not_returned(conn):
    assert [a.id for a in data_access.fetch_articles(conn, [2, 999])] == [2]


def test_counts(conn):
    c = data_access.table_counts(conn, [1, 2, 999])
    assert c["articles"] == c["articles_cleaned"] == 10
    assert (c["ml_ready_ids"], c["ml_ready_found_in_cleaned"]) == (3, 2)


def test_writes_fail(conn):
    import psycopg2
    with pytest.raises(psycopg2.Error):
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public.articles_cleaned")
    conn.rollback()
    with pytest.raises(psycopg2.Error):
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE public.x (a int)")
