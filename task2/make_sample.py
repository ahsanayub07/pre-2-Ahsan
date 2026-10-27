"""
Create articles_sample.csv with the first 200 articles from articles_task2.csv.
The full file is too big for GitHub, so the repository gets this small sample.

    python make_sample.py
"""
import csv
import sys

SOURCE = "articles_task2.csv"
TARGET = "articles_sample.csv"
ROWS = 200

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))   # article bodies can be long

with open(SOURCE, newline="", encoding="utf-8-sig") as src, \
        open(TARGET, "w", newline="", encoding="utf-8-sig") as dst:
    reader = csv.reader(src)
    writer = csv.writer(dst)
    writer.writerow(next(reader))                    # header
    count = 0
    for row in reader:
        writer.writerow(row)
        count += 1
        if count >= ROWS:
            break

print("Saved", count, "articles to", TARGET)
