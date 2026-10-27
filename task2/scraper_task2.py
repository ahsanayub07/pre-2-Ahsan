"""
Task 2: news scraper, 10,000 valid articles.
Tools: RSS (feedparser) + sitemaps to find links, requests + BeautifulSoup to
read pages, Selenium (Chrome, 5 tabs, scrolling, pauses) for dynamic pages.

  Phase 1 DISCOVER : RSS feeds + sitemaps (robots.txt respected) -> links in SQLite.
  Phase 2 FAST     : threads download pages, BeautifulSoup extracts the fields.
  Phase 3 CHROME   : Selenium opens pages that need JavaScript in 5 tabs,
                     scrolls like a person, stays a few seconds. Captcha:
                     never bypassed. You solve it in the tab, or the page is skipped.

Stop with Ctrl+C any time; run again to continue (progress is in SQLite).

  pip install -r requirements.txt
  python scraper_task2.py --test           quick test (3 sites, 60 articles)
  python scraper_task2.py                  full run (HTTP, then Chrome for leftovers)
  python scraper_task2.py --chrome         show Chrome tabs first (200 pages)
  python scraper_task2.py --chrome --chrome-pages 500
  python scraper_task2.py --retry          retry failed pages
  python scraper_task2.py --rediscover     search for links again
"""
import csv, gzip, html as htmllib, json, random, re, sqlite3, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser

import feedparser
import requests
from bs4 import BeautifulSoup

# ------------------------------ SETTINGS -------------------------------------
TARGET_TOTAL = 10_000
MAX_PER_SOURCE = 600
DISCOVER_THREADS = 16
DISCOVER_TIMEOUT = 180
FETCH_THREADS = 64
NUM_BATCHES = 70               # pages are downloaded in this many batches
PER_SITE_DELAY = 1.5
REQUEST_TIMEOUT = 20
MIN_WORDS = 150                # valid article = at least this many words
RESPECT_ROBOTS = True
TABS_AT_ONCE = 5
BROWSER_PAGES_LIMIT = 1_500
DWELL_SECONDS = (4, 10)
CAPTCHA_WAIT_SECONDS = 60
CAPTCHA_GIVE_UP_AFTER = 3
BLOCK_SITE_AFTER = 15          # bot-check hits before a site is skipped in the fast phase
MAX_SITEMAPS_PER_SITE = 30
DB_FILE, CSV_FILE, SOURCES_FILE = "articles_task2.db", "articles_task2.csv", "sources.txt"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
FEED_PATHS = ["/feed", "/feed/", "/rss", "/rss.xml", "/feed.xml", "/atom.xml",
              "/index.xml", "/rss/index.xml", "/feeds/all.rss.xml"]
STRONG_CAPTCHA = ("verify you are human", "are you a robot", "unusual traffic",
                  "captcha-delivery", "cf-challenge", "just a moment...",
                  "press & hold", "access denied", "px-captcha", "g-recaptcha",
                  "h-captcha", "attention required")
TEST_MODE = "--test" in sys.argv
if TEST_MODE:
    TARGET_TOTAL, MAX_PER_SOURCE, BROWSER_PAGES_LIMIT = 60, 20, 10

