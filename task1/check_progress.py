"""
Shows how many articles you have, how fast it is going, and how long until 100,000.
Safe to run while the scraper is running (it only reads).

    python check_progress.py
It waits 60 seconds between two readings to measure the speed.
"""
import sqlite3
import time

DB = "articles_task1.db"
GOAL = 100_000
WAIT = 60


def read():
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    saved = db.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    waiting = db.execute("SELECT COUNT(*) FROM urls WHERE status='new'").fetchone()[0]
    db.close()
    return saved, waiting


saved1, waiting1 = read()
print(f"Now: {saved1} articles saved, {waiting1} links still waiting.")
print(f"Measuring speed for {WAIT} seconds...")
time.sleep(WAIT)
saved2, waiting2 = read()
gained = saved2 - saved1
per_min = gained / (WAIT / 60)
print(f"After {WAIT}s: {saved2} saved (+{gained}), {waiting2} waiting.")
if per_min <= 0:
    print("No new articles in this minute. The scraper may be stopped or stuck.")
else:
    need = max(0, GOAL - saved2)
    mins = need / per_min
    print(f"Speed: about {per_min:.0f} articles per minute ({per_min*60:.0f} per hour).")
    print(f"To reach {GOAL}: need {need} more, roughly {mins/60:.1f} hours.")
