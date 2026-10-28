"""Task 4: preprocess the Task 3 articles (PostgreSQL -> PostgreSQL).

Reads public.articles (never changes it) and rebuilds public.articles_cleaned.

    python preprocess.py              # full run
    python preprocess.py --limit 500  # small test
    python preprocess.py --dry-run    # do everything, then roll back (writes nothing)
"""
import argparse
import logging
import os
import time

from psycopg2.extras import execute_values

from cleaning import (body_fingerprint, clean_body, clean_line, count_words,
                      fix_encoding, has_suspicious_encoding)
from db import get_connection

log = logging.getLogger("preprocess")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "2000"))

CREATE_SQL = """
DROP TABLE IF EXISTS public.articles_cleaned;
CREATE TABLE public.articles_cleaned (
    id                      BIGINT PRIMARY KEY,
    url                     TEXT NOT NULL UNIQUE,
    source                  VARCHAR(100) NOT NULL,
    title                   TEXT NOT NULL,
    author                  TEXT,
    published_date          DATE,
    published_time          TIMETZ,
    description             TEXT,
    tags                    TEXT[] NOT NULL DEFAULT '{}',
    language                VARCHAR(10),
    body                    TEXT NOT NULL,
    word_count              INTEGER NOT NULL,
    method                  VARCHAR(20),
    imported_at             TIMESTAMPTZ,
    -- added by preprocessing
    clean_word_count        INTEGER NOT NULL,
    body_hash               TEXT,
    duplicate_group_size    INTEGER NOT NULL DEFAULT 1,
    is_duplicate            BOOLEAN NOT NULL DEFAULT FALSE,   -- later copy of a duplicate body
    encoding_repaired       BOOLEAN NOT NULL DEFAULT FALSE,   -- wrong-encoding text was fixed
    has_suspicious_encoding BOOLEAN NOT NULL DEFAULT FALSE,   -- still looks broken after repair
    is_non_article          BOOLEAN NOT NULL DEFAULT FALSE,   -- game / team / product / index page
    author_missing          BOOLEAN NOT NULL DEFAULT FALSE,   -- no author in the source data
    is_short                BOOLEAN NOT NULL DEFAULT FALSE,   -- fewer than 50 words
    has_html_tags           BOOLEAN NOT NULL DEFAULT FALSE,   -- body contains HTML-like tags
    has_boilerplate         BOOLEAN NOT NULL DEFAULT FALSE    -- cookie / newsletter notice text
)"""

SELECT_SQL = """
SELECT id, url, source, title, author, published_date, published_time, description,
       tags, language, body, word_count, method, imported_at
FROM public.articles ORDER BY id"""

INSERT_SQL = """
INSERT INTO public.articles_cleaned (
    id, url, source, title, author, published_date, published_time, description,
    tags, language, body, word_count, method, imported_at,
    clean_word_count, body_hash, encoding_repaired, has_suspicious_encoding) VALUES %s"""

# Mark duplicates in SQL, so Python does not have to keep every hash in memory.
# The copy with the lowest id is the one to keep; the other copies get is_duplicate = TRUE.
DUPLICATE_SQL = """
UPDATE public.articles_cleaned c
SET duplicate_group_size = g.n, is_duplicate = (g.rn > 1)
FROM (SELECT id,
             COUNT(*)     OVER (PARTITION BY body_hash)            AS n,
             ROW_NUMBER() OVER (PARTITION BY body_hash ORDER BY id) AS rn
      FROM public.articles_cleaned WHERE body_hash IS NOT NULL) g
WHERE c.id = g.id AND g.n > 1"""

# Quality flags. Nothing is deleted or changed: rows are only marked.
# Non-article rules come from checking the URL sections of each source:
#   bleacherreport.com /game/...                      match pages
#   goal.com (whole source)                           team and info pages
#   techspot.com /products/, /trivia/, /downloads/    product, trivia, download pages
#   sciencedaily.com /terms/... and top-level *.htm   topic index and info pages
FLAGS_SQL = r"""
UPDATE public.articles_cleaned SET
    author_missing  = (author IS NULL),
    is_short        = (clean_word_count < 50),
    has_html_tags   = (body ~ '<[a-zA-Z/][^>]*>'),
    has_boilerplate = (body ~* '(we use cookies|accept all cookies|cookie policy|cookie notice|subscribe to our newsletter)'),
    is_non_article  = (
           (source = 'bleacherreport.com' AND url ~ '^https?://[^/]+/game/')
        OR (source = 'techspot.com'       AND url ~ '^https?://[^/]+/(products|trivia|downloads)/')
        OR (source = 'sciencedaily.com'   AND url ~ '^https?://[^/]+/(terms/|[^/]+\.htm)')
        OR  source = 'goal.com')"""


