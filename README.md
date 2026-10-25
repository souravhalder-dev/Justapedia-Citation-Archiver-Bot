# Justapedia Wayback Machine Citation Archiver Bot

A production-ready MediaWiki citation archiving and link preservation bot for [Justapedia](https://justapedia.org).

It scans Justapedia articles, inspects citations with missing archive parameters or dead links, retrieves historical snapshots from the Internet Archive (using both the **Availability API** and **CDX Server API**), and safely updates citation templates with validated `archive-url`, `archive-date`, and `url-status` parameters without corrupting wikitext.

---

## Developer Information

- **Developer**: Sourav Halder
- **Email**: skhsouravhalder@gmail.com
- **Justapedia OAuth Consumer Token**: `9b12e5b4377613f6b46d14f8a6c77798`
- **Secret Token**: `0fb2bbb28cd108462f367149b56ab1748e460251`

---

## Key Features & Improvements (v2.0)

1. **Authentication Required (Security & Attribution)**:
   - Users must authenticate with their Justapedia account (username & password or MediaWiki Bot Password) before accessing the bot.
   - If not logged in, users are automatically directed to the secure login page.
   - All article edits, summaries, revisions, and automated tasks are strictly recorded and attributed to the **currently logged-in user**.

2. **Automatic Mode (Auto Mode)**:
   - Autonomous background processing loop with **Start**, **Pause**, **Resume**, and **Stop** controls.
   - Continuously traverses category queues (e.g. `Living people`, `Articles with dead external links`) without requiring manual button clicks.
   - Real-time telemetry: articles scanned, updates saved, live activity logs, and current article status.

3. **High-Speed Processing (> 20 Articles / Minute)**:
   - Batch fetching from MediaWiki: requests up to 50 article wikitexts in a single API call instead of sequential round trips.
   - Parallel URL health checking using thread-pool concurrency.
   - Parallel Internet Archive snapshot queries with persistent HTTP connection pooling.
   - Sub-millisecond SQLite cache hits for previously inspected links.

4. **Saved Article Update Versions**:
   - Preserves complete version history in SQLite whenever an article is updated.
   - Users can review previous versions, track who made each change, and inspect side-by-side or unified diffs.

5. **Clean Interface (Settings Option Removed)**:
   - The Settings menu and related UI elements have been completely removed for a streamlined, clutter-free user experience.

---

## Installation & Running on Localhost

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Build the React frontend:**
   ```bash
   npm --prefix frontend install
   npm --prefix frontend run build
   ```

3. **Launch the bot server:**
   ```bash
   python run_server.py
   ```

Open your browser at:
👉 **[http://localhost:8080](http://localhost:8080)**

---

## Command-Line Interface (CLI)

```bash
# Check an article in dry-run mode (safe preview)
python main.py --article "Kevin Gorey" --dry-run

# Batch scan from a file and export JSON report
python main.py --input articles.txt --dry-run --report report.json

# Scan a category with limit
python main.py --category "Living people" --limit 20 --dry-run

# Live edit mode
python main.py --input articles.txt --apply --max-edits 10

# Resume interrupted job
python main.py --resume
```

---

## Automated Test Suite

Run the full pytest suite (49 tests covering authentication, version history, Auto Mode, URL checking, diff generation, and API endpoints):

```bash
python -m pytest -v
```
