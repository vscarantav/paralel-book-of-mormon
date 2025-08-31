# server.py
from flask import Flask, request, jsonify, send_from_directory
from bs4 import BeautifulSoup
from urllib.parse import urlencode, urljoin
import requests
import os
import re
import time
import json
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry



# ----------------------------
# Canonical books & chapters
# ----------------------------
BOOK_SLUGS = [
    "1-ne", "2-ne", "jacob", "enos", "jarom", "omni",
    "w-of-m", "mosiah", "alma", "hel", "3-ne", "4-ne", "morm", "ether", "moro",
]

BOOK_CHAPTERS = {
    "1-ne": 22, "2-ne": 33, "jacob": 7, "enos": 1, "jarom": 1, "omni": 1,
    "w-of-m": 1, "mosiah": 29, "alma": 63, "hel": 16, "3-ne": 30, "4-ne": 1,
    "morm": 9, "ether": 15, "moro": 10,
}

# Where we fetch the *book title* on fallback (chapter 1 per book)
BOOK_TITLE_URL = "https://www.churchofjesuschrist.org/study/scriptures/bofm/{slug}/1?lang={lang}"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# ----------------------------
# Load precomputed localized names
# ----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOOKSNAMES_PATH = os.path.join(BASE_DIR, "booksnames.json")

try:
    with open(BOOKSNAMES_PATH, "r", encoding="utf-8") as f:
        BOOKS_NAMES = json.load(f)   # { "<lang>": { "<slug>": "<Localized Title>", ... }, ... }
except Exception:
    BOOKS_NAMES = {}                 # graceful if file missing/corrupt

def _demojibake(s: str) -> str:
    """
    Fix common 'Ã¼/Ã¤/Ã¶/ÃŸ' style mojibake by assuming the text was
    decoded as latin-1 but is actually UTF-8 bytes.
    Only applies if we detect the telltale 'Ã'/'Â' patterns.
    """
    if not s:
        return s
    # Quick heuristic: contains 'Ã' or 'Â' followed by high-bit chars
    if re.search(r"[ÃÂ][\x80-\xBF]", s):
        try:
            return s.encode("latin-1", "ignore").decode("utf-8", "ignore")
        except Exception:
            return s
    return s

# ----------------------------
# Utilities & normalizers
# ----------------------------
def _clean_spaces(s: str) -> str:
    # Normalize NBSP/thin-space and strip stray 'Â' from mojibake
    s = s.replace("\u00A0", " ").replace("\u202F", " ").replace("\u00C2", "")
    return " ".join(s.split()).strip()

def _strip_trailing_chapter(text: str) -> str:
    # Some locales put a lonely trailing "1" after the title; drop a final bare integer token
    parts = text.split()
    if parts and parts[-1].isdigit():
        parts = parts[:-1]
    return " ".join(parts)

from urllib.parse import urlencode, urljoin

from urllib.parse import urljoin

def fetch_1ne1_extras(lang: str) -> dict:
    base_url = "https://www.churchofjesuschrist.org/study/scriptures/bofm/1-ne/1"
    page_url = f"{base_url}?{urlencode({'lang': lang})}"

    r = _session.get(page_url, headers={"User-Agent": "Mozilla/5.0 (compatible; 1ne1-extractor/1.0)"}, timeout=20)
    r.raise_for_status()
    outer = BeautifulSoup(r.content, "html.parser")

    # --- choose the real document to parse ---
    doc_soup = outer

    # a) srcdoc path (some locales still use it)
    iframe = outer.select_one('iframe[srcdoc]')
    if iframe and iframe.has_attr("srcdoc"):
        doc_soup = BeautifulSoup(iframe["srcdoc"], "html.parser")
    else:
        # b) explicit scripture iframe[src]; avoid login/silent and similar
        # Prefer the iframe that lives under the content section
        iframe = (
            outer.select_one('section#content iframe[src*="/study/scriptures/"]')
            or outer.select_one('iframe[src*="/study/scriptures/"]')
        )

        # Fallback: pick the first iframe[src] that does NOT contain "login" or "silent"
        if not iframe:
            for cand in outer.select('iframe[src]'):
                src = cand.get("src", "")
                if "login" in src or "silent" in src:
                    continue
                iframe = cand
                break

        if iframe and iframe.has_attr("src"):
            iframe_url = urljoin(page_url, iframe["src"])
            ri = _session.get(iframe_url, headers={"User-Agent": "Mozilla/5.0 (compatible; 1ne1-extractor/1.0)"}, timeout=20)
            ri.raise_for_status()
            doc_soup = BeautifulSoup(ri.content, "html.parser")

    # --- robust selectors for the two blocks ---
    subtitle_el = doc_soup.select_one('p.subtitle, [id^="subtitle"], [data-aid^="subtitle"]')
    intro_el    = doc_soup.select_one('p.intro, [id^="intro"], [data-aid^="intro"]')

    subtitle = _clean_spaces(" ".join(subtitle_el.stripped_strings)) if subtitle_el else ""
    introduction = _clean_spaces(" ".join(intro_el.stripped_strings)) if intro_el else ""

    subtitle = _demojibake(subtitle)
    introduction = _demojibake(introduction)
    app.logger.info(f"/api/intro {lang}: subtitle='{subtitle[:60]}' intro_len={len(introduction)}")
    return {"subtitle": subtitle, "introduction": introduction}