def transform(row):
    """Clean one source row and add the new columns."""
    (rid, url, source, title, author, pub_date, pub_time, description,
     tags, language, body, word_count, method, imported_at) = row
    # 1) repair wrong-encoding text FIRST, before spaces are normalized
    title, c1 = fix_encoding(title)
    author, c2 = fix_encoding(author)
    description, c3 = fix_encoding(description)
    body, c4 = fix_encoding(body)
    repaired = c1 or c2 or c3 or c4
    # 2) tidy the text
    title, author = clean_line(title), clean_line(author)
    description, source = clean_line(description), clean_line(source)
    language, method = clean_line(language), clean_line(method)
    body = clean_body(body)
    return (rid, url, source, title, author or None, pub_date, pub_time, description or None,
            tags or [], language or None, body, word_count, method or None, imported_at,
            count_words(body), body_fingerprint(body), repaired,
            has_suspicious_encoding(title, description, body))


def summary(cur):
    cur.execute("""
        SELECT COUNT(*),
               COUNT(*) FILTER (WHERE title = ''),
               COUNT(*) FILTER (WHERE body = ''),
               COUNT(DISTINCT body_hash) FILTER (WHERE duplicate_group_size > 1),
               COUNT(*) FILTER (WHERE duplicate_group_size > 1),
               COUNT(*) FILTER (WHERE is_duplicate),
               COUNT(*) FILTER (WHERE has_suspicious_encoding),
               COUNT(*) FILTER (WHERE encoding_repaired)
        FROM public.articles_cleaned""")
    return cur.fetchone()


def quality_summary(cur):
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE is_non_article),
               COUNT(*) FILTER (WHERE author_missing),
               COUNT(*) FILTER (WHERE author_missing AND NOT is_non_article),
               COUNT(*) FILTER (WHERE is_short),
               COUNT(*) FILTER (WHERE is_short AND NOT is_non_article),
               COUNT(*) FILTER (WHERE has_html_tags),
               COUNT(*) FILTER (WHERE has_boilerplate)
        FROM public.articles_cleaned""")
    return cur.fetchone()


def main():
    parser = argparse.ArgumentParser(description="Preprocess the Task 3 articles.")
    parser.add_argument("--limit", type=int, help="only the first N articles (test)")
    parser.add_argument("--dry-run", action="store_true", help="roll back at the end")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    started = time.time()
    conn = get_connection()
    try:
        with conn:                                   # one transaction: all or nothing
            with conn.cursor() as cur:
                cur.execute(CREATE_SQL)
                read = 0
                # Named cursor = server-side: rows are streamed, not all loaded at once.
                with conn.cursor(name="articles_reader") as src:
                    src.itersize = BATCH_SIZE
                    src.execute(SELECT_SQL)
                    while True:
                        rows = src.fetchmany(BATCH_SIZE)
                        if not rows:
                            break
                        if args.limit is not None:
                            rows = rows[:max(0, args.limit - read)]
                            if not rows:
                                break
                        execute_values(cur, INSERT_SQL, [transform(r) for r in rows],
                                       page_size=BATCH_SIZE)
                        read += len(rows)
                        log.info("processed %s rows", f"{read:,}")
                cur.execute(DUPLICATE_SQL)
                cur.execute(FLAGS_SQL)
                cur.execute("CREATE INDEX ON public.articles_cleaned (body_hash)")
                total, no_title, no_body, groups, in_groups, later, suspicious, repaired = summary(cur)
                (non_article, no_author, no_author_real, short, short_real,
                 html, boiler) = quality_summary(cur)
            if args.dry_run:
                conn.rollback()      # inside the transaction block, so nothing is committed
        print("\nPreprocessing finished" + (" (DRY RUN, rolled back)." if args.dry_run else "."))
        print(f"Original rows read          : {read:,}")
        print(f"Cleaned rows                : {total:,}")
        print(f"Missing titles / bodies     : {no_title:,} / {no_body:,}")
        print(f"Duplicate body groups       : {groups:,} ({in_groups:,} rows in those groups)")
        print(f"Later copies (is_duplicate) : {later:,}  <- the first copy of each group is kept")
        print(f"Encoding repaired           : {repaired:,} rows")
        print(f"Still suspicious (review)   : {suspicious:,}")
        print(f"Non-article pages (flagged) : {non_article:,}")
        print(f"Missing author              : {no_author:,} ({no_author_real:,} on real articles)")
        print(f"Short text (< 50 words)     : {short:,} ({short_real:,} on real articles)")
        print(f"HTML-like tags in body      : {html:,}")
        print(f"Cookie/newsletter text      : {boiler:,}")
        print(f"Time                        : {time.time() - started:.1f} s")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
    