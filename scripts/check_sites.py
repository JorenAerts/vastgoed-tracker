#!/usr/bin/env python3
"""Check vastgoedkantoor sites for text changes and publish them as RSS items."""

import difflib
import hashlib
import json
import textwrap
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

ROOT = Path(__file__).resolve().parent.parent
SITES_FILE = ROOT / "sites.json"
STATE_FILE = ROOT / "state" / "snapshots.json"
FEED_FILE = ROOT / "docs" / "feed.xml"

FEED_TITLE = "Vastgoedkantoren Hasselt - wijzigingsmonitor"
FEED_LINK = "https://github.com/"  # overschreven door workflow via --site-url indien nodig
FEED_DESCRIPTION = "Detecteert wijzigingen op de websites van vastgoedkantoren rond Hasselt."

TIMEOUT = 15
FAIL_THRESHOLD = 3
FEED_MAX_AGE_DAYS = 60
STRIP_TAGS = ["script", "style", "nav", "header", "footer", "noscript"]
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch(url):
    """Return page text, or None if the site can't be reached (after 1 retry)."""
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code >= 400:
                if attempt == 0:
                    continue
                return None
            return resp.text
        except requests.RequestException:
            if attempt == 0:
                continue
            return None
    return None


def extract_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(STRIP_TAGS):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def diff_snippet(old_text, new_text, max_lines=12, max_chars=1000):
    old_lines = textwrap.wrap(old_text, 100)
    new_lines = textwrap.wrap(new_text, 100)
    diff = difflib.unified_diff(old_lines, new_lines, lineterm="")
    changed = [
        line for line in diff
        if line[:1] in ("+", "-") and not line.startswith(("+++", "---"))
    ]
    if not changed:
        return "Wijziging gedetecteerd (geen leesbare tekstdiff)."
    snippet = "\n".join(changed[:max_lines])
    return snippet[:max_chars]


def slugify(name):
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def read_existing_items(path):
    """Parse an existing feed.xml (if any) back into a list of item dicts."""
    items = []
    if not path.exists():
        return items
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return items
    for item in tree.getroot().findall("./channel/item"):
        guid = item.findtext("guid") or ""
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        description = item.findtext("description") or ""
        pub_date_raw = item.findtext("pubDate")
        try:
            pub_date = parsedate_to_datetime(pub_date_raw)
        except (TypeError, ValueError):
            continue
        if pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=timezone.utc)
        items.append(
            {
                "guid": guid,
                "title": title,
                "link": link,
                "description": description,
                "pub_date": pub_date,
            }
        )
    return items


def write_feed(path, items):
    """Write all items (already sorted newest-first) out as docs/feed.xml."""
    fg = FeedGenerator()
    fg.title(FEED_TITLE)
    fg.link(href=FEED_LINK, rel="alternate")
    fg.description(FEED_DESCRIPTION)
    fg.language("nl-be")

    for item in items:
        fe = fg.add_entry(order="append")
        fe.title(item["title"])
        fe.link(href=item["link"])
        fe.description(item["description"])
        fe.guid(item["guid"], permalink=False)
        fe.pubDate(item["pub_date"])

    path.parent.mkdir(parents=True, exist_ok=True)
    fg.rss_file(str(path), pretty=True)


def main():
    sites = load_json(SITES_FILE, [])
    state = load_json(STATE_FILE, {})
    existing_items = read_existing_items(FEED_FILE)

    now = datetime.now(timezone.utc)
    new_items = []

    for site in sites:
        name = site["name"]
        url = site["url"]
        entry = state.get(name, {})

        html = fetch(url)

        if html is None:
            fail_streak = entry.get("fail_streak", 0) + 1
            entry["fail_streak"] = fail_streak
            state[name] = entry
            if fail_streak == FAIL_THRESHOLD:
                new_items.append(
                    {
                        "guid": f"unreachable-{slugify(name)}-{now.date().isoformat()}",
                        "title": f"Kon {name} niet meer bereiken",
                        "link": url,
                        "description": (
                            f"{name} is nu {fail_streak} dagen op rij niet bereikbaar "
                            "(timeout, blokkering of serverfout)."
                        ),
                        "pub_date": now,
                    }
                )
            print(f"[FAIL] {name}: onbereikbaar ({fail_streak}x op rij)")
            continue

        text = extract_text(html)
        new_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

        if "hash" not in entry:
            # eerste keer dat we deze site zien: baseline opslaan, geen item
            state[name] = {"hash": new_hash, "text": text, "fail_streak": 0}
            print(f"[BASELINE] {name}")
            continue

        if entry["fail_streak"] > 0:
            entry["fail_streak"] = 0

        if entry["hash"] == new_hash:
            state[name] = entry
            print(f"[OK] {name}: geen wijziging")
            continue

        description = diff_snippet(entry.get("text", ""), text)
        new_items.append(
            {
                "guid": f"{slugify(name)}-{now.isoformat()}",
                "title": name,
                "link": url,
                "description": description,
                "pub_date": now,
            }
        )
        state[name] = {"hash": new_hash, "text": text, "fail_streak": 0}
        print(f"[CHANGE] {name}: wijziging gedetecteerd")

    save_json(STATE_FILE, state)

    cutoff = now - timedelta(days=FEED_MAX_AGE_DAYS)
    combined = existing_items + new_items
    combined = [i for i in combined if i["pub_date"] >= cutoff]
    combined.sort(key=lambda i: i["pub_date"], reverse=True)

    write_feed(FEED_FILE, combined)
    print(f"Feed geschreven: {len(combined)} items ({len(new_items)} nieuw).")


if __name__ == "__main__":
    main()