# Common localized words meaning "Chapter" for leading "Chapter 1 " sequences.
CHAPTER_WORDS = [
    # English & Romance
    "chapter", "capítulo", "capitulo", "chapitre", "capitolo", "capítol",
    # Germanic / Nordic
    "kapitel", "kapittel", "hoofstuk", "hoofdstuk",
    # Slavic (romanized) and Cyrillic
    "glava", "глава", "глава́", "раздел",
    # Misc variants
    "cap", "cap\u00edtulo",
]

def _strip_leading_chapter_phrase(text: str) -> str:
    """
    Remove a leading 'Chapter 1 ' / 'Capítulo 1 ' prefix if a page puts
    the chapter heading where we expect the book title. Also drop any summary
    that follows an em/en dash: '—'.
    """
    t = _clean_spaces(text)
    # Drop synopsis after an em/en/normal dash
    t = re.split(r"\s+[—–-]\s+", t)[0]
    words = "|".join(sorted(set(CHAPTER_WORDS), key=len, reverse=True))
    pat = re.compile(rf"^(?:{words})\s*\d+\s+", re.IGNORECASE | re.UNICODE)
    t = pat.sub("", t)
    return t.strip()

# ----------------------------
# Title extraction (fallback)
# ----------------------------
def _extract_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Try the contentTitle region (most consistent on scriptures pages)
    cand = soup.select_one('span[class*="contentTitle"] div')
    if cand and cand.get_text(strip=True):
        return cand.get_text(strip=True)

    # Try dominant H1 span
    cand = soup.select_one("h1 span.dominant")
    if cand and cand.get_text(strip=True):
        return cand.get_text(strip=True)

    # Plain h1 fallback
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)

    # og:title fallback (less ideal but better than nothing)
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return og["content"].strip()

    return "<UNKNOWN>"

def _fetch_book_title(slug: str, lang: str) -> str:
    """
    Fallback only: fetch chapter 1, decode UTF-8, extract canonical title,
    strip leaked 'Chapter 1 ' headings and trailing numbers.
    """
    url = BOOK_TITLE_URL.format(slug=slug, lang=lang)
    r = _session.get(url, headers=HEADERS, timeout=12)
    if r.status_code == 404:
        return "<NOT AVAILABLE>"
    r.raise_for_status()

    raw_html = r.content.decode("utf-8", errors="replace")
    title = _extract_title(raw_html)
    title = _strip_leading_chapter_phrase(title)
    title = _clean_spaces(_strip_trailing_chapter(_clean_spaces(title)))
    return title

# ----------------------------
# /api/books — now served from booksnames.json (with fallback)
# ----------------------------
_BOOKS_CACHE = {}   # { lang: { "at": epoch_seconds, "data": [...] } }
_CACHE_TTL   = 60 * 60 * 24  # 24h

