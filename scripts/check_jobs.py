#!/usr/bin/env python3
"""
Job Watchtower — checks each portal in config/sources.csv for postings that
match your keywords, and writes the results into docs/data/ for the web app.

Data files produced (all in docs/data/, all committed back to the repo by
the GitHub Actions workflow):
  - matches.json    cumulative feed of every match ever found (capped)
  - seen.json       internal de-dupe list, so the same posting isn't re-added
  - run_meta.json   info about the most recent run: timestamp, which ids
                    were new this run, and per-source status (ok/error)
"""

import csv
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES_CSV = os.path.join(ROOT, "config", "sources.csv")
DATA_DIR = os.path.join(ROOT, "docs", "data")
MATCHES_PATH = os.path.join(DATA_DIR, "matches.json")
SEEN_PATH = os.path.join(DATA_DIR, "seen.json")
RUN_META_PATH = os.path.join(DATA_DIR, "run_meta.json")

MAX_MATCHES_KEPT = 400
RETENTION_DAYS = 5          # postings older than this drop off the board
REQUEST_TIMEOUT = 20
REQUEST_RETRIES = 2         # extra attempts on transient network errors
REQUEST_RETRY_DELAY = 4     # seconds between retries
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; JobWatchtower/1.0; "
        "+https://github.com/) job-alert-personal-use"
    )
}

# Anchor text shorter than this is almost always nav/UI chrome ("Home",
# "Login", icons), not a job title, so we skip it.
MIN_LINK_TEXT_LEN = 8

# Employment-type detection: EN + DE phrasing, since these are German portals.
JOB_TYPE_SIGNALS = {
    "working_student": ["werkstudent", "working student", "working-student"],
    "internship": [
        "praktikum", "praktikant", "praktikantin", "internship",
        "intern ", "trainee", "abschlussarbeit", "thesis",
    ],
    "full_time": [
        "vollzeit", "full-time", "full time", "permanent",
        "unbefristet", "festanstellung",
    ],
}


def classify_job_types(text_lower):
    found = [
        job_type
        for job_type, signals in JOB_TYPE_SIGNALS.items()
        if any(sig in text_lower for sig in signals)
    ]
    return found or ["unspecified"]


# Best-effort "date posted" detection. Career pages don't expose this
# consistently, so we look for a <time> element first, then fall back to
# common date phrasing (absolute or relative, EN + DE) in the text around
# the job link. If nothing matches, the posting is labeled "No date".
NO_DATE_LABEL = "No date"

DATE_PATTERNS = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),                                   # 2026-07-30
    re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b"),                           # 30.07.2026
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),                             # 07/30/2026
    re.compile(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+"
        r"\d{1,2},?\s+\d{4}\b", re.IGNORECASE
    ),                                                                       # July 30, 2026
    re.compile(
        r"\b\d{1,2}\.?\s+(Januar|Februar|März|April|Mai|Juni|Juli|August|"
        r"September|Oktober|November|Dezember)\s+\d{4}\b", re.IGNORECASE
    ),                                                                       # 30. Juli 2026
    re.compile(
        r"\b(vor\s+)?\d+\s*"
        r"(days?|hours?|weeks?|months?|Tage?n?|Stunden?|Wochen?|Monate?n?)"
        r"(\s+ago)?\b", re.IGNORECASE
    ),                                                                       # "3 days ago" / "vor 2 Tagen"
    re.compile(r"\b(Today|Yesterday|Heute|Gestern)\b", re.IGNORECASE),
]


def find_posted_date(anchor):
    container = anchor.find_parent(["li", "tr", "article", "div"]) or anchor.parent
    if container is None:
        return NO_DATE_LABEL

    time_tag = container.find("time")
    if time_tag is not None:
        candidate = (time_tag.get("datetime") or time_tag.get_text(strip=True) or "").strip()
        if candidate:
            return candidate

    container_text = container.get_text(" ", strip=True)
    for pattern in DATE_PATTERNS:
        match = pattern.search(container_text)
        if match:
            return match.group(0).strip()

    return NO_DATE_LABEL


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return default
    return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_sources():
    if not os.path.exists(SOURCES_CSV):
        print(f"No sources file found at {SOURCES_CSV}", file=sys.stderr)
        return []
    sources = []
    with open(SOURCES_CSV, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company = (row.get("company") or "").strip()
            url = (row.get("url") or "").strip()
            kw_raw = (row.get("keywords") or "").strip()
            if not url:
                continue
            # Blank keywords = wildcard: every posting on the page counts,
            # you'll still be able to narrow down by employment type on the
            # dashboard.
            keywords = [k.strip().lower() for k in kw_raw.split(",") if k.strip()]
            sources.append({"company": company, "url": url, "keywords": keywords})
    return sources


def make_id(url, href, text):
    raw = f"{url}|{href}|{text}".encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:16]


