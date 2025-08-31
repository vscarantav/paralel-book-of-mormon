# Book of Mormon Parallel Website (Proxy Version)

This version includes a tiny Flask backend that proxies and parses chapter content to avoid CORS issues when fetching from churchofjesuschrist.org.

## Quick Start
1. Create and activate a virtual environment (optional but recommended).
2. Install dependencies:
   ```bash
   pip install flask requests beautifulsoup4
   ```
3. Start the server from this folder:
   ```bash
   python server.py
   ```
4. Open your browser at: http://localhost:5050/

## How it works
- Frontend requests: `/api/chapter?book=1-ne&chapter=1&lang=por`
- The Flask server fetches and parses the chapter HTML server-side and returns JSON verses.
- Pages:
  - `index.html` — language selection
  - `books.html` — choose book & chapter
  - `chapter.html` — two-column parallel view

## Notes
- If you plan to deploy, you can host this on Render, Railway, Fly.io, or any VPS where you can run Python + Flask.
- If you prefer static hosting only, consider pre-generating JSON files for each chapter with a Python script and point the frontend to local `/data/*.json` instead of the proxy.
