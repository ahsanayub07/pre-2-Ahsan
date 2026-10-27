import csv
from collections import Counter

csv.field_size_limit(2**31 - 1)
FILE = "articles_large.csv"

with open(FILE, encoding="utf-8-sig", newline="") as f:
    reader = csv.reader(f)
    header = next(reader)
    print("Columns:", header)
    rows, bad, urls, longest = 0, 0, Counter(), {h: 0 for h in header}
    first = None
    for row in reader:
        rows += 1
        if len(row) != len(header):
            bad += 1
            continue
        if first is None:
            first = row
        urls[row[header.index("url")]] += 1
        for h, v in zip(header, row):
            longest[h] = max(longest[h], len(v))
print("Rows:", rows, "| wrong column count:", bad)
print("Duplicate URLs:", sum(1 for c in urls.values() if c > 1))
print("Longest value per column:", longest)
print("First row (short):", {h: v[:40] for h, v in zip(header, first)})