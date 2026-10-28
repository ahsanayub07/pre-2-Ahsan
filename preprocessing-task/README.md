# Task 4 — Article Data Preprocessing

## 1. Project Overview

This project cleans an article dataset stored in PostgreSQL and adds quality flags to it.

The original dataset was imported in Task 3 (`public.articles`, 100,026 records). Task 4 reads those records, repairs wrongly decoded text, tidies whitespace, fingerprints each article body to find duplicates, and flags records that look like non-articles or have other quality problems.

The original table is never changed. All results are written to a separate table, `public.articles_cleaned`. No record is deleted: problems are flagged, not removed.

## 2. Technologies Used

- Python
- PostgreSQL
- psycopg2 (database access)
- python-dotenv (local settings from `.env`)
- ftfy (repair of wrongly decoded text)
- Regular expressions
- MD5 hashing for duplicate detection

## 3. Database Details

- Database: `task3_articles`
- Source table: `public.articles`
- Output table: `public.articles_cleaned`
- Database host: `localhost`
- Source record count: 100,026

Database credentials are stored in a local `.env` file and must not be committed to GitHub.

## 4. Project Structure

```text
preprocessing-task/
├── .env                 (local only, never committed)
├── .gitignore
├── cleaning.py          text-cleaning functions (no database)
├── db.py                database connection
├── preprocess.py        main program
├── requirements.txt
├── README.md
└── test_connection.py
```

## 5. Setup Instructions

Run these commands from the repository root in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\preprocessing-task\requirements.txt
```

Create `preprocessing-task/.env` with your local database settings:

```text
DB_HOST=localhost
DB_PORT=5432
DB_NAME=task3_articles
DB_USER=task3_user
DB_PASSWORD=your_local_password
```

Replace the example password with your local PostgreSQL password. Never publish real credentials.

## 6. Test the Database Connection

```powershell
.\.venv\Scripts\python.exe .\preprocessing-task\test_connection.py
```

The test confirms that Python can connect to PostgreSQL and read the article count.

## 7. Run Preprocessing

```powershell
.\.venv\Scripts\python.exe .\preprocessing-task\preprocess.py             # full run
.\.venv\Scripts\python.exe .\preprocessing-task\preprocess.py --limit 500 # small test
.\.venv\Scripts\python.exe .\preprocessing-task\preprocess.py --dry-run   # runs everything, then rolls back
```

The program:

1. Reads records from `public.articles` in batches of 2,000 (streamed, not loaded all at once).
2. Repairs text that was decoded with the wrong encoding (for example `PokÃ©mon` becomes `Pokémon`).
3. Tidies whitespace and removes invisible characters. One-line fields (title, author, ...) become one line; article bodies keep their paragraph breaks.
4. Calculates an MD5 hash of the normalized body and marks duplicate bodies.
5. Adds quality flags (see section 8).
6. Saves the result to `public.articles_cleaned`, all in one transaction (all or nothing).
7. Prints a quality summary.

The output table is dropped and rebuilt on every run. Do not store manually maintained records in it. A full run on 100,026 records takes about 4 minutes.

## 8. Columns Added by Preprocessing

| Column | Meaning |
|---|---|
| `clean_word_count` | Word count of the cleaned body |
| `body_hash` | MD5 of the normalized body (lower case, whitespace collapsed) |
| `duplicate_group_size` | How many records share the same body hash |
| `is_duplicate` | TRUE for later copies; the copy with the lowest `id` is kept as the original |
| `encoding_repaired` | TRUE if wrongly decoded text was repaired |
| `has_suspicious_encoding` | TRUE if the text still shows wrong-encoding patterns after repair |
| `is_non_article` | TRUE for pages that are not articles (see below) |
| `author_missing` | TRUE if the source data has no author |
| `is_short` | TRUE if the cleaned body has fewer than 50 words |
| `has_html_tags` | TRUE if the body contains HTML-like tags |
| `has_boilerplate` | TRUE if the body contains cookie or newsletter notice text |

**Non-article rules.** They come from checking the URL sections of each source:

- `bleacherreport.com`: `/game/` (match pages)
- `goal.com`: whole source (team and information pages)
- `techspot.com`: `/products/`, `/trivia/`, `/downloads/`
- `sciencedaily.com`: `/terms/` and top-level `.htm` pages (topic indexes, contact, copyright, ...)

## 9. Results (run on 2026-10-28)

| Metric | Result |
|---|---:|
| Original records | 100,026 |
| Cleaned records saved | 100,026 |
| Missing titles / bodies | 0 / 0 |
| Duplicate body groups | 266 |
| Rows in duplicate body groups | 1,045 |
| Later copies flagged `is_duplicate` | 779 |
| Rows with encoding repaired | 724 |
| Rows still suspicious after repair | 9 |
| Non-article pages flagged | 2,584 |
| Missing author | 6,393 (3,827 on real articles) |
| Short text (< 50 words) | 908 (831 on real articles) |
| HTML-like tags in body | 708 |
| Cookie or newsletter text | 39 |

The 9 rows that are still suspicious contain a lost character (the replacement character `�`, or text like `â€` whose last byte is missing in the source). The original text cannot be recovered from the data. Two of them appear to be articles that discuss encoding problems and contain such characters on purpose.

These figures describe this run. They may change if the source data or the rules change.

## 10. Important Limitations

- Duplicate body text does not necessarily mean two complete articles are identical. Duplicates are flagged, not deleted.
- Encoding repair only runs on text that shows a typical wrong-encoding pattern. Text whose original bytes were lost in the source (for example `â€` without its last character) cannot be restored and stays flagged.
- The non-article rules cover four sources that were checked by hand. Other sources may also contain non-article pages that are not flagged.
- Missing authors are not guessed from the body text. Many missing authors come from non-article pages or from sources that do not print a byline.
- `is_short`, `has_html_tags` and `has_boilerplate` are keyword and pattern checks. They are hints for review, not proof of a problem; a flagged row may be correct (for example an article that shows HTML code).
- MD5 hashes are used as practical text fingerprints, not for security.
- Cleaning is not a complete linguistic or semantic process. The results do not prove that all text is free of errors.

## 11. Verification

Source and output row counts:

```sql
SELECT
    (SELECT COUNT(*) FROM public.articles)         AS original_rows,
    (SELECT COUNT(*) FROM public.articles_cleaned) AS cleaned_rows;
```

Both tables contain 100,026 rows.

Duplicate groups:

```sql
SELECT COUNT(*) AS groups, SUM(n) AS rows_in_groups
FROM (SELECT COUNT(*) AS n FROM public.articles_cleaned
      WHERE body_hash IS NOT NULL GROUP BY body_hash HAVING COUNT(*) > 1) g;
```

Before/after check of repaired titles:

```sql
SELECT c.source, a.title AS before_repair, c.title AS after_repair
FROM public.articles_cleaned c JOIN public.articles a USING (id)
WHERE c.encoding_repaired AND a.title <> c.title LIMIT 10;
```

A `--dry-run` was run before the real run; both produced identical counts.

## 12. Data Safety

- The source table `public.articles` is only read, never modified.
- The whole run is one database transaction: if anything fails, the previous output table stays unchanged.
- `.env` holds the database password and is excluded from Git. Do not publish it.
- Records are flagged, never deleted.
