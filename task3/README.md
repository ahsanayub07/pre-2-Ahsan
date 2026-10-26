# Task 3: Large-Scale News Web Scraper

A Python web scraper that collected **100,000+ news articles** from about 160 news websites, with title, author, date, time, description, tags, language, body text and word count for each article.

Assignment for the AI course at Limeox, Sargodha (topic: web scraping).

## Results

| Item | Value |
|---|---|
| Articles collected | 100,028 |
| Sources listed in `sources.txt` | 204 |
| Article links found | 335,206 |
| Links that failed | about 53,600 (see `failed_links.csv`) |
| Success rate of attempted pages | about 65% |
| Links not tried (target already reached) | 181,549 |

**Full dataset (100,027 articles, CSV):** [articles_large.csv on Google Drive](https://drive.google.com/file/d/1E-NO469ZMbRuG50Mf7dCtsam9oLDecBX/view?usp=drive_link)

## What it collects

| Field | Description |
|---|---|
| source | Website (for example bbc.com) |
| url | Link to the article |
| title | Headline |
| author | Author name, if available |
| date | Publish date |
| time | Publish time, if available |
| description | Short summary |
| tags | Topic tags, if available |
| language | Language of the article |
| body | Full article text |
| word_count | Number of words in the body |
| method | `http` or `browser` (how the page was fetched) |

## How it works

The scraper runs in three phases. Everything is stored in a SQLite database (`articles.db`), so it can be stopped with Ctrl+C and resumed at any time.

1. **Find links.** For each site in `sources.txt` it reads `robots.txt`, RSS feeds and sitemap files (newest first) and keeps links that look like articles.
2. **Fast download.** Many threads download pages over plain HTTP, with a polite delay per site. The article text and metadata are extracted with `trafilatura`.
3. **Chrome for dynamic pages.** Pages that need JavaScript are opened in a visible Chrome window with Playwright, 5 tabs at a time. Each tab scrolls like a reader and stays on the page for a few seconds.

### Captchas and blocked sites

- The scraper does **not** solve or bypass captchas.
- When a real captcha page appears in Chrome, the script waits so a **person can solve it**. If it is not solved, the page is skipped.
- After 3 unsolved captchas on one site, that site is skipped for the run.
- A site that keeps returning bot-check pages in the fast phase is skipped after 15 tries.
- Pages disallowed by `robots.txt` are skipped.
- If the internet connection drops, the scraper pauses and continues when it is back.

## Setup

```
pip install -r requirements.txt
playwright install chromium
```

## Usage

```
python scraper_large.py                       # run / resume (fast download)
python scraper_large.py --test                # tiny test: 3 sources, 20 articles each
python scraper_large.py --chrome              # open Chrome tabs first (200 pages)
python scraper_large.py --rediscover --retry  # find more links + retry failed pages
```

Helper scripts:

```
python check_progress.py   # articles saved, speed, hours left
python clean_db.py         # remove bot-check pages saved by mistake (makes a backup)
python export_failed.py    # write failed_links.csv with the reason for each link
python make_sample.py      # write articles_sample.csv with the first 200 articles
```

## Files

| File | Purpose |
|---|---|
| `scraper_large.py` | The main scraper |
| `sources.txt` | List of news websites (one per line) |
| `clean_db.py` | Removes bot-check pages from the database |
| `export_failed.py` | Creates `failed_links.csv` |
| `check_progress.py` | Progress and speed check |
| `make_sample.py` | Creates a small sample CSV |
| `articles_sample.csv` | First 200 articles (sample of the data) |
| `failed_links.csv` | Links that did not become an article, with reasons |
| `requirements.txt` | Python packages |

The full dataset (`articles_large.csv`, about 100,000 rows) and the database (`articles.db`) are not stored in this repository because of GitHub's file size limit. The full CSV is available from the Google Drive link in the Results section above.

## Limitations

- Paywalled sites (Bloomberg, FT, WSJ and similar) usually return only a short teaser, not the full article.
- Some sites block automated access or hide their sitemaps and returned no links.
- Some collected pages are archive or tag pages rather than news stories.
- The scraper stopped when it reached the 100,000 target, so about 181,000 links were never tried.

## Ethical scraping

- Public RSS feeds and sitemaps are used to find links.
- `robots.txt` is respected.
- There is a delay between requests to the same site.
- Captchas are never bypassed.
- The data was collected for learning only and should not be republished.
