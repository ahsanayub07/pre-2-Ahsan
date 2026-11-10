"""Read-only access to the articles. Nothing in this project writes to the database."""
import csv
from collections import namedtuple

import config
from text_prep import domain_from_url

Article = namedtuple("Article", "id url domain title lead")


def get_readonly_connection(settings=None):
    """PostgreSQL connection that cannot write (same pattern as the validation stage).

    readonly=True makes any INSERT/UPDATE/DELETE/DDL fail; REPEATABLE READ gives every query
    of one run the same snapshot. The password is never printed.
    """
    import psycopg2                              # imported here so tests run without a server
    s = settings or config.load_db_settings()
    conn = psycopg2.connect(host=s.host, port=s.port, dbname=s.dbname, user=s.user,
                            password=s.password, connect_timeout=s.connect_timeout)
    conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
    return conn


def chunked(items, size):
    """Yield consecutive lists of at most `size` items."""
    if size < 1:
        raise ValueError("size must be at least 1")
    for i in range(0, len(items), size):
        yield items[i:i + size]


def load_ml_ready_ids(path=None):
    """Sorted article ids from data_ml_ready.csv (reads only the 'id' column).

    Raises if the file or the column is missing, or an id appears twice.
    """
    path = path or config.ML_READY_CSV
    try:
        f = open(path, newline="", encoding="utf-8-sig")
    except FileNotFoundError:
        raise FileNotFoundError(f"{path} not found. Run validate.py --export-ml-ready first, "
                                "or set ML_READY_CSV in .env.") from None
    csv.field_size_limit(2 ** 31 - 1)            # article bodies can be very long
    with f:
        reader = csv.DictReader(f)
        if "id" not in (reader.fieldnames or []):
            raise ValueError(f"{path} has no 'id' column (found {reader.fieldnames})")
        ids = [int(row["id"]) for row in reader]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path} contains duplicate ids")
    return sorted(ids)


def fetch_articles(conn, ids, lead_chars=None, batch=None):
    """Yield Article rows for `ids`, in id order, a batch at a time.

    Only the first `lead_chars` characters of each body are read (LEFT(body, n) runs inside
    PostgreSQL), so a 700 KB article never travels to Python. Ids missing from the table are
    simply not returned; use table_counts to see how many.
    """
    lead_chars = lead_chars or config.LEAD_CHARS
    batch = batch or config.FETCH_BATCH
    sql = (f"SELECT id, url, title, LEFT(body, %s) FROM {config.INPUT_TABLE} "
           "WHERE id = ANY(%s) ORDER BY id")
    for part in chunked(sorted(ids), batch):
        with conn.cursor() as cur:
            cur.execute(sql, (lead_chars, part))
            for art_id, url, title, lead in cur.fetchall():
                yield Article(art_id, url, domain_from_url(url), title or "", lead or "")


def table_counts(conn, ids):
    """Row counts used to check the database against the documented figures."""
    out = {}
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM public.articles")
        out["articles"] = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM {config.INPUT_TABLE}")
        out["articles_cleaned"] = cur.fetchone()[0]
        found = 0
        for part in chunked(sorted(ids), 20_000):
            cur.execute(f"SELECT COUNT(*) FROM {config.INPUT_TABLE} WHERE id = ANY(%s)", (part,))
            found += cur.fetchone()[0]
    out["ml_ready_ids"] = len(ids)
    out["ml_ready_found_in_cleaned"] = found
    return out


def fetch_duplicate_groups(conn):
    """Groups of articles with identical body text, as found by preprocessing.

    Returns {body_hash: [(id, is_duplicate), ...]} for every group that contains at least one
    flagged later copy. Read-only. Uses the columns body_hash and is_duplicate of
    public.articles_cleaned (as documented by the preprocessing stage).
    """
    sql = (f"SELECT body_hash, id, is_duplicate FROM {config.INPUT_TABLE} "
           f"WHERE body_hash IN (SELECT body_hash FROM {config.INPUT_TABLE} "
           "WHERE is_duplicate AND body_hash IS NOT NULL) ORDER BY body_hash, id")
    groups = {}
    with conn.cursor() as cur:
        cur.execute(sql)
        for body_hash, art_id, is_dup in cur.fetchall():
            groups.setdefault(body_hash, []).append((art_id, bool(is_dup)))
    return groups


def fetch_body_peek(conn, article_id, chars=300):
    """First `chars` characters of one article's body (read-only), or None if the id is unknown."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT title, LEFT(body, %s) FROM {config.INPUT_TABLE} WHERE id = %s",
                    (chars, article_id))
        row = cur.fetchone()
    return None if row is None else {"title": row[0] or "", "body_start": row[1] or ""}
