import sqlite3
import time

GOAL = 100000
WAIT = 60


def read():
    db = sqlite3.connect("file:articles.db?mode=ro", uri=True)
    saved = db.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    waiting = db.execute("SELECT COUNT(*) FROM urls WHERE status='new'").fetchone()[0]
    db.close()
    return saved, waiting


saved1, waiting1 = read()
print("Now:", saved1, "articles saved,", waiting1, "links still waiting.")
print("Measuring speed for", WAIT, "seconds...")
time.sleep(WAIT)
saved2, waiting2 = read()
gained = saved2 - saved1
per_min = gained / (WAIT / 60)
print("After", WAIT, "s:", saved2, "saved (+" + str(gained) + "),", waiting2, "waiting.")
if per_min <= 0:
    print("No new articles in this minute. The scraper may be stopped or stuck.")
else:
    need = max(0, GOAL - saved2)
    print("Speed: about", round(per_min), "articles per minute.")
    print("To reach", GOAL, ": need", need, "more, roughly", round(need / per_min / 60, 1), "hours.")