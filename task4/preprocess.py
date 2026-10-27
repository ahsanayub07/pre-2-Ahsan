
import re
from collections import Counter

from db import get_connection


def clean_text(value):
    """Normalize whitespace without changing the original wording."""
    if value is None:
        return None

    value = value.replace("\u00a0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def main():
    connection = get_connection()

    try:
        with connection:
            with connection.cursor() as cursor:
                # Create a separate output table using the source schema.
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS public.articles_cleaned
                    (LIKE public.articles INCLUDING DEFAULTS)
                """)

                # Add preprocessing metadata without changing source columns.
                cursor.execute("""
                    ALTER TABLE public.articles_cleaned
                    ADD COLUMN IF NOT EXISTS normalized_body_hash TEXT,
                    ADD COLUMN IF NOT EXISTS is_duplicate_body BOOLEAN
                        NOT NULL DEFAULT FALSE,
                    ADD COLUMN IF NOT EXISTS has_suspicious_encoding BOOLEAN
                        NOT NULL DEFAULT FALSE
                """)

                # Read the original data; never update or delete it.
                cursor.execute("""
                    SELECT id, url, source, title, author, published_date,
                           published_time, description, tags, language,
                           body, word_count, method, imported_at
                    FROM public.articles
                    ORDER BY id
                """)
                rows = cursor.fetchall()

                # Clean text fields and compute normalized body hashes.
                processed = []
                hash_counts = Counter()
                suspicious_count = 0

                for row in rows:
                    row = list(row)

                    # Text fields: source, title, author, description,
                    # language, body and method.
                    for index in (2, 3, 4, 7, 9, 10, 12):
                        row[index] = clean_text(row[index])

                    body = row[10]
                    body_hash = None

                    if body:
                        import hashlib

                        normalized_body = body.casefold()
                        body_hash = hashlib.md5(
                            normalized_body.encode("utf-8")
                        ).hexdigest()
                        hash_counts[body_hash] += 1

                    combined_text = " ".join(
                        value for value in (row[3], row[7], row[10])
                        if value
                    )
                    suspicious = bool(
                        re.search(r"Ã.|â€|â€™|â€œ|â€|Æ", combined_text)
                    )

                    if suspicious:
                        suspicious_count += 1

                    processed.append((row, body_hash, suspicious))

                # Prepare the cleaned table output.
                insert_sql = """
                    INSERT INTO public.articles_cleaned (
                        id, url, source, title, author, published_date,
                        published_time, description, tags, language,
                        body, word_count, method, imported_at,
                        normalized_body_hash, is_duplicate_body,
                        has_suspicious_encoding
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (id) DO NOTHING
                """

                # If the output table already has rows, refresh it safely.
                cursor.execute("TRUNCATE TABLE public.articles_cleaned")

                for row, body_hash, suspicious in processed:
                    is_duplicate = (
                        body_hash is not None
                        and hash_counts[body_hash] > 1
                    )

                    cursor.execute(
                        insert_sql,
                        tuple(row) + (
                            body_hash,
                            is_duplicate,
                            suspicious,
                        ),
                    )

                # Produce a concise quality summary.
                cursor.execute("""
                    SELECT COUNT(*),
                           COUNT(*) FILTER (
                               WHERE title IS NULL OR BTRIM(title) = ''
                           ),
                           COUNT(*) FILTER (
                               WHERE body IS NULL OR BTRIM(body) = ''
                           ),
                           COUNT(*) FILTER (WHERE is_duplicate_body),
                           COUNT(*) FILTER (WHERE has_suspicious_encoding)
                    FROM public.articles_cleaned
                """)
                total, missing_titles, missing_bodies, duplicates, suspicious = (
                    cursor.fetchone()
                )

                print("\nPreprocessing completed successfully.")
                print(f"Original rows read: {len(rows):,}")
                print(f"Cleaned rows saved: {total:,}")
                print(f"Missing titles: {missing_titles:,}")
                print(f"Missing bodies: {missing_bodies:,}")
                print(f"Rows flagged as duplicate bodies: {duplicates:,}")
                print(
                    "Rows flagged for suspicious encoding: "
                    f"{suspicious:,}"
                )
                print(
                    "\nNote: suspicious encoding is flagged for review, "
                    "not automatically repaired."
                )

    finally:
        connection.close()


if __name__ == "__main__":
    main()
