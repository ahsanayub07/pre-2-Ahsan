import csv
import sqlite3
import sys

DB_FILE = "articles.db"
OUT_FILE = "failed_links.csv"

REASONS = {
    "captcha":         "Captcha / bot-check page",
    "skipped_captcha": "Captcha not solved, skipped",
    "robots":          "Disallowed by robots.txt",
    "needs_browser":   "Needs JavaScript, not loaded in Chrome yet",
    "short":           "Page too short to be an article",
    "error":           "Download error (timeout, 404, connection)",
    "failed":          "Opened in Chrome but no article text found",
    "new":             "Not tried yet (stopped at 100,000 target)",
}

try:
    db = sqlite3.connect("file:" + DB_FILE + "?mode=ro", uri=True)
    rows = db.execute(
        "SELECT source, url, status FROM urls "
        "WHERE status != 'done' ORDER BY source, status").fetchall()
except sqlite3.Error as e:
    sys.exit("Could not read " + DB_FILE + ": " + str(e))

with open(OUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["source", "url", "status", "reason"])
    for source, url, status in rows:
        w.writerow([source, url, status, REASONS.get(status, status)])

print("Saved", len(rows), "failed links to", OUT_FILE)
print("")
print("Summary by reason:")
summary = {}
for _, _, status in rows:
    summary[status] = summary.get(status, 0) + 1
for status, n in sorted(summary.items(), key=lambda x: -x[1]):
    print(" ", n, "-", REASONS.get(status, status))

done = db.execute("SELECT COUNT(*) FROM urls WHERE status='done'").fetchone()[0]
print("")
print("Successful:", done, "  Not successful:", len(rows))