"""feeds.json のブログの RSS / Atom を取得し、直近の記事を data/latest.json に書き出す。

標準ライブラリだけで動く（GitHub Actions の python3 でそのまま実行できる）。
usage: python3 scripts/fetch_feeds.py [DAYS]
"""
import gzip
import hashlib
import html
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (compatible; tech-blog-feeds/1.0; +https://github.com/masarugit/tech-blog-feeds)"
DEFAULT_MAX_ITEMS = 30
SUMMARY_LEN = 90


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.8, */*;q=0.5"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(), r.geturl()


def strip_tags(s):
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s).strip()


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        d = None
    if d is None:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            m = re.match(r"\d{4}-\d{2}-\d{2}", s)
            d = datetime.fromisoformat(m.group(0)) if m else None
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def clean_url(u):
    """計測用のクエリ（utm_*、Medium の source=rss など）を取り除く。"""
    p = urlsplit(u)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not k.startswith("utm_") and k not in ("source", "sk", "gi")]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))


def local(tag):
    return tag.rsplit("}", 1)[-1]


def child(el, *names):
    for c in el:
        if local(c.tag) in names:
            return c
    return None


def text_of(el):
    return "".join(el.itertext()).strip() if el is not None else ""


def parse_feed(data, base):
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    data = data.lstrip(b"\xef\xbb\xbf \t\r\n")
    root = ET.fromstring(data)
    entries = [e for e in root.iter() if local(e.tag) in ("item", "entry")]
    out = []
    for e in entries:
        title = strip_tags(text_of(child(e, "title")))
        link = ""
        for c in e:
            if local(c.tag) != "link":
                continue
            href = c.get("href")
            if href and c.get("rel", "alternate") == "alternate":
                link = href
                break
            if not href and (c.text or "").strip():
                link = c.text.strip()
                break
        if not link:
            g = child(e, "guid")
            if g is not None and (g.text or "").startswith("http"):
                link = g.text.strip()
        date = None
        for n in ("pubDate", "published", "date", "issued", "updated", "modified"):
            date = parse_date(text_of(child(e, n)))
            if date:
                break
        summ = ""
        for n in ("description", "summary", "encoded", "content"):
            summ = strip_tags(text_of(child(e, n)))
            if summ:
                break
        if title and link and date:
            out.append({"title": title, "url": clean_url(urljoin(base, link)), "publishedAt": date, "summary": summ[:SUMMARY_LEN]})
    return out


def discover(site):
    data, final = get(site)
    page = data.decode("utf-8", "replace")
    for m in re.finditer(r"<link\b[^>]*>", page, re.I):
        tag = m.group(0)
        if re.search(r"rel=[\"']?alternate", tag, re.I) and re.search(r"application/(rss|atom)\+xml", tag, re.I):
            h = re.search(r"href=[\"']([^\"']+)", tag, re.I)
            if h:
                return urljoin(final, html.unescape(h.group(1)))
    return None


def fetch_one(feed, since):
    if not feed.get("feed"):
        return {"name": feed["name"], "ok": False, "count": 0, "feedUrl": "", "error": "RSSフィードを提供していないため取得対象外"}, []
    tried = []
    urls = [feed["feed"]]
    result = {"name": feed["name"], "ok": False, "count": 0, "feedUrl": feed["feed"], "error": ""}
    for attempt in range(2):
        url = urls[-1]
        tried.append(url)
        try:
            data, final = get(url)
            items = parse_feed(data, final)
            result.update(ok=True, feedUrl=url, error="")
            break
        except Exception as ex:  # noqa: BLE001 - 失敗は記録して次へ
            result["error"] = f"{type(ex).__name__}: {ex}"[:200]
            items = []
            if attempt == 0:
                try:
                    found = discover(feed["site"])
                except Exception:  # noqa: BLE001
                    found = None
                if not found or found in tried:
                    break
                urls.append(found)
    result["parsed"] = len(items)
    result["latest"] = max((i["publishedAt"] for i in items), default=None)
    result["latest"] = result["latest"].strftime("%Y-%m-%dT%H:%M:%SZ") if result["latest"] else ""
    items = [i for i in items if i["publishedAt"] >= since]
    items.sort(key=lambda i: i["publishedAt"], reverse=True)
    items = items[: feed.get("maxItems", DEFAULT_MAX_ITEMS)]
    out = []
    for i in items:
        out.append({
            "id": hashlib.md5(i["url"].encode()).hexdigest()[:16],
            "blog": feed["name"],
            "category": feed["category"],
            "title": i["title"],
            "url": i["url"],
            "publishedAt": i["publishedAt"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "summary": i["summary"],
        })
    result["count"] = len(out)
    return result, out


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    since = datetime.now(timezone.utc) - timedelta(days=days)
    feeds = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda f: fetch_one(f, since), feeds))
    status = [r for r, _ in results]
    items, seen = [], set()
    for _, its in results:
        for it in its:
            if it["id"] not in seen:
                seen.add(it["id"])
                items.append(it)
    items.sort(key=lambda i: i["publishedAt"], reverse=True)
    out = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "days": days,
        "feeds": status,
        "items": items,
    }
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for s in status if s["ok"])
    print(f"{ok}/{len(status)} feeds ok, {len(items)} items")
    for s in status:
        if not s["ok"]:
            print(f"  NG {s['name']}: {s['error']}")


main()
