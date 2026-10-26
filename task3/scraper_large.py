"""
LARGE-SCALE NEWS SCRAPER  (100 sources -> up to 100,000 articles)

How it works (3 phases, resumable):
  Phase 1  DISCOVER : for every site in sources.txt, read robots.txt, then find
                      article links from RSS feeds and sitemaps.
  Phase 2  FAST     : download pages with plain HTTP (many threads, polite
                      per-site delay) and extract title/author/date/time/body.
  Phase 3  BROWSER  : pages that need JavaScript (empty result) are opened in
                      visible Chrome, 5 tabs at a time, with natural scrolling
                      and a short stay on each page. If a captcha appears you
                      solve it yourself in the tab; if you don't, the page is
                      skipped. Nothing here solves or bypasses captchas.

Everything is stored in SQLite (articles.db), so you can stop with Ctrl+C and
run again: it continues where it stopped. Export to CSV is automatic.

Install:
    pip install requests trafilatura feedparser playwright
    playwright install chromium
Files needed in the same folder:  sources.txt  (one website per line)
Run:
    python scraper_large.py            (full run)
    python scraper_large.py --test     (tiny test: 3 sources, 20 articles each)
    python scraper_large.py --rediscover --retry   (find MORE links + retry wrong captcha flags)
    python scraper_large.py --chrome               (open Chrome tabs FIRST for 200 pages, then the fast phase)
    python scraper_large.py --chrome --chrome-pages 500
"""

import csv
import gzip
import html as htmllib
import json
import random
import re
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import requests
import trafilatura
from trafilatura import feeds as tf_feeds
from trafilatura import sitemaps as tf_sitemaps

# ------------------------------ SETTINGS -------------------------------------
TARGET_TOTAL = 100_000        # stop when this many articles are saved
MAX_PER_SOURCE = 3_000        # cap per website (100 sites x 1000+ = 100k)
DISCOVER_THREADS = 20
DISCOVER_TIMEOUT = 240        # max seconds to look for links on one site
FETCH_THREADS = 32
PER_SITE_DELAY = 1.5          # seconds between requests to the SAME site
REQUEST_TIMEOUT = 20
MIN_WORDS = 40                # fewer words = not a real article
RESPECT_ROBOTS = True         # keep True: skip pages the site disallows
TABS_AT_ONCE = 5
BROWSER_PAGES_LIMIT = 2_000   # max pages to open in Chrome per run
DWELL_SECONDS = (4, 10)       # random stay on a page (min, max)
CAPTCHA_WAIT_SECONDS = 60     # how long to wait for YOU to solve a captcha
CAPTCHA_GIVE_UP_AFTER = 3     # after 3 unsolved captchas on a site, skip its other pages
MAX_SITEMAPS_PER_SITE = 80    # how many sitemap files to read per site
DB_FILE = "articles.db"
CSV_FILE = "articles_large.csv"
SOURCES_FILE = "sources.txt"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 student-research")

STRONG_CAPTCHA_MARKERS = [
    "just a moment...", "verify you are human", "verify that you are human",
    "are you a robot", "not a robot", "click the box below",
    "unusual traffic", "px-captcha", "cf-challenge", "pardon our interruption",
    "checking your browser", "attention required", "access denied",
    "enable javascript and cookies", "supports javascript and cookies",
]
# normal pages often contain a recaptcha script (comment/login forms), so
# these only count when the page has almost no text at all
WEAK_CAPTCHA_MARKERS = ["g-recaptcha", "hcaptcha", "captcha"]
BLOCK_SITE_AFTER = 15         # stop hitting a site that keeps returning bot checks

TEST_MODE = "--test" in sys.argv
if TEST_MODE:
    TARGET_TOTAL, MAX_PER_SOURCE, BROWSER_PAGES_LIMIT = 60, 20, 10

# ------------------------------- DATABASE ------------------------------------
db = sqlite3.connect(DB_FILE, check_same_thread=False)
db_lock = threading.Lock()
db.executescript("""
CREATE TABLE IF NOT EXISTS urls (
    url TEXT PRIMARY KEY, source TEXT, status TEXT DEFAULT 'new');
CREATE TABLE IF NOT EXISTS articles (
    url TEXT PRIMARY KEY, source TEXT, title TEXT, author TEXT, date TEXT,
    time TEXT, description TEXT, tags TEXT, language TEXT, body TEXT,
    word_count INTEGER, method TEXT);
""")
db.commit()