def _get_books_for_lang(lang: str):
    now = time.time()
    hit = _BOOKS_CACHE.get(lang)
    if hit and (now - hit["at"] < _CACHE_TTL):
        return hit["data"]

    names = BOOKS_NAMES.get(lang, {})  # dict of slug->localized title (or empty)
    out = []

    if names:
        # Fast path: build from precomputed names
        for slug in BOOK_SLUGS:
            out.append({
                "abbr": slug,
                "name": names.get(slug, slug.upper()),
                "chapters": BOOK_CHAPTERS[slug],
            })
        _BOOKS_CACHE[lang] = {"at": now, "data": out}
        return out

    # Fallback: compute on the fly (kept for completeness)
    for slug in BOOK_SLUGS:
        out.append({
            "abbr": slug,
            "name": _fetch_book_title(slug, lang),
            "chapters": BOOK_CHAPTERS[slug],
        })
    _BOOKS_CACHE[lang] = {"at": now, "data": out}
    return out

# ----------------------------
# Flask app & routes
# ----------------------------
app = Flask(__name__, static_folder=BASE_DIR, static_url_path='')

# cache static files in browser for 1 day
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 86400

@app.get("/healthz")
def healthz():
    return {"ok": True}

# global requests session with retry
_session = requests.Session()
_retry = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "HEAD"]
)
_session.mount("https://", HTTPAdapter(max_retries=_retry))
_session.mount("http://", HTTPAdapter(max_retries=_retry))

# Proxy target for chapter text
BASE_URL = "https://www.churchofjesuschrist.org/study/scriptures/bofm/{}/{}?lang={}"

@app.route('/api/books')
def api_books():
    lang = request.args.get('lang', 'por').lower().strip()
    try:
        data = _get_books_for_lang(lang)
        return jsonify({"lang": lang, "books": data})
    except Exception as e:
        return jsonify({"error": f"Failed to load books for {lang}: {e}"}), 500

@app.route('/')
def root():
    return app.send_static_file('index.html')

@app.route('/<path:path>')
def static_proxy(path):
    return send_from_directory(BASE_DIR, path)

@app.route('/api/chapter')
def api_chapter():
    # Unchanged: your working chapter proxy/parse flow
    book = request.args.get('book')
    chapter = request.args.get('chapter')
    lang = request.args.get('lang', 'por')

    if not book or not chapter:
        return jsonify({"error": "Missing 'book' or 'chapter' parameter"}), 400

    url = BASE_URL.format(book, chapter, lang)
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = _session.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        return jsonify({"error": f"Upstream fetch failed: {e}"}), 502

    # Parse the fetched HTML
    soup = BeautifulSoup(resp.content, 'html.parser')

    verses = []
    for v in soup.select('p.verse'):
        # main verse number
        num_tag = v.select_one('.verse-number')
        num = num_tag.get_text(strip=True) if num_tag else ''

        # remove ALL verse-number spans
        for t in v.select('.verse-number'):
            t.decompose()

        # extract cleaned verse text
        text = v.get_text(" ", strip=True)

        # remove any duplicate number at the start of the text
        if num:
            text = re.sub(rf'^\s*{re.escape(num)}[\s\.\u00A0:\-–—]*', '', text)

        # remove spaces before punctuation
        text = re.sub(r'\s+([,.;:!?…\)\]\}”’†])', r'\1', text)

        verses.append(f"{num} {text}".strip())

    return jsonify({"verses": verses, "book": book, "chapter": chapter, "lang": lang})

@app.get("/api/intro")
def api_intro():
    book = request.args.get("book", "").strip().lower()
    chapter = request.args.get("chapter", type=int)
    lang = request.args.get("lang", "eng").strip().lower()

    if book != "1-ne" or chapter != 1:
        return jsonify({"subtitle": "", "introduction": ""})

    try:
        data = fetch_1ne1_extras(lang)
        return jsonify(data)
    except Exception as e:
        # Don’t fail the chapter page if scraping hiccups; just return empty
        app.logger.warning(f"/api/intro error for lang={lang}: {e}")
        return jsonify({"subtitle": "", "introduction": ""})

if __name__ == '__main__':
    # Render/Heroku/etc. set PORT in the environment
    port = int(os.getenv("PORT", "5050"))
    app.run(host='0.0.0.0', port=port, debug=False)
