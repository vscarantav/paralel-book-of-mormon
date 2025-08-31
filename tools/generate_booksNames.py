#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate booksnames.json by crawling CJCLDS scriptures pages per language.

Usage:
  python tools/generate_booksnames.py \
      --languages ./languages.json \
      --out ./booksnames.json \
      --concurrency 12 \
      --timeout 12

Options:
  --languages   Path to languages.json (array of objects with "code" key)
  --out         Output JSON path
  --concurrency Global max concurrent HTTP requests (default: 12)
  --timeout     Per-request timeout seconds (default: 12)
  --langs       Optional comma-separated whitelist of lang codes to process
"""

import argparse
import json
import sys
import time
import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
try:
    from urllib3.util.retry import Retry
except Exception:
    # requests<2.26 vendored path; best effort
    from urllib3.util import Retry  # type: ignore

BOOK_SLUGS = [
    "1-ne","2-ne","jacob","enos","jarom","omni",
    "w-of-m","mosiah","alma","hel","3-ne","4-ne","morm","ether","moro",
]

BOOK_TITLE_URL = "https://www.churchofjesuschrist.org/study/scriptures/bofm/{slug}/1?lang={lang}"
UA = "Mozilla/5.0 (compatible; BookNameCrawler/1.0; +https://example.local)"

CHAPTER_WORDS = [
    # English & Romance
    "chapter","capítulo","capitulo","chapitre","capitolo","capítol",
    # Germanic / Nordic
    "kapitel","kapittel","hoofstuk","hoofdstuk",
    # Slavic (romanized) and Cyrillic
    "glava","глава","глава́","раздел",
    # Misc common variants
    "cap","cap\u00edtulo",
]

def clean_spaces(s: str) -> str:
    # Normalize NBSP, thin space and stray 'Â' (mojibake), compress whitespace
    s = s.replace("\u00A0", " ").replace("\u202F", " ").replace("\u00C2", "")
    return " ".join(s.split()).strip()

def strip_trailing_chapter(text: str) -> str:
    parts = text.split()
    if parts and parts[-1].isdigit():
        parts = parts[:-1]
    return " ".join(parts)

def strip_leading_chapter_phrase(text: str) -> str:
    """
    Remove leading 'Chapter 1 ' / 'Capítulo 1 ' if the page title leaks a chapter heading.
    Also drop any synopsis after an em/en/normal dash.
    """
    t = clean_spaces(text)
    t = re.split(r"\s+[—–-]\s+", t)[0]
    words = "|".join(sorted(set(CHAPTER_WORDS), key=len, reverse=True))
    pat = re.compile(rf"^(?:{words})\s*\d+\s+", re.IGNORECASE | re.UNICODE)
    return pat.sub("", t).strip()

def extract_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    cand = soup.select_one('span[class*="contentTitle"] div')
    if cand and cand.get_text(strip=True):
        return cand.get_text(strip=True)
    cand = soup.select_one("h1 span.dominant")
    if cand and cand.get_text(strip=True):
        return cand.get_text(strip=True)
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return og["content"].strip()
    return "<UNKNOWN>"

def fetch_book_title(session: requests.Session, slug: str, lang: str, timeout: int) -> str:
    url = BOOK_TITLE_URL.format(slug=slug, lang=lang)
    r = session.get(url, timeout=timeout, headers={"User-Agent": UA})
    if r.status_code == 404:
        return ""  # treat not available as empty to skip
    r.raise_for_status()
    raw_html = r.content.decode("utf-8", errors="replace")
    title = extract_title(raw_html)
    title = strip_leading_chapter_phrase(title)
    title = clean_spaces(strip_trailing_chapter(clean_spaces(title)))
    # final sanity: drop obvious non-titles
    if not title or title == "<UNKNOWN>":
        return ""
    return title

def build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3, backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=100, pool_maxsize=100)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

def process_languages(languages_path: str, out_path: str, concurrency: int, timeout: int, whitelist: set[str] | None):
    with open(languages_path, "r", encoding="utf-8") as f:
        langs_list = json.load(f)
    if not isinstance(langs_list, list):
        raise SystemExit("languages.json must be an array of objects with a 'code' key.")

    codes = [entry.get("code") for entry in langs_list if isinstance(entry, dict) and entry.get("code")]
    # Optional whitelist
    if whitelist:
        codes = [c for c in codes if c in whitelist]

    session = build_session()
    started = time.time()
    results: dict[str, dict[str, str]] = {}

    # We run tasks per (lang, slug) with global concurrency control
    tasks = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for lang in codes:
            for slug in BOOK_SLUGS:
                tasks.append(pool.submit(fetch_book_title, session, slug, lang, timeout))

        # Walk tasks in submission order but harvest as they complete
        idx = 0
        for future in as_completed(tasks):
            # Map future back to its (lang, slug)
            # Because we queued in a deterministic order, we can reconstruct indices
            i = idx
            idx += 1
            # But deterministic reconstruction is messy. Better: store metadata on each future.
            # (We’ll recreate submission with metadata below.)
            pass

def process_languages_fast(languages_path: str, out_path: str, concurrency: int, timeout: int, whitelist: set[str] | None):
    with open(languages_path, "r", encoding="utf-8") as f:
        langs_list = json.load(f)
    if not isinstance(langs_list, list):
        raise SystemExit("languages.json must be an array of objects with a 'code' key.")

    codes = [entry.get("code") for entry in langs_list if isinstance(entry, dict) and entry.get("code")]
    if whitelist:
        codes = [c for c in codes if c in whitelist]

    session = build_session()
    started = time.time()
    results: dict[str, dict[str, str]] = {}

    def submit(pool):
        futures = []
        for lang in codes:
            for slug in BOOK_SLUGS:
                fut = pool.submit(fetch_book_title, session, slug, lang, timeout)
                fut._meta = (lang, slug)  # attach metadata (safe in CPython)
                futures.append(fut)
        return futures

    completed = 0
    total = max(1, len(codes) * len(BOOK_SLUGS))
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = submit(pool)
        for fut in as_completed(futures):
            lang, slug = fut._meta  # type: ignore[attr-defined]
            try:
                title = fut.result()
            except Exception as e:
                title = ""
                # Optionally log: print(f"[warn] {lang}/{slug}: {e}", file=sys.stderr)

            if title:
                results.setdefault(lang, {})[slug] = title
            completed += 1
            if completed % 20 == 0 or completed == total:
                pct = completed * 100 // total
                elapsed = time.time() - started
                print(f"[{pct:3d}%] {completed}/{total} done ({elapsed:.1f}s)", file=sys.stderr)

    payload = results
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(results)} languages to {out_path} in {time.time()-started:.1f}s")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--languages", required=True, help="Path to languages.json")
    ap.add_argument("--out", required=True, help="Output booksnames.json path")
    ap.add_argument("--concurrency", type=int, default=12, help="Global max concurrent requests")
    ap.add_argument("--timeout", type=int, default=12, help="Per-request timeout seconds")
    ap.add_argument("--langs", default="", help="Comma-separated whitelist of lang codes to process (optional)")
    args = ap.parse_args()

    whitelist = set([c.strip() for c in args.langs.split(",") if c.strip()]) if args.langs else None
    process_languages_fast(args.languages, args.out, args.concurrency, args.timeout, whitelist)

if __name__ == "__main__":
    main()
