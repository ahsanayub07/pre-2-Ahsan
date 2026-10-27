# Task 2: News web scraper (10,000 valid articles)

Built with **BeautifulSoup**, **RSS (feedparser)** and **Selenium**.
60 news sites, target 10,000 valid articles (at least 150 words, no bot-check pages).

Fields: source, url, title, author, date, time, description, tags, language, body, word count.

## How it works
1. **Discover** links from RSS feeds (found on the homepage and at common paths) and
   from sitemaps (robots.txt first, newest first).
2. **Fast download**: 32 threads, polite 1.5 s delay per site. BeautifulSoup reads the
   title, author, date and time (meta tags, JSON-LD, `<time>`), and the body text.
3. **Selenium**: pages that need JavaScript open in Chrome, 5 tabs at once, with
   human-like scrolling and a 4-10 s stay on each page.
4. **Captchas** are never bypassed. You solve it in the tab (60 s) or the page is skipped;
   after 3 unsolved on one site, that site is skipped.
5. Everything is stored in SQLite, so Ctrl+C is safe and re-running continues.

## Run
    pip install -r requirements.txt
    python scraper_task2.py --test
    python scraper_task2.py --chrome        # Chrome tabs first, then fast download
    python clean_db.py
    python export_failed.py                 # failed_links.csv
    python make_sample.py                   # articles_sample.csv

Selenium needs Google Chrome installed; it downloads the matching driver by itself.
Ethics: robots.txt is respected, requests are rate-limited, only public pages are read.
