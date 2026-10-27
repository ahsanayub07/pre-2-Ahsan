# Task 1: News web scraper (1,000 valid articles)

Same scraper as Task 3, smaller scale: **24 news sites, 1,000+ valid articles**
(at least 150 words each, no bot-check pages).

Each article has: source, url, title, author, date, time, description, tags, language, body, word count.

## How it works
1. **Discover links** from robots.txt, sitemaps and RSS feeds.
2. **Fast download** with 16 threads and a polite 1.5 s delay per site.
3. **Chrome phase** (5 tabs, human-like scrolling and pauses) for JavaScript pages.
4. **Captchas** are never bypassed: you solve them in the tab (60 s) or the page is skipped.
5. Everything is saved in SQLite, so Ctrl+C is safe and re-running continues.

## Run
    pip install -r requirements.txt
    python -m playwright install chromium
    python scraper_task1.py --test      # quick test
    python scraper_task1.py             # full run
    python scraper_task1.py --chrome    # Chrome tabs for dynamic pages
    python export_failed.py             # failed_links.csv
    python clean_db.py                  # remove bot-check pages
    python make_sample.py               # articles_sample.csv