def db_exec(sql, args=()):
    with db_lock:
        db.execute(sql, args)
        db.commit()


def db_query(sql, args=()):
    with db_lock:
        return db.execute(sql, args).fetchall()


def article_count():
    return db_query("SELECT COUNT(*) FROM articles")[0][0]


# ------------------------------- HELPERS -------------------------------------
_robots, _robots_lock = {}, threading.Lock()
_last_hit, _hit_lock = {}, threading.Lock()


def allowed_by_robots(url):
    if not RESPECT_ROBOTS:
        return True
    host = urlparse(url)
    base = f"{host.scheme}://{host.netloc}"
    with _robots_lock:
        rp = _robots.get(base)
    if rp is None:
        rp = RobotFileParser()
        try:
            r = requests.get(base + "/robots.txt", headers={"User-Agent": UA},
                             timeout=10)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            rp.parse([])
        with _robots_lock:
            _robots[base] = rp
    return rp.can_fetch(UA, url)


def wait_turn(url):
    """Polite per-site delay, safe across threads."""
    host = urlparse(url).netloc
    with _hit_lock:
        now = time.time()
        ready = max(now, _last_hit.get(host, 0) + PER_SITE_DELAY)
        _last_hit[host] = ready
    delay = ready - now
    if delay > 0:
        time.sleep(delay)


def captcha_kind(html, words):
    """'strong' = a real bot-check page, 'weak' = near-empty page with a
    captcha script, None = normal page."""
    if words >= 150:
        return None
    low = html.lower()
    if any(m in low for m in STRONG_CAPTCHA_MARKERS):
        return "strong"
    if words < 20 and any(m in low for m in WEAK_CAPTCHA_MARKERS):
        return "weak"
    return None


def looks_like_captcha(html, words):
    return captcha_kind(html, words) is not None


def looks_like_article(url):
    path = urlparse(url).path.lower()
    if any(x in path for x in ("/tag/", "/tags/", "/category/", "/author/",
                               "/video", "/gallery", "/live/", "/search")):
        return False
    last = path.rstrip("/").split("/")[-1]
    return (path.count("/") >= 2 and ("-" in last and len(last) > 15)) or \
        path.endswith((".html", ".ece", ".htm", ".php"))


def _read_xml(url):
    wait_turn(url)
    r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
    r.raise_for_status()
    data = r.content
    if url.endswith(".gz") or data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data.decode("utf-8", errors="ignore")


def _locs(xml):
    out = []
    for m in re.findall(r"<loc>\s*(.*?)\s*</loc>", xml, re.S | re.I):
        m = re.sub(r"^<!\[CDATA\[|\]\]>$", "", m.strip())
        out.append(htmllib.unescape(m))
    return out


def crawl_sitemaps(home, add, is_full):
    """Read robots.txt + sitemap indexes (newest first) and add article URLs."""
    p = urlparse(home)
    base = f"{p.scheme}://{p.netloc}"
    queue = []
    try:
        r = requests.get(base + "/robots.txt", headers={"User-Agent": UA}, timeout=10)
        for line in r.text.splitlines():
            if line.lower().startswith("sitemap:"):
                queue.append(line.split(":", 1)[1].strip())
    except Exception:
        pass
    queue += [base + x for x in ("/sitemap.xml", "/sitemap_index.xml",
                                 "/news-sitemap.xml", "/sitemap-news.xml")]
    seen, fetched = set(), 0
    while queue and fetched < MAX_SITEMAPS_PER_SITE and not is_full():
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        fetched += 1
        try:
            xml = _read_xml(sm)
        except Exception:
            continue
        if "<sitemapindex" in xml[:3000].lower():
            children = []
            for block in re.findall(r"<sitemap>(.*?)</sitemap>", xml, re.S | re.I):
                loc = _locs(block)
                lm = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", block, re.S | re.I)
                if loc and not any(x in loc[0].lower() for x in
                                   ("image", "video", "tag", "categor", "author", "topic")):
                    children.append((lm.group(1) if lm else "", loc[0]))
            children.sort(key=lambda c: c[0], reverse=True)   # newest first
            queue = [c[1] for c in children] + queue
        else:
            for u in _locs(xml):
                add(u)
                if is_full():
                    break


