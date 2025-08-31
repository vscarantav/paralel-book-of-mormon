// Shared data
const BOOK_META = [
  { abbr: "1-ne", chapters: 22 },
  { abbr: "2-ne", chapters: 33 },
  { abbr: "jacob", chapters: 7 },
  { abbr: "enos", chapters: 1 },
  { abbr: "jarom", chapters: 1 },
  { abbr: "omni", chapters: 1 },
  { abbr: "w-of-m", chapters: 1 },
  { abbr: "mosiah", chapters: 29 },
  { abbr: "alma", chapters: 63 },
  { abbr: "hel", chapters: 16 },
  { abbr: "3-ne", chapters: 30 },
  { abbr: "4-ne", chapters: 1 },
  { abbr: "morm", chapters: 9 },
  { abbr: "ether", chapters: 15 },
  { abbr: "moro", chapters: 10 },
];

// Utilities
function params() { return new URLSearchParams(window.location.search); }
function q(sel) { return document.querySelector(sel); }
function setBackLink() {
  const main = params().get("main");
  const second = params().get("second");
  const back = q("#back-link");
  if (back) back.href = `books.html?main=${encodeURIComponent(main || "por")}&second=${encodeURIComponent(second || "fra")}`;
}

// ------------------------------
// BOOKS PAGE
// ------------------------------
async function renderBooksPage() {
  const container = document.getElementById("book-list");
  if (!container) return;

  const main = params().get("main") || "por";
  const second = params().get("second") || "fra";

  // Fetch localized book names (silent fallback to slugs)
  let localized = {};
  try {
    const resp = await fetch(`/api/books?lang=${encodeURIComponent(main)}`, { cache: "no-store" });
    if (resp.ok) {
      const data = await resp.json();
      if (data && Array.isArray(data.books)) {
        for (const b of data.books) {
          if (b && b.abbr) localized[b.abbr] = (b.name || "").trim();
        }
      }
    }
  } catch (_) { /* silent fallback */ }

  // Chapter label from booksnames.json (silent fallback to "Chapter")
  let chapterWord = "Chapter";
  try {
    const res = await fetch("/booksnames.json", { cache: "no-store" });
    if (res.ok) {
      const all = await res.json();
      const ch = all?.[main]?.chapter?.toString().trim();
      const looksLikeWord =
        /[A-Za-z\u00C0-\u024F\u0370-\u03FF\u0400-\u04FF\u0590-\u06FF\u0900-\u097F]/.test(ch || "") ||
        /[\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]/.test(ch || "");
      if (ch && looksLikeWord) chapterWord = ch;
    }
  } catch (_) { /* silent fallback */ }

  const isCJK = /[\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]/.test(chapterWord);
  const makeChapterLabel = (n) => (isCJK ? `${n}${chapterWord}` : `${chapterWord} ${n}`);

  // Render list
  for (const meta of BOOK_META) {
    const displayName =
      localized[meta.abbr] && !localized[meta.abbr].startsWith("<")
        ? localized[meta.abbr]
        : meta.abbr.toUpperCase();

    const bookHeader = document.createElement("h2");
    bookHeader.textContent = displayName;
    container.appendChild(bookHeader);

    const ul = document.createElement("ul");
    for (let i = 1; i <= meta.chapters; i++) {
      const li = document.createElement("li");
      const link = document.createElement("a");
      link.href = `chapter.html?book=${meta.abbr}&chapter=${i}&main=${main}&second=${second}`;
      link.textContent = makeChapterLabel(i);
      li.appendChild(link);
      ul.appendChild(li);
    }
    container.appendChild(ul);
  }
}

