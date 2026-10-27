# Task 4 — Article Data Preprocessing

## 1. Project Overview

This project performs initial data preprocessing and quality checks on an article dataset stored in PostgreSQL.

The original dataset was imported during Task 3. Task 4 reads the original records, normalizes whitespace in selected text columns, calculates normalized body-text hashes, flags duplicate body text, and identifies potentially suspicious encoding patterns.

The original table is preserved. Processed records are stored in a separate table.

## 2. Technologies Used

- Python
- PostgreSQL
- psycopg2
- python-dotenv
- Regular expressions
- MD5 hashing for duplicate detection

## 3. Database Details

- Database: `task3_articles`
- Source table: `public.articles`
- Output table: `public.articles_cleaned`
- Database host: `localhost`
- Source record count: 100,026

Database credentials are stored in a local environment file and should not be committed to GitHub.

## 4. Project Structure

```text
task4/
├── .env
├── .gitignore
├── db.py
├── preprocess.py
├── requirements.txt
├── README.md
└── test_connection.py
```

The `.env` file contains local database settings and must remain untracked.

## 5. Setup Instructions

Run these commands from the repository root in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\task4\requirements.txt
```

Configure the required database environment variables in `task4/.env`.

Example:

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
.\.venv\Scripts\python.exe .\task4\test_connection.py
```

The test confirms that Python can connect to PostgreSQL and read the article count.

## 7. Run Preprocessing

```powershell
.\.venv\Scripts\python.exe .\task4\preprocess.py
```

The preprocessing program:

1. Reads records from `public.articles`.
2. Normalizes whitespace in selected text fields.
3. Calculates a hash of the normalized article body.
4. Flags records whose normalized body text appears more than once.
5. Flags text containing selected suspicious character patterns.
6. Saves processed records to `public.articles_cleaned`.
7. Prints a quality summary.

The program refreshes the output table each time it runs. Do not store unrelated or manually maintained records in that table.

## 8. Initial Results

| Metric | Result |
|---|---:|
| Original records | 100,026 |
| Cleaned records saved | 100,026 |
| Missing titles | 0 |
| Missing bodies | 0 |
| Duplicate body groups | 266 |
| Rows in duplicate body groups | 1,045 |
| Rows flagged for suspicious encoding | 195 |

These figures describe the initial run. Results may change if the source data or preprocessing rules change.

## 9. Important Limitations

- Duplicate body text does not necessarily mean that two complete articles are identical.
- Duplicate records are flagged, not deleted.
- Suspicious encoding patterns are flagged for review; the program does not automatically repair encoding.
- Whitespace normalization is not a complete linguistic or semantic cleaning process.
- MD5 hashes are used as practical text fingerprints, not for security.
- The initial results do not prove that all text is correctly encoded or free of errors.

## 10. Verification

The source and output tables were checked using:

```sql
SELECT
    (SELECT COUNT(*) FROM public.articles) AS original_rows,
    (SELECT COUNT(*) FROM public.articles_cleaned) AS cleaned_rows;
```

Both tables contained 100,026 rows at verification time.

Duplicate groups were checked using the normalized body hash and a `GROUP BY` query.

## 11. Data Safety

The source table `public.articles` is not