def check_source(source):
    """Fetch one portal, return (postings, status_dict)."""
    url = source["url"]
    company = source.get("company", "")
    keywords = source["keywords"]
    status = {"url": url, "company": company, "checked_at": now_iso(), "ok": False, "error": None}
    postings = []

    last_error = None
    resp = None
    for attempt in range(REQUEST_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            last_error = None
            break
        except requests.RequestException as e:
            last_error = e
            if attempt < REQUEST_RETRIES:
                time.sleep(REQUEST_RETRY_DELAY)

    if last_error is not None:
        status["error"] = str(last_error)[:300]
        return postings, status

    status["ok"] = True

    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if len(text) < MIN_LINK_TEXT_LEN:
            continue
        text_lower = text.lower()

        if keywords:
            matched = [kw for kw in keywords if kw and kw in text_lower]
            if not matched:
                continue
        else:
            matched = ["(any)"]  # wildcard source: keep every listing

        href = urljoin(url, a["href"])
        postings.append(
            {
                "id": make_id(url, href, text),
                "title": text,
                "link": href,
                "source": url,
                "company": company,
                "matched_keywords": matched,
                "job_types": classify_job_types(text_lower),
                "date_posted": find_posted_date(a),
            }
        )

    return postings, status


def main():
    sources = read_sources()
    seen = load_json(SEEN_PATH, {"ids": []})
    seen_ids = set(seen.get("ids", []))
    matches = load_json(MATCHES_PATH, {"items": []})
    matches_items = matches.get("items", [])
    matches_by_id = {m["id"]: m for m in matches_items}
    prev_meta = load_json(RUN_META_PATH, {"sources": []})
    prev_status_by_url = {s["url"]: s.get("ok") for s in prev_meta.get("sources", [])}

    new_ids_this_run = []
    source_statuses = []
    status_changed = False

    if not sources:
        print("No sources configured in config/sources.csv — nothing to check.")

    for source in sources:
        postings, status = check_source(source)
        source_statuses.append(status)
        if prev_status_by_url.get(status["url"]) != status["ok"]:
            status_changed = True  # a portal went from ok->error or back
        for p in postings:
            if p["id"] in seen_ids:
                continue
            seen_ids.add(p["id"])
            p["first_seen"] = now_iso()
            matches_by_id[p["id"]] = p
            new_ids_this_run.append(p["id"])
        # be polite between requests
        time.sleep(1)

    if not new_ids_this_run and not status_changed:
        # Nothing new to report and every source's health is unchanged —
        # leave matches.json / seen.json / run_meta.json exactly as they
        # are so the workflow has nothing to commit this run.
        print(f"Checked {len(sources)} source(s). No new postings, no status changes — leaving data as is.")
        return

    # Drop postings older than the retention window, newest first
    cutoff = datetime.now(timezone.utc).timestamp() - RETENTION_DAYS * 86400
    def first_seen_ts(m):
        try:
            return datetime.fromisoformat(m.get("first_seen", "")).timestamp()
        except ValueError:
            return 0

    all_items = sorted(
        (m for m in matches_by_id.values() if first_seen_ts(m) >= cutoff),
        key=lambda m: m.get("first_seen", ""),
        reverse=True,
    )[:MAX_MATCHES_KEPT]

    save_json(MATCHES_PATH, {"items": all_items})
    save_json(SEEN_PATH, {"ids": sorted(seen_ids)})
    save_json(
        RUN_META_PATH,
        {
            "last_run": now_iso(),
            "new_ids": new_ids_this_run,
            "sources": source_statuses,
        },
    )

    print(f"Checked {len(sources)} source(s). {len(new_ids_this_run)} new match(es).")


if __name__ == "__main__":
    main()
