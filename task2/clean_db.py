"""
Remove bot-check / captcha pages that were wrongly saved as articles.

Run ONCE, with the scraper stopped:
    python clean_db.py

1. Makes a backup copy: articles_task2_backup.db
2. Deletes junk rows from the 'articles' table (short pages containing
   phrases like "not a robot", "verify you are human", "access denied")
3. Marks those links as 'captcha' so they are not counted as done
"""
import shutil
import sqlite3

DB = "articles_task2.db"
PHRASES = [
    "not a robot", "verify you are human", "verify that you are human",
    "are you a robot", "unusual traffic", "just a moment", "pardon our interruption",
    "checking your browser", "attention required", "access denied",
    "enable javascript and cookies", "supports javascript and cookies",
    "click the box below", "captcha", "you have been blocked", "request blocked",
]

shutil.copy(DB, "articles_task2_backup.db")
print("Backup saved: articles_task2_backup.db")

db = sqlite3.connect(DB)
rows = db.execute("SELECT url, source, title, body, word_count FROM articles").fetchall()
junk = []
for url, source, title, body, wc in rows:
    text = f"{title} {body}".lower()
    if (wc or 0) < 200 and any(p in text for p in PHRASES):
        junk.append((url, source))

by_source = {}
for _, src in junk:
    by_source[src] = by_source.get(src, 0) + 1

db.executemany("DELETE FROM articles WHERE url=?", [(u,) for u, _ in junk])
db.executemany("UPDATE urls SET status='captcha' WHERE url=?", [(u,) for u, _ in junk])
db.commit()

left = db.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
print(f"Checked {len(rows)} articles, removed {len(junk)} bot-check pages.")
for src, n in sorted(by_source.items(), key=lambda x: -x[1])[:15]:
    print(f"  {n:>6}  {src}")
print(f"Real articles remaining: {left}")