TIME_RE = re.compile(
    r'(?:published_time|datePublished|pubdate|publish[-_]?date|"date")["\'\s:=>]*'
    r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)',
    re.I)


def parse_page(html, url, source):
    """Return an article dict from raw HTML, or None."""
    data = trafilatura.extract(html, url=url, output_format="json",
                               with_metadata=True, include_comments=False)
    if not data:
        return None
    d = json.loads(data)
    body = d.get("text") or ""
    date, clock = d.get("date") or "", ""
    m = TIME_RE.search(html)
    if m:
        try:
            dt = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
            date, clock = dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S %z").strip()
        except ValueError:
            pass
    return {
        "url": url, "source": source, "title": d.get("title") or "",
        "author": d.get("author") or "", "date": date, "time": clock,
        "description": d.get("description") or "",
        "tags": d.get("tags") or d.get("categories") or "",
        "language": d.get("language") or "", "body": body,
        "word_count": len(body.split()),
    }


def save_article(a, method):
    db_exec("""INSERT OR REPLACE INTO articles VALUES
               (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (a["url"], a["source"], a["title"], a["author"], a["date"],
             a["time"], a["description"], a["tags"], a["language"], a["body"],
             a["word_count"], method))


def show(a, tag):
    preview = " ".join(a["body"].split())[:160]
    print(f"[{tag}] {a['source']} | {a['title'][:70]}")
    print(f"      {a['date']} {a['time']} | by {a['author'] or 'N/A'} | "
          f"{a['word_count']} words")
    if preview:
        print(f"      {preview}...")


# ---------------------------- PHASE 1: DISCOVER ------------------------------
def discover(home):
    """Find article URLs for one site (feeds first, then sitemaps)."""
    if not home.startswith("http"):
        home = "https://" + home
    source = urlparse(home).netloc.replace("www.", "")
    found, seen = [], set()

    def add(u):
        if u and u not in seen and looks_like_article(u):
            seen.add(u)
            found.append(u)

    try:
        for feed_url in (tf_feeds.find_feed_urls(home) or [])[:40]:
            for e in feedparser.parse(feed_url, request_headers={"User-Agent": UA}).entries:
                add(e.get("link"))
            if len(found) >= MAX_PER_SOURCE:
                break
    except Exception:
        pass

    try:
        crawl_sitemaps(home, add, lambda: len(found) >= MAX_PER_SOURCE)
    except Exception:
        pass

    if len(found) < 50:                      # last resort
        try:
            for u in tf_sitemaps.sitemap_search(home) or []:
                add(u)
                if len(found) >= MAX_PER_SOURCE:
                    break
        except Exception:
            pass
    return source, found[:MAX_PER_SOURCE]


def phase_discover(sites):
    print(f"\n=== PHASE 1: finding links on {len(sites)} sites ===")
    ex = ThreadPoolExecutor(max_workers=DISCOVER_THREADS)
    futures = {ex.submit(discover, s): s for s in sites}
    done_sites = 0
    try:
        for fut in as_completed(futures, timeout=DISCOVER_TIMEOUT * 3):
            done_sites += 1
            try:
                source, urls = fut.result(timeout=DISCOVER_TIMEOUT)
            except Exception:
                print(f"  [{done_sites}/{len(sites)}] {futures[fut]}: failed")
                continue
            with db_lock:
                db.executemany(
                    "INSERT OR IGNORE INTO urls(url, source) VALUES (?,?)",
                    [(u, source) for u in urls])
                db.commit()
            print(f"  [{done_sites}/{len(sites)}] {source}: {len(urls)} links")
    except Exception:
        print("  (some sites were too slow and were skipped)")
    ex.shutdown(wait=False, cancel_futures=True)
    total = db_query("SELECT COUNT(*) FROM urls")[0][0]
    print(f"  total links stored: {total}")


# ------------------------- PHASE 2: FAST HTTP FETCH --------------------------
_cap_hits, _ok_hits = {}, {}


def fetch_one(url, source):
    if article_count() >= TARGET_TOTAL:
        return None
    if _cap_hits.get(source, 0) >= BLOCK_SITE_AFTER and \
            _ok_hits.get(source, 0) < _cap_hits.get(source, 0):
        return "site_blocked"            # stays 'new'; tried again in a later run
    try:
        if not allowed_by_robots(url):
            db_exec("UPDATE urls SET status='robots' WHERE url=?", (url,))
            return "robots"
        wait_turn(url)
        r = requests.get(url, headers={"User-Agent": UA}, timeout=REQUEST_TIMEOUT)
        if r.status_code in (401, 403, 429):
            _cap_hits[source] = _cap_hits.get(source, 0) + 1
            db_exec("UPDATE urls SET status='needs_browser' WHERE url=?", (url,))
            return "blocked"
        r.raise_for_status()
        a = parse_page(r.text, url, source)
        words = a["word_count"] if a else 0
        kind = captcha_kind(r.text, words)
        if a and words >= MIN_WORDS and kind != "strong":
            save_article(a, "http")
            db_exec("UPDATE urls SET status='done' WHERE url=?", (url,))
            _ok_hits[source] = _ok_hits.get(source, 0) + 1
            show(a, "http")
            return "ok"
        if kind:
            _cap_hits[source] = _cap_hits.get(source, 0) + 1
            status = "captcha"
        elif words == 0:
            status = "needs_browser"         # empty -> probably a JavaScript page
        else:
            status = "short"                 # real but tiny page (photo, ad): skip
        db_exec("UPDATE urls SET status=? WHERE url=?", (status, url))
        return status
    except Exception:
        db_exec("UPDATE urls SET status='error' WHERE url=?", (url,))
        return "error"


def phase_fast():
    rows = db_query("SELECT url, source FROM urls WHERE status='new'")
    random.shuffle(rows)            # spreads load across all sites
    print(f"\n=== PHASE 2: fast download of {len(rows)} pages "
          f"({FETCH_THREADS} threads) ===")
    stats = {}
    with ThreadPoolExecutor(max_workers=FETCH_THREADS) as ex:
        futs = [ex.submit(fetch_one, u, s) for u, s in rows]
        for i, f in enumerate(as_completed(futs), 1):
            res = f.result()
            stats[res] = stats.get(res, 0) + 1
            if i % 200 == 0:
                print(f"  --- progress {i}/{len(rows)} | saved "
                      f"{article_count()} | {stats}")
            if article_count() >= TARGET_TOTAL:
                print("  target reached")
                break
    print(f"  phase 2 finished: {stats}")


# --------------------------- PHASE 3: VISIBLE CHROME -------------------------
def human_scroll(page):
    """Scroll down the way a reader does: varied steps and short pauses."""
    for _ in range(random.randint(4, 8)):
        page.mouse.wheel(0, random.randint(300, 800))
        time.sleep(random.uniform(0.4, 1.4))
    if random.random() < 0.4:
        page.mouse.wheel(0, -random.randint(200, 500))
        time.sleep(random.uniform(0.4, 1.0))


def wait_for_human_captcha(page):
    """Captcha shown: wait for the PERSON to solve it in the visible tab."""
    print(f"   !! captcha on {page.url[:60]} -> solve it in Chrome "
          f"(waiting up to {CAPTCHA_WAIT_SECONDS}s)")
    end = time.time() + CAPTCHA_WAIT_SECONDS
    while time.time() < end:
        time.sleep(3)
        html = page.content()
        a = parse_page(html, page.url, "")
        words = a["word_count"] if a else 0
        if a and words >= MIN_WORDS and captcha_kind(html, words) != "strong":
            return True
    return False


def phase_browser(limit=None):
    from playwright.sync_api import sync_playwright

    rows = db_query("SELECT url, source FROM urls WHERE status IN "
                    "('needs_browser','captcha') ORDER BY RANDOM() LIMIT ?",
                    (limit or BROWSER_PAGES_LIMIT,))
    if not rows:
        print("\n=== PHASE 3: nothing needs the browser ===")
        return
    print(f"\n=== PHASE 3: {len(rows)} dynamic pages in Chrome, "
          f"{TABS_AT_ONCE} tabs at a time ===")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=False)
        except Exception:
            browser = p.chromium.launch(headless=False)

        captcha_fails = {}
        for start in range(0, len(rows), TABS_AT_ONCE):
            if article_count() >= TARGET_TOTAL:
                break
            batch = []
            for url, source in rows[start:start + TABS_AT_ONCE]:
                if captcha_fails.get(source, 0) >= CAPTCHA_GIVE_UP_AFTER:
                    db_exec("UPDATE urls SET status='skipped_captcha' WHERE url=?", (url,))
                else:
                    batch.append((url, source))
            if not batch:
                continue
            ctx = browser.new_context(user_agent=UA)
            pages = []
            for url, source in batch:
                pg = ctx.new_page()
                try:
                    pg.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
                pages.append((pg, url, source))

            for pg, url, source in pages:
                try:
                    pg.bring_to_front()
                    human_scroll(pg)
                    time.sleep(random.uniform(*DWELL_SECONDS))   # stay on page
                    html = pg.content()
                    a = parse_page(html, url, source)
                    words = a["word_count"] if a else 0
                    kind = captcha_kind(html, words)
                    ok = bool(a and words >= MIN_WORDS and kind != "strong")
                    if not ok and kind == "strong":
                        if wait_for_human_captcha(pg):
                            a = parse_page(pg.content(), url, source)
                            ok = True
                        else:
                            db_exec("UPDATE urls SET status='skipped_captcha' "
                                    "WHERE url=?", (url,))
                            captcha_fails[source] = captcha_fails.get(source, 0) + 1
                            print(f"   skipped (captcha not solved): {url[:70]}")
                            if captcha_fails[source] == CAPTCHA_GIVE_UP_AFTER:
                                print(f"   -> giving up on {source} for this run")
                            continue
                        captcha_fails[source] = 0
                    if ok:
                        a["source"] = source
                        save_article(a, "browser")
                        db_exec("UPDATE urls SET status='done' WHERE url=?", (url,))
                        show(a, "chrome")
                    else:
                        db_exec("UPDATE urls SET status='failed' WHERE url=?", (url,))
                except Exception as e:
                    db_exec("UPDATE urls SET status='failed' WHERE url=?", (url,))
                    print(f"   [!] {url[:60]}: {e}")
            ctx.close()
        browser.close()


# --------------------------------- EXPORT ------------------------------------
def export_csv():
    rows = db_query("SELECT source,url,title,author,date,time,description,tags,"
                    "language,body,word_count,method FROM articles")
    with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["source", "url", "title", "author", "date", "time",
                    "description", "tags", "language", "body", "word_count",
                    "method"])
        w.writerows(rows)
    print(f"\nExported {len(rows)} articles to {CSV_FILE}")


def main():
    try:
        sites = [l.strip() for l in open(SOURCES_FILE, encoding="utf-8")
                 if l.strip() and not l.startswith("#")]
    except FileNotFoundError:
        print(f"Put a file called {SOURCES_FILE} next to this script "
              "(one website per line).")
        return
    if TEST_MODE:
        sites = sites[:3]

    try:
        if "--retry" in sys.argv:
            db_exec("UPDATE urls SET status='new' WHERE status IN "
                    "('captcha','needs_browser','skipped_captcha','failed','error')")
            print("Retrying pages that were wrongly flagged earlier.")
        if "--rediscover" in sys.argv or db_query("SELECT COUNT(*) FROM urls")[0][0] == 0:
            phase_discover(sites)
        else:
            print("Links already stored from an earlier run -> resuming.")
        if "--chrome" in sys.argv:
            # Show the Chrome tabs FIRST: N random pages go to the browser
            n = 200
            if "--chrome-pages" in sys.argv:
                n = int(sys.argv[sys.argv.index("--chrome-pages") + 1])
            db_exec("UPDATE urls SET status='needs_browser' WHERE url IN "
                    "(SELECT url FROM urls WHERE status='new' "
                    "ORDER BY RANDOM() LIMIT ?)", (n,))
            print(f"Chrome mode: {n} pages will open in tabs first.")
            phase_browser(limit=n)
        phase_fast()
        phase_browser()
    except KeyboardInterrupt:
        print("\nStopped by user. Progress is saved; run again to continue.")
    finally:
        export_csv()
        print(f"Total articles saved: {article_count()}")


if __name__ == "__main__":
    main()