# ------------------------------- DATABASE ------------------------------------
db = sqlite3.connect(DB_FILE, check_same_thread=False)
db_lock = threading.Lock()
db.executescript("""
CREATE TABLE IF NOT EXISTS urls (url TEXT PRIMARY KEY, source TEXT,
    status TEXT DEFAULT 'new', reason TEXT);
CREATE TABLE IF NOT EXISTS articles (url TEXT PRIMARY KEY, source TEXT, title TEXT,
    author TEXT, date TEXT, time TEXT, description TEXT, tags TEXT, language TEXT,
    body TEXT, word_count INTEGER, method TEXT);
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


def set_status(url, status, reason=""):
    db_exec("UPDATE urls SET status=?, reason=? WHERE url=?", (status, reason, url))


# ------------------------------- HELPERS -------------------------------------
_robots, _robots_lock = {}, threading.Lock()
_last_hit, _hit_lock = {}, threading.Lock()


def allowed_by_robots(url):
    if not RESPECT_ROBOTS:
        return True
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    with _robots_lock:
        rp = _robots.get(base)
    if rp is None:
        rp = RobotFileParser()
        try:
            r = requests.get(base + "/robots.txt", headers=HEADERS, timeout=10)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            rp.parse([])
        with _robots_lock:
            _robots[base] = rp
    return rp.can_fetch(UA, url)


def wait_turn(url):
    host = urlparse(url).netloc
    with _hit_lock:
        now = time.time()
        ready = max(now, _last_hit.get(host, 0) + PER_SITE_DELAY)
        _last_hit[host] = ready
    if ready - now > 0:
        time.sleep(ready - now)


def get(url, **kw):
    wait_turn(url)
    return requests.get(url, headers=HEADERS, timeout=kw.pop("timeout", REQUEST_TIMEOUT), **kw)


def looks_like_article(url):
    path = urlparse(url).path.lower()
    if any(x in path for x in ("/tag/", "/tags/", "/category/", "/author/",
                               "/video", "/gallery", "/live/", "/search", "/topic")):
        return False
    last = path.rstrip("/").split("/")[-1]
    return (path.count("/") >= 2 and "-" in last and len(last) > 15) or \
        path.endswith((".html", ".htm", ".ece", ".php"))


# -------------------------- BEAUTIFULSOUP PARSER -----------------------------
def _meta(soup, *names):
    for n in names:
        t = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
        if t and t.get("content", "").strip():
            return t["content"].strip()
    return ""


def _jsonld(soup):
    out = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except Exception:
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack.extend(x)
            elif isinstance(x, dict):
                out.append(x)
                stack.extend(v for v in x.values() if isinstance(v, (dict, list)))
    return out


BOILERPLATE = ("cookie notice", "privacy center", "consent management",
               "tracking technologies", "become an independent member",
               "all products featured on wired", "your window is closing",
               "get full access for", "subscribe to continue", "we may earn commission")


def clean_body(body):
    keep = [ln for ln in body.splitlines()
            if ln.strip() and not any(b in ln.lower() for b in BOILERPLATE)]
    return "\n".join(keep)


def parse_page(html, url, source):
    """Extract an article dict from HTML with BeautifulSoup, or None."""
    soup = BeautifulSoup(html, "html.parser")
    ld = [d for d in _jsonld(soup) if str(d.get("@type", "")).lower().endswith(
        ("article", "newsarticle", "blogposting", "reportage"))]
    ld = ld[0] if ld else {}

    title = _meta(soup, "og:title", "twitter:title") or ld.get("headline", "")
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(" ", strip=True) if h1 else (soup.title.string if soup.title else "")

    author = _meta(soup, "author", "article:author", "parsely-author")
    a = ld.get("author")
    if not author and a:
        a = a[0] if isinstance(a, list) and a else a
        author = a.get("name", "") if isinstance(a, dict) else str(a)
    if not author:
        t = soup.find(attrs={"rel": "author"}) or soup.find(class_=re.compile("author|byline", re.I))
        author = t.get_text(" ", strip=True)[:80] if t else ""

    raw = (_meta(soup, "article:published_time", "og:article:published_time",
                 "datePublished", "pubdate", "date") or ld.get("datePublished", ""))
    if not raw:
        t = soup.find("time")
        raw = (t.get("datetime") or t.get_text(strip=True)) if t else ""
    date, clock = raw[:10] if re.match(r"\d{4}-\d{2}-\d{2}", raw) else raw, ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        date, clock = dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S %z").strip()
    except ValueError:
        pass

    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        tag.decompose()
    box = soup.find("article") or soup.find(attrs={"itemprop": "articleBody"}) or soup.find("main") or soup
    paras = [p.get_text(" ", strip=True) for p in box.find_all("p")]
    paras = [p for p in paras if len(p.split()) >= 5]
    body = clean_body("\n".join(paras))
    if len(body.split()) < MIN_WORDS and box is not soup:   # fallback: whole page
        paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        body = clean_body("\n".join(p for p in paras if len(p.split()) >= 5))

    ogt = _meta(soup, "og:type")
    if ogt and "article" not in ogt.lower() and "news" not in ogt.lower():
        body = ""                                  # topic/section page, not an article
    tags = _meta(soup, "keywords", "article:tag", "news_keywords")
    lang = (soup.html.get("lang", "") if soup.html else "") or _meta(soup, "og:locale")
    return {"url": url, "source": source, "title": title.strip(),
            "author": author.strip(), "date": date, "time": clock,
            "description": _meta(soup, "og:description", "description"),
            "tags": tags, "language": lang, "body": body,
            "word_count": len(body.split())}


def is_bot_page(html, words):
    if words >= 150:
        return False
    low = html.lower()
    return any(m in low for m in STRONG_CAPTCHA) or words < 20 and "captcha" in low


def save_article(a, method):
    db_exec("INSERT OR REPLACE INTO articles VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (a["url"], a["source"], a["title"], a["author"], a["date"], a["time"],
             a["description"], a["tags"], a["language"], a["body"], a["word_count"], method))


def show(a, tag):
    print(f"[{tag}] {a['source']} | {a['title'][:70]}")
    print(f"      {a['date']} {a['time']} | by {a['author'] or 'N/A'} | {a['word_count']} words")
    print(f"      {' '.join(a['body'].split())[:160]}...")


# ---------------------------- PHASE 1: DISCOVER ------------------------------
def _locs(xml):
    return [htmllib.unescape(re.sub(r"^<!\[CDATA\[|\]\]>$", "", m.strip()))
            for m in re.findall(r"<loc>\s*(.*?)\s*</loc>", xml, re.S | re.I)]


def _read_xml(url):
    r = get(url, timeout=15)
    r.raise_for_status()
    data = r.content
    if url.endswith(".gz") or data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data.decode("utf-8", errors="ignore")


def find_feeds(home):
    """RSS/Atom feed URLs: <link rel=alternate> on the homepage + common paths."""
    feeds = []
    try:
        soup = BeautifulSoup(get(home, timeout=15).text, "html.parser")
        for l in soup.find_all("link", attrs={"type": re.compile("rss|atom", re.I)}):
            if l.get("href"):
                feeds.append(urljoin(home, l["href"]))
    except Exception:
        pass
    feeds += [urljoin(home, p) for p in FEED_PATHS]
    return list(dict.fromkeys(feeds))[:25]


def crawl_sitemaps(home, add, is_full):
    base = home.rstrip("/")
    queue = []
    try:
        for line in get(base + "/robots.txt", timeout=10).text.splitlines():
            if line.lower().startswith("sitemap:"):
                queue.append(line.split(":", 1)[1].strip())
    except Exception:
        pass
    queue = queue or [base + "/sitemap.xml", base + "/sitemap_index.xml"]
    fetched = 0
    while queue and fetched < MAX_SITEMAPS_PER_SITE and not is_full():
        sm = queue.pop(0)
        try:
            xml = _read_xml(sm)
        except Exception:
            continue
        fetched += 1
        if "<sitemapindex" in xml.lower():
            kids = re.findall(r"<sitemap>(.*?)</sitemap>", xml, re.S | re.I)
            children = []
            for k in kids:
                loc, lm = _locs(k), re.search(r"<lastmod>(.*?)</lastmod>", k, re.I)
                if loc and not any(x in loc[0].lower() for x in
                                   ("image", "video", "tag", "categor", "author", "topic")):
                    children.append((lm.group(1) if lm else "", loc[0]))
            children.sort(key=lambda c: c[0], reverse=True)       # newest first
            queue = [c[1] for c in children] + queue
        else:
            for u in _locs(xml):
                add(u)
                if is_full():
                    break


def discover(home):
    if not home.startswith("http"):
        home = "https://" + home
    source = urlparse(home).netloc.replace("www.", "")
    found, seen = [], set()

    def add(u):
        if u and u not in seen and looks_like_article(u):
            seen.add(u)
            found.append(u)

    for feed in find_feeds(home):                       # RSS first
        try:
            for e in feedparser.parse(feed, request_headers=HEADERS).entries:
                add(e.get("link"))
        except Exception:
            pass
        if len(found) >= MAX_PER_SOURCE:
            break
    try:
        crawl_sitemaps(home, add, lambda: len(found) >= MAX_PER_SOURCE)
    except Exception:
        pass
    return source, found[:MAX_PER_SOURCE]


def phase_discover(sites):
    print(f"\n=== PHASE 1: finding links (RSS + sitemaps) on {len(sites)} sites ===")
    ex = ThreadPoolExecutor(max_workers=DISCOVER_THREADS)
    futures = {ex.submit(discover, s): s for s in sites}
    n = 0
    try:
        for fut in as_completed(futures, timeout=DISCOVER_TIMEOUT * 3):
            n += 1
            try:
                source, urls = fut.result(timeout=DISCOVER_TIMEOUT)
            except Exception:
                print(f"  [{n}/{len(sites)}] {futures[fut]}: failed")
                continue
            with db_lock:
                db.executemany("INSERT OR IGNORE INTO urls(url, source) VALUES (?,?)",
                               [(u, source) for u in urls])
                db.commit()
            print(f"  [{n}/{len(sites)}] {source}: {len(urls)} links")
    except Exception:
        print("  (some sites were too slow and were skipped)")
    ex.shutdown(wait=False, cancel_futures=True)
    print(f"  total links stored: {db_query('SELECT COUNT(*) FROM urls')[0][0]}")


# ------------------------- PHASE 2: FAST HTTP FETCH --------------------------
_bot_hits, _errs, _net = {}, {}, [0.0, True]
_net_lock = threading.Lock()


def internet_ok():
    with _net_lock:
        if time.time() - _net[0] < 5:
            return _net[1]
    try:
        requests.head("https://www.google.com", timeout=5)
        ok = True
    except Exception:
        ok = False
    with _net_lock:
        _net[0], _net[1] = time.time(), ok
    return ok


def wait_for_internet():
    if internet_ok():
        return
    print("\n  [!] Internet is down. Waiting...")
    while not internet_ok():
        time.sleep(10)
    print("  Internet is back. Continuing.")


def fetch_one(url, source, _retry=False):
    if article_count() >= TARGET_TOTAL:
        return
    if _bot_hits.get(source, 0) >= BLOCK_SITE_AFTER:
        set_status(url, "skipped_captcha", "site blocks bots")
        return
    if not allowed_by_robots(url):
        set_status(url, "robots", "disallowed by robots.txt")
        return
    try:
        r = get(url)
        if r.status_code in (403, 429, 503):
            _bot_hits[source] = _bot_hits.get(source, 0) + 1
            set_status(url, "captcha", f"HTTP {r.status_code}")
            return
        r.raise_for_status()
        a = parse_page(r.text, url, source)
        words = a["word_count"] if a else 0
        if is_bot_page(r.text, words):
            _bot_hits[source] = _bot_hits.get(source, 0) + 1
            set_status(url, "captcha", "bot-check page")
        elif words >= MIN_WORDS:
            save_article(a, "bs4")
            set_status(url, "done")
            show(a, "http")
        elif words < 20:
            set_status(url, "needs_browser", "little text, maybe JavaScript")
        else:
            set_status(url, "short", f"only {words} words")
    except Exception as e:
        if not internet_ok() and not _retry:
            wait_for_internet()
            return fetch_one(url, source, True)
        reason = type(e).__name__
        _errs[reason] = _errs.get(reason, 0) + 1
        set_status(url, "error", reason)


def phase_fast():
    rows = db_query("SELECT url, source FROM urls WHERE status='new'")
    by_src = {}
    for u, s in rows:
        by_src.setdefault(s, []).append(u)
    mixed = []
    while any(by_src.values()):                  # round-robin across sites
        for s, lst in by_src.items():
            if lst:
                mixed.append((lst.pop(0), s))
    if not mixed:
        return
    n_batches = min(NUM_BATCHES, len(mixed))
    size = -(-len(mixed) // n_batches)           # ceiling division
    print(f"\n=== PHASE 2: {len(mixed)} pages in {n_batches} batches of ~{size} "
          f"({FETCH_THREADS} threads) ===")
    t0 = time.time()
    for b in range(n_batches):
        batch = mixed[b * size:(b + 1) * size]
        if not batch:
            break
        start = article_count()
        with ThreadPoolExecutor(max_workers=FETCH_THREADS) as ex:
            list(ex.map(lambda x: fetch_one(*x), batch))
        total = article_count()
        mins = (time.time() - t0) / 60
        left = (n_batches - b - 1) * mins / (b + 1)
        print(f"  --- batch {b + 1}/{n_batches} done: +{total - start} articles, "
              f"saved {total}/{TARGET_TOTAL} | {mins:.1f} min used, ~{left:.0f} min left "
              f"| errors: {dict(sorted(_errs.items(), key=lambda x: -x[1])[:3])}")
        if (b + 1) % 10 == 0:
            export_csv()                          # checkpoint every 10 batches
        if total >= TARGET_TOTAL:
            print("  target reached")
            return


# ------------------------ PHASE 3: SELENIUM (CHROME) -------------------------
def human_scroll(driver):
    """Scroll down in small random steps, sometimes back up a little."""
    try:
        height = driver.execute_script("return document.body.scrollHeight") or 3000
        pos = 0
        while pos < height * 0.9:
            step = random.randint(250, 600)
            pos += step
            driver.execute_script(f"window.scrollTo(0, {pos});")
            time.sleep(random.uniform(0.3, 1.0))
            if random.random() < 0.15:
                pos -= random.randint(80, 200)
                driver.execute_script(f"window.scrollTo(0, {max(pos, 0)});")
                time.sleep(random.uniform(0.3, 0.8))
    except Exception:
        pass


def wait_for_human_captcha(driver):
    print(f"   >>> CAPTCHA in Chrome. Solve it in the tab within {CAPTCHA_WAIT_SECONDS}s <<<")
    end = time.time() + CAPTCHA_WAIT_SECONDS
    while time.time() < end:
        time.sleep(3)
        try:
            html = driver.page_source
            if not is_bot_page(html, len(parse_page(html, "", "")["body"].split())):
                return True
        except Exception:
            pass
    return False


def make_driver():
    from selenium import webdriver
    opts = webdriver.ChromeOptions()
    opts.add_argument("--start-maximized")
    opts.add_argument(f"--user-agent={UA}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    return webdriver.Chrome(options=opts)          # Selenium Manager gets the driver


def phase_browser(limit=None):
    rows = db_query("SELECT url, source FROM urls WHERE status='needs_browser'")
    rows = rows[:limit or BROWSER_PAGES_LIMIT]
    if not rows:
        return
    print(f"\n=== PHASE 3: opening {len(rows)} pages in Chrome ({TABS_AT_ONCE} tabs) ===")
    driver = make_driver()
    fails = {}
    try:
        for i in range(0, len(rows), TABS_AT_ONCE):
            if article_count() >= TARGET_TOTAL:
                print("  target reached")
                break
            batch = []
            for url, source in rows[i:i + TABS_AT_ONCE]:
                if fails.get(source, 0) >= CAPTCHA_GIVE_UP_AFTER:
                    set_status(url, "skipped_captcha", "captcha not solved")
                else:
                    batch.append((url, source))
            handles = []
            for k, (url, source) in enumerate(batch):
                if k == 0:
                    handle = driver.current_window_handle
                else:
                    driver.switch_to.new_window("tab")
                    handle = driver.current_window_handle
                driver.set_page_load_timeout(30)
                try:
                    driver.get(url)
                except Exception:
                    pass
                handles.append((handle, url, source))
            for handle, url, source in handles:
                try:
                    driver.switch_to.window(handle)
                    human_scroll(driver)
                    time.sleep(random.uniform(*DWELL_SECONDS))
                    html = driver.page_source
                    a = parse_page(html, url, source)
                    words = a["word_count"] if a else 0
                    bot = is_bot_page(html, words)
                    if bot and not wait_for_human_captcha(driver):
                        fails[source] = fails.get(source, 0) + 1
                        set_status(url, "skipped_captcha", "captcha not solved")
                        print(f"   skipped (captcha not solved): {url[:70]}")
                        continue
                    if bot:
                        a = parse_page(driver.page_source, url, source)
                        words = a["word_count"]
                    fails[source] = 0
                    if words >= MIN_WORDS:
                        save_article(a, "selenium")
                        set_status(url, "done")
                        show(a, "chrome")
                    else:
                        set_status(url, "failed", f"no article text ({words} words)")
                except Exception as e:
                    set_status(url, "failed", type(e).__name__)
                    print(f"   [!] {url[:60]}: {e}")
            for handle, _, _ in handles[1:]:           # close extra tabs
                try:
                    driver.switch_to.window(handle)
                    driver.close()
                except Exception:
                    pass
            driver.switch_to.window(driver.window_handles[0])
    finally:
        driver.quit()


# --------------------------------- EXPORT ------------------------------------
def export_csv():
    rows = db_query("SELECT source,url,title,author,date,time,description,tags,"
                    "language,body,word_count,method FROM articles")
    with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["source", "url", "title", "author", "date", "time", "description",
                    "tags", "language", "body", "word_count", "method"])
        w.writerows(rows)
    print(f"\nExported {len(rows)} articles to {CSV_FILE}")


def main():
    try:
        sites = [l.strip() for l in open(SOURCES_FILE, encoding="utf-8")
                 if l.strip() and not l.startswith("#")]
    except FileNotFoundError:
        print(f"Put {SOURCES_FILE} next to this script (one website per line).")
        return
    if TEST_MODE:
        sites = sites[:3]
    try:
        if "--retry" in sys.argv:
            db_exec("UPDATE urls SET status='new' WHERE status IN "
                    "('captcha','needs_browser','skipped_captcha','failed','error')")
        if "--rediscover" in sys.argv or db_query("SELECT COUNT(*) FROM urls")[0][0] == 0:
            phase_discover(sites)
        else:
            print("Links already stored -> resuming.")
        if "--chrome" in sys.argv:
            n = 200
            if "--chrome-pages" in sys.argv:
                n = int(sys.argv[sys.argv.index("--chrome-pages") + 1])
            db_exec("UPDATE urls SET status='needs_browser' WHERE url IN (SELECT url FROM "
                    "urls WHERE status='new' ORDER BY RANDOM() LIMIT ?)", (n,))
            print(f"Chrome mode: {n} pages open in tabs first.")
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
