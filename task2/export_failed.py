"""Write failed_links.csv: every link that did not become an article, with the reason."""
import csv, sqlite3
db = sqlite3.connect("articles_task2.db")
rows = db.execute("SELECT source,url,status,COALESCE(reason,'') FROM urls "
                  "WHERE status!='done' ORDER BY source").fetchall()
with open("failed_links.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f); w.writerow(["source", "url", "status", "reason"]); w.writerows(rows)
print(f"Saved {len(rows)} links to failed_links.csv")
for st, n in db.execute("SELECT status,COUNT(*) FROM urls GROUP BY status ORDER BY 2 DESC"):
    print(f"  {n:7d}  {st}")
print("Note: status 'new' = never tried (the 10,000 target was reached first).")
