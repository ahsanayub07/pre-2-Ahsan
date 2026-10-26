import csv

SOURCE = "articles_large.csv"
TARGET = "articles_sample.csv"
ROWS = 200

csv.field_size_limit(2**31 - 1)

with open(SOURCE, newline="", encoding="utf-8-sig") as src, \
        open(TARGET, "w", newline="", encoding="utf-8-sig") as dst:
    reader = csv.reader(src)
    writer = csv.writer(dst)
    writer.writerow(next(reader))
    count = 0
    for row in reader:
        writer.writerow(row)
        count += 1
        if count >= ROWS:
            break

print("Saved", count, "articles to", TARGET)