// ------------------------------
// Helpers for chapter meta rows
// ------------------------------
function escapeHtml(s = "") {
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function prependMetaRow(container, label, leftText, rightText) {
  if (!container) return;

  const L = (leftText  ?? "").toString().trim();
  const R = (rightText ?? "").toString().trim();
  if (!L && !R) return;

  const row = document.createElement("div");
  row.className = "verse-row meta-row";

  const left = document.createElement("div");
  left.className = "verse-col";
  left.innerHTML = L
    ? `<div class="meta-text">${escapeHtml(L)}</div>`
    : `<div class="meta-text" style="opacity:.5">—</div>`;

  const right = document.createElement("div");
  right.className = "verse-col";
  right.innerHTML = R
    ? `<div class="meta-text">${escapeHtml(R)}</div>`
    : `<div class="meta-text" style="opacity:.5">—</div>`;

  row.appendChild(left);
  row.appendChild(right);
  container.insertBefore(row, container.firstChild);
}

// ------------------------------
// CHAPTER PAGE
// ------------------------------
async function loadChapter() {
  if (!window.location.pathname.endsWith("chapter.html")) return;

  setBackLink();

  const p = params();
  const book = p.get("book");
  const chapter = p.get("chapter");
  const main = p.get("main") || "spa";
  const second = p.get("second") || "eng";
  const bookKey = (book || "").trim().toLowerCase();
  const chNum = parseInt(chapter, 10) || 0;

  // Localized book names for header (silent fallback to slug)
  let localized = {};
  try {
    const resp = await fetch(`/api/books?lang=${encodeURIComponent(main)}`, { cache: "no-store" });
    if (resp.ok) {
      const data = await resp.json();
      if (data && Array.isArray(data.books)) {
        for (const b of data.books) {
          if (b && b.abbr) localized[b.abbr] = (b.name || "").trim();
        }
      }
    }
  } catch (_) { /* silent fallback */ }

  // Chapter label for header (localized; silent fallback)
  let chapterWord = "Chapter";
  try {
    const res = await fetch("/booksnames.json", { cache: "no-store" });
    if (res.ok) {
      const all = await res.json();
      const ch = all?.[main]?.chapter?.toString().trim();
      const looksLikeWord =
        /[A-Za-z\u00C0-\u024F\u0370-\u03FF\u0400-\u04FF\u0590-\u06FF\u0900-\u097F]/.test(ch || "") ||
        /[\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]/.test(ch || "");
      if (ch && looksLikeWord) chapterWord = ch;
    }
  } catch (_) { /* silent fallback */ }

  const isCJK = /[\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]/.test(chapterWord);
  const makeChapterLabel = (n) => (isCJK ? `${n}${chapterWord}` : `${chapterWord} ${n}`);

  const displayName =
    localized[book] && !localized[book].startsWith("<")
      ? localized[book]
      : (book || "").toUpperCase();

  const headerEl = document.getElementById("chapter-title");
  if (headerEl) {
  headerEl.innerHTML = `
    <span class="book-name">${displayName}</span>
    <span class="chapter-sep"> – </span>
    <span class="chapter-name">${makeChapterLabel(chapter)}</span>
  `;
}

  // Prev/Next buttons
  const bookMeta = BOOK_META.find(b => b.abbr === book);
  const prevBtn = document.getElementById("prev-chapter");
  const nextBtn = document.getElementById("next-chapter");

  const currentChapter = parseInt(chapter, 10);
  const totalChapters = bookMeta ? bookMeta.chapters : 0;
  const bookIndex = BOOK_META.findIndex(b => b.abbr === book);

  let nextBookAbbr = book;
  let nextChapterNum = currentChapter + 1;
  if (currentChapter >= totalChapters) {
    const nb = (bookIndex + 1) % BOOK_META.length;
    nextBookAbbr = BOOK_META[nb].abbr;
    nextChapterNum = 1;
  }

  let prevBookAbbr = book;
  let prevChapterNum = currentChapter - 1;
  if (currentChapter <= 1) {
    const pb = (bookIndex - 1 + BOOK_META.length) % BOOK_META.length;
    prevBookAbbr = BOOK_META[pb].abbr;
    prevChapterNum = BOOK_META[pb].chapters;
  }

  if (prevBtn) {
    prevBtn.href = `chapter.html?book=${prevBookAbbr}&chapter=${prevChapterNum}&main=${main}&second=${second}`;
    prevBtn.removeAttribute("aria-disabled");
  }
  if (nextBtn) {
    nextBtn.href = `chapter.html?book=${nextBookAbbr}&chapter=${nextChapterNum}&main=${main}&second=${second}`;
    nextBtn.removeAttribute("aria-disabled");
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft" && prevBtn && prevBtn.href) window.location.href = prevBtn.href;
    if (e.key === "ArrowRight" && nextBtn && nextBtn.href) window.location.href = nextBtn.href;
  });

  // Badges/labels
  const badges = document.getElementById("lang-badges");
  if (badges) {
    badges.innerHTML = `
      <span class="badge">Main: ${main.toUpperCase()}</span>
      <span class="badge">Second: ${second.toUpperCase()}</span>`;
  }
  const colLeft = document.getElementById("col-left");
  const colRight = document.getElementById("col-right");
  if (colLeft) colLeft.textContent = `${main.toUpperCase()}`;
  if (colRight) colRight.textContent = `${second.toUpperCase()}`;

  // Verses container
  const container = document.getElementById("verse-container");
  if (!container) { console.warn("No #verse-container found"); return; }

  const getVersesViaProxy = async (lang) => {
    const url = `/api/chapter?book=${encodeURIComponent(book)}&chapter=${encodeURIComponent(chapter)}&lang=${encodeURIComponent(lang)}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`Proxy error: ${resp.status}`);
    const data = await resp.json();
    return data.verses || [];
  };

  let mainVerses = [];
  let secondVerses = [];
  try {
    [mainVerses, secondVerses] = await Promise.all([getVersesViaProxy(main), getVersesViaProxy(second)]);
  } catch (e) {
    console.error("Proxy fetch error:", e);
    if (container) {
      const div = document.createElement("div");
      div.className = "verse-row error";
      div.textContent = "Unable to fetch content via proxy. Make sure the Flask server is running (see README).";
      container.appendChild(div);
    }
    return;
  }

  // 1 Nephi 1: prepend subtitle + introduction rows
  if (bookKey === "1-ne" && chNum === 1) {
    try {
      const [mainExtras, secondExtras] = await Promise.all([
        fetch(`/api/intro?book=${encodeURIComponent(bookKey)}&chapter=${chNum}&lang=${encodeURIComponent(main)}`,   { cache: "no-store" })
          .then(r => (r.ok ? r.json() : { subtitle: "", introduction: "" })),
        fetch(`/api/intro?book=${encodeURIComponent(bookKey)}&chapter=${chNum}&lang=${encodeURIComponent(second)}`, { cache: "no-store" })
          .then(r => (r.ok ? r.json() : { subtitle: "", introduction: "" })),
      ]);

      prependMetaRow(
        container,
        "Introduction",
        (mainExtras.introduction ?? "").toString(),
        (secondExtras.introduction ?? "").toString()
      );
      prependMetaRow(
        container,
        "Book subtitle",
        (mainExtras.subtitle ?? "").toString(),
        (secondExtras.subtitle ?? "").toString()
      );
    } catch (_) { /* silent: meta rows are optional */ }
  }

  // Render verses
  const maxLen = Math.max(mainVerses.length, secondVerses.length);
  for (let i = 0; i < maxLen; i++) {
    const row = document.createElement("div");
    row.className = "verse-row";

    const col1 = document.createElement("div");
    col1.className = "verse-col";
    col1.textContent = mainVerses[i] || "";

    const col2 = document.createElement("div");
    col2.className = "verse-col";
    col2.textContent = secondVerses[i] || "";

    row.appendChild(col1);
    row.appendChild(col2);

    container.appendChild(row);
  }
}

// Router-ish init
document.addEventListener("DOMContentLoaded", () => {
  if (document.getElementById("book-list")) renderBooksPage();
  loadChapter();
});