# Task 3 extension: CSV to PostgreSQL importer

Loads the articles from `articles_large.csv` (output of the Task 3 scraper) into a PostgreSQL
table. It is separate from the scraper and does not change it.

Features: `.env` configuration, validation and cleaning of every row, bulk loading with
`COPY`, safe re-runs, one transaction per batch with rollback, a dry-run mode, logging,
a rejects file, tests and SQL checks.

## Files

| File | Purpose |
|---|---|
| `settings.py` | Reads and validates `.env`; the password never appears in logs |
| `db.py` | Connection and schema management (`python -m importer.db`) |
| `schema.sql` | The `articles` table and indexes |
| `transform.py` | Cleans and validates one CSV row |
| `csv_reader.py` | Streams the CSV with low memory (`python -m importer.csv_reader`) |
| `import_articles.py` | The importer and its command-line options |
| `verify.sql` | SQL checks to run after the import |
| `tests/` | Automated tests (no database needed) |
| `.env.example` | Template for `.env` (the real `.env` is never committed) |

## Setup (Windows PowerShell, from the `task3` folder with the CSV)

1. Install PostgreSQL and make sure `psql --version` works.
2. Create the database and a limited user (you are asked for a password for `task3_user`):
   ```
   psql -U postgres -h localhost -c "CREATE DATABASE task3_articles;"
   psql -U postgres -h localhost -c "CREATE ROLE task3_user LOGIN;"
   psql -U postgres -h localhost -c "\password task3_user"
   psql -U postgres -h localhost -d task3_articles -c "GRANT ALL ON SCHEMA public TO task3_user;"
   ```
3. Install the packages: `python -m pip install -r importer/requirements.txt`
4. Create `.env` **once** and put your real password in it:
   ```
   Copy-Item importer\.env.example importer\.env
   ```
   Do not run the copy again, because it overwrites your `.env`.
5. Check the connection and create the table: `python -m importer.db`

## Configuration

Values that change between computers, or are secret, are in `importer/.env`:
`APP_ENV`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_CONNECT_TIMEOUT`,
`CSV_FILE_PATH`, `BATCH_SIZE`, `LOG_LEVEL`. Fixed design choices (table name, column list,
rejects file name) are constants in the code, not in `.env`.

## Usage

```
python -m importer.csv_reader                      # check the CSV only
python -m importer.import_articles --dry-run       # validate, write nothing
python -m importer.import_articles --limit 1000    # small test import
python -m importer.import_articles                 # full import
python -m importer.import_articles --update        # also update rows whose URL exists
python -m pytest importer/tests -q                 # run the tests
psql -U task3_user -h localhost -d task3_articles -f importer/verify.sql
```

## How it works

1. `csv_reader.py` reads one row at a time (memory stays low even with 700 KB articles).
2. `transform.py` rejects bad rows (no URL, no title or body, bad URL, value too long) and
   cleans the rest: NUL characters removed, dates and times parsed, tags split into a list,
   empty values stored as NULL, `word_count` recalculated if invalid.
3. Rows are grouped into batches (`BATCH_SIZE`, or less if the text is very long).
4. Each batch is one transaction: `COPY` into a temporary table, then
   `INSERT ... ON CONFLICT (url) DO NOTHING` into `articles`.
5. If a batch fails, it is rolled back and retried in halves until the bad row is found.
   Only that row is rejected. Rejected rows are written to `importer/rejected_rows.csv`.
6. A log file is written to `importer/logs/` for every run.

## Design choices and limits

- **Duplicates:** `url` is the unique key. Titles are not unique, so they are not used. The CSV
  has no duplicate URLs. Two URLs that point to the same page (for example with tracking
  parameters) would count as two articles.
- **Re-runs:** existing URLs are skipped. `--update` replaces a row only when something changed.
- **Times:** 26,184 articles had a time without a UTC offset. They are stored as UTC, which
  is an assumption.
- **Empty columns:** `description` and `language` are empty in this CSV, so they are NULL.
- **Not covered by tests:** the PostgreSQL part is checked with SQL (`verify.sql`), not pytest.

## Results of the import on the real data

| Item | Value |
|---|---|
| Rows read from the CSV | 100,027 |
| Valid rows | 100,026 |
| Rejected (missing title) | 1 |
| Inserted | 99,026 (+ 1,000 from the earlier test run) |
| Rejected by the database | 0 |
| Time for the full import | about 83 seconds |

## Troubleshooting

| Problem | Fix |
|---|---|
| `No module named importer.xyz` | Run commands from the `task3` folder. Check the file name with `dir importer` (no spaces) |
| `CONFIG PROBLEM: DB_PASSWORD is still 'change_me'` | Put the real password in `importer\.env` and save |
| `password authentication failed` | The password in `.env` is wrong for `task3_user` |
| `permission denied for schema public` | Run the `GRANT ALL ON SCHEMA public` command from Setup again |
| `no tests ran` | The test files must be in `importer\tests\` and named `test_*.py` |
| `-- More --` in psql | Press `q` |

## Security

`.env` is listed in `.gitignore` and must never be committed or pasted into chat. The app
connects as `task3_user`, not as the `postgres` administrator.
