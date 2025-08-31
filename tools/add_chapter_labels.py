#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Adds/refreshes localized "chapter" labels in booksnames.json by fetching
/bofm/1-ne/1?lang=<code> and reading <p class="title-number">.

Usage:
  python tools/add_chapter_labels.py \
    --languages ./languages.json \
    --books ./booksnames.json \
    --out ./booksnames.json
"""

import argparse, json, os, re, sys, unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional, Set

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
try:
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover
    from urllib3.util import Retry  # type: ignore

# Fetch the *chapter page* directly
CHAPTER_URL = "https://www.churchofjesuschrist.org/study/scriptures/bofm/1-ne/1?lang={lang}"
UA = "Mozilla/5.0 (compatible; ChapterLabelCrawler/2.0)"

# ---------- helpers ----------

def clean_spaces(s: str) -> str:
    s = s.replace("\u00A0", " ").replace("\u202F", " ").replace("\u00C2", "")
    return " ".join(s.split()).strip()

def is_cjk_or_hangul(ch: str) -> bool:
    o = ord(ch)
    return (
        0x4E00 <= o <= 0x9FFF or   # CJK
        0x3400 <= o <= 0x4DBF or   # CJK Ext A
        0x3040 <= o <= 0x30FF or   # Hiragana/Katakana
        0xAC00 <= o <= 0xD7AF      # Hangul
    )

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
    s.headers.update({"User-Agent": UA})
    return s

# ---------- core extraction ----------

def extract_label_from_title_number_text(text: str) -> str:
    """
    Given the innerText of <p class="title-number"> (e.g., "CHAPTER 1",
    "Capítulo 1", "第 1 章", "الفصل ١"), return the localized word for 'chapter'.
    """
    t = clean_spaces(text)
    if not t:
        return ""

    # Normalize any unicode digits to ASCII '1' by just matching \d+
    # Prefer CJK/Hangul suffix after the number: "第 1 章" / "1章" -> "章"
    m_suf = re.search(r"\d+\s*([^\s\dA-Za-z\u00C0-\u024F\u0370-\u03FF\u0400-\u04FF]{1,3})", t, re.UNICODE)
    if m_suf:
        suf = clean_spaces(m_suf.group(1))
        if suf and any(is_cjk_or_hangul(ch) for ch in suf):
            return suf

    # Otherwise, take the letters *before* the number: "Capítulo 1" -> "Capítulo"
    m_pre = re.match(r"^\s*([^\d]+?)\s*\d+\s*$", t, re.UNICODE)
    if m_pre:
        return clean_spaces(m_pre.group(1))

    # Last resort: strip digits and pick a short leftover token
    t2 = clean_spaces(re.sub(r"\d+", " ", t))
    # If result contains CJK/Hangul, prefer the last CJK/Hangul char(s)
    cjk = "".join(ch for ch in t2 if is_cjk_or_hangul(ch))
    if cjk:
        return cjk[-1]  # likely "章", "장" etc.
    # Else take the first word
    return t2.split()[0] if t2 else ""

def extract_label_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Primary: <p class="title-number">
    p = soup.select_one("p.title-number")
    if p and p.get_text(strip=True):
        return extract_label_from_title_number_text(p.get_text(" ", strip=True))

    # Fallbacks seen occasionally:
    # Some themes wrap it in <span class="title-number"> or an <h2> variant
    p2 = soup.select_one(".title-number")
    if p2 and p2.get_text(strip=True):
        return extract_label_from_title_number_text(p2.get_text(" ", strip=True))

    # Nothing found
    return ""

def fetch_label(session: requests.Session, lang: str, timeout: int) -> str:
    r = session.get(CHAPTER_URL.format(lang=lang), timeout=timeout)
    if r.status_code == 404:
        return ""
    r.raise_for_status()
    html = r.content.decode("utf-8", errors="replace")
    return extract_label_from_html(html)

# ---------- pipeline ----------

def run(languages_path: str, books_path: Optional[str], out_path: str,
        concurrency: int, timeout: int, whitelist: Optional[Set[str]]) -> None:
    # languages.json: array of { "code": "eng", ... }
    with open(languages_path, "r", encoding="utf-8") as f:
        langs_list = json.load(f)
    codes = [e.get("code") for e in langs_list if isinstance(e, dict) and e.get("code")]
    if whitelist:
        codes = [c for c in codes if c in whitelist]
    if not codes:
        raise SystemExit("No language codes found.")

    # booksnames.json: { "<lang>": { "<slug>": "<title>", ... }, ... }
    base: Dict[str, Dict] = {}
    if books_path and os.path.exists(books_path):
        try:
            with open(books_path, "r", encoding="utf-8") as f:
                base = json.load(f)
                if not isinstance(base, dict):
                    base = {}
        except Exception:
            base = {}

    session = build_session()
    results: Dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        fut_to_lang = {pool.submit(fetch_label, session, lang, timeout): lang for lang in codes}
        done = 0
        total = len(fut_to_lang)
        for fut in as_completed(fut_to_lang):
            lang = fut_to_lang[fut]
            try:
                label = fut.result()
            except Exception as e:
                label = ""
                print(f"[warn] {lang}: {e}", file=sys.stderr)
            if label:
                results[lang] = label
            done += 1
            if done % 20 == 0 or done == total:
                print(f"[{done}/{total}] processed", file=sys.stderr)

    # Merge: write "chapter" into each language block if found
    for lang in codes:
        d = base.setdefault(lang, {})
        if results.get(lang):
            d["chapter"] = results[lang]

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=2)
    print(f"Wrote {out_path} with {len(results)} chapter labels.", file=sys.stderr)

# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--languages", required=True, help="Path to languages.json (array of {code,...})")
    ap.add_argument("--books", default="./booksnames.json", help="Path to existing booksnames.json to merge (optional)")
    ap.add_argument("--out", required=True, help="Output path (e.g., ./booksnames.json)")
    ap.add_argument("--concurrency", type=int, default=12, help="Concurrent HTTP requests (default: 12)")
    ap.add_argument("--timeout", type=int, default=12, help="Per-request timeout seconds (default: 12)")
    ap.add_argument("--langs", default="", help="Comma-separated whitelist (e.g., eng,spa,por)")
    args = ap.parse_args()

    whitelist = set([c.strip() for c in args.langs.split(",") if c.strip()]) if args.langs else None
    run(args.languages, args.books, args.out, args.concurrency, args.timeout, whitelist)

if __name__ == "__main__":
    main()
