"""Autonomous background worker and controller for Justapedia Archiver Bot."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bot.article_scanner import ArticleScanner
from bot.citation_parser import CitationParser
from bot.config import config
from bot.database import Database
from bot.logging_config import logger
from bot.mediawiki_client import MediaWikiClient
from bot.reporting import ScanReport
from bot.snapshot_selector import SnapshotSelector


class AutoModeController:
    """Thread-safe background controller for automatic continuous citation archiving."""

    def __init__(self, db: Optional[Database] = None) -> None:
        self.db = db or Database(config.db_path)
        self.state: str = "stopped"  # "stopped", "running", "paused"
        self.running_user: Optional[str] = None
        self.target_category: str = "Living people"
        self.dry_run: bool = True
        self.articles_scanned: int = 0
        self.articles_updated: int = 0
        self.citations_updated: int = 0
        self.current_article: str = ""
        self.start_time: Optional[float] = None
        self.recent_activities: List[Dict[str, Any]] = []

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._lock = threading.Lock()
        self._user_client: Optional[MediaWikiClient] = None

    def log_activity(self, message: str, level: str = "info") -> None:
        """Append to in-memory live activity log for the UI."""
        with self._lock:
            entry = {
                "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                "message": message,
                "level": level,
            }
            self.recent_activities.insert(0, entry)
            if len(self.recent_activities) > 60:
                self.recent_activities.pop()

    def start(
        self,
        username: str,
        user_client: MediaWikiClient,
        category: str = "Living people",
        dry_run: bool = False,
    ) -> bool:
        """Start Auto Mode attributed to the logged-in user."""
        with self._lock:
            if self.state in ("running", "paused"):
                return False

            self.state = "running"
            self.running_user = username
            self.target_category = category
            self.dry_run = dry_run
            self._user_client = user_client
            self.articles_scanned = 0
            self.articles_updated = 0
            self.citations_updated = 0
            self.current_article = "Initializing..."
            self.start_time = time.time()
            self.recent_activities = []

            self._stop_event.clear()
            self._pause_event.clear()

            self._thread = threading.Thread(
                target=self._run_loop, name=f"AutoWorker-{username}", daemon=True
            )
            self._thread.start()

        self.log_activity(
            f"Auto Mode started by user '{username}' on category '{category}' (Live Edit: {not dry_run})"
        )
        return True

    def pause(self) -> bool:
        """Pause the running Auto Mode loop."""
        with self._lock:
            if self.state != "running":
                return False
            self.state = "paused"
            self._pause_event.set()
        self.log_activity("Auto Mode paused by user.", "warning")
        return True

    def resume(self) -> bool:
        """Resume the paused Auto Mode loop."""
        with self._lock:
            if self.state != "paused":
                return False
            self.state = "running"
            self._pause_event.clear()
        self.log_activity("Auto Mode resumed.", "info")
        return True

    def stop(self) -> bool:
        """Stop Auto Mode gracefully."""
        with self._lock:
            if self.state == "stopped":
                return False
            self.state = "stopped"
            self._stop_event.set()
            self._pause_event.clear()
            self.current_article = "Stopped"

        self.log_activity("Auto Mode stopped.", "warning")
        return True

    def get_status(self) -> Dict[str, Any]:
        """Return current real-time telemetry."""
        with self._lock:
            elapsed = (time.time() - self.start_time) if self.start_time else 0.0
            speed = (
                (self.articles_scanned / (elapsed / 60.0))
                if elapsed > 2 and self.articles_scanned > 0
                else 0.0
            )

            return {
                "state": self.state,
                "running_user": self.running_user,
                "target_category": self.target_category,
                "dry_run": self.dry_run,
                "articles_scanned": self.articles_scanned,
                "articles_updated": self.articles_updated,
                "citations_updated": self.citations_updated,
                "current_article": self.current_article,
                "speed_articles_per_minute": round(speed, 1),
                "elapsed_seconds": int(elapsed),
                "recent_activities": list(self.recent_activities[:25]),
            }

    def _run_loop(self) -> None:
        """Background continuous worker loop."""
        logger.info(f"Auto Mode loop started by {self.running_user}")
        scanner = ArticleScanner(
            wiki_client=self._user_client,
            db=self.db,
            dry_run=self.dry_run,
            acting_user=self.running_user,
        )

        dummy_report = ScanReport(
            job_id=f"auto_{int(time.time())}",
            target_type="category",
            target=self.target_category,
            mode="live_edit" if not self.dry_run else "dry_run",
        )

        offset = 0
        batch_size = 25

        while not self._stop_event.is_set():
            # Check pause state
            while self._pause_event.is_set():
                if self._stop_event.is_set():
                    break
                time.sleep(0.5)

            if self._stop_event.is_set():
                break

            # Fetch next batch of category members
            try:
                self.current_article = f"Discovering articles in {self.target_category}..."
                titles = self._user_client.get_category_members(
                    self.target_category, limit=batch_size + offset
                )
                chunk = titles[offset : offset + batch_size]
                if not chunk:
                    self.log_activity("No more articles in category. Completed sweep.", "success")
                    break

                offset += len(chunk)
                # Prefetch wikitext in one batch call
                self.current_article = f"Fetching batch of {len(chunk)} articles..."
                preloaded = self._user_client.get_pages_batch(chunk)

                # Collect and pre-warm URLs and snapshots across chunk for high throughput (> 20 art/min)
                urls_to_prewarm = []
                snapshots_to_prewarm = []
                for t in chunk:
                    p_tuple = preloaded.get(t)
                    if not p_tuple or not p_tuple[0]:
                        continue
                    try:
                        cits = CitationParser.parse_citations(p_tuple[0])
                        for c in cits:
                            if c.url:
                                urls_to_prewarm.append(c.url)
                                if not c.archive_url:
                                    tgt_ts = SnapshotSelector.parse_citation_date_to_timestamp(
                                        c.date or c.access_date
                                    )
                                    snapshots_to_prewarm.append((c.url, tgt_ts))
                    except Exception:
                        pass

                # Pre-fetch concurrently
                if urls_to_prewarm:
                    try:
                        scanner.url_checker.check_urls_parallel(urls_to_prewarm)
                    except Exception:
                        pass

                if snapshots_to_prewarm:
                    try:
                        scanner.archive_client.find_snapshots_parallel(snapshots_to_prewarm)
                    except Exception:
                        pass

                for title in chunk:
                    if self._stop_event.is_set():
                        break

                    while self._pause_event.is_set():
                        if self._stop_event.is_set():
                            break
                        time.sleep(0.5)

                    with self._lock:
                        self.current_article = title

                    try:
                        content = preloaded.get(title)
                        res = scanner.scan_article(
                            title, dummy_report, preloaded_content=content
                        )

                        with self._lock:
                            self.articles_scanned += 1
                            if res.saved:
                                self.articles_updated += 1
                                self.citations_updated += res.citations_updated
                            elif res.has_changes:
                                self.citations_updated += res.citations_updated

                        if self.dry_run:
                            if res.has_changes:
                                self.log_activity(
                                    f"[Dry Run] [[{title}]]: Found +{res.citations_updated} citation(s) to archive.",
                                    "info",
                                )
                            else:
                                self.log_activity(
                                    f"[Dry Run] [[{title}]]: Verified (no changes needed).",
                                    "info",
                                )
                        else:
                            if res.saved:
                                self.log_activity(
                                    f"Saved [[{title}]]: +{res.citations_updated} archive citation(s) (rev {res.revid or 'new'}).",
                                    "success",
                                )
                            elif res.has_changes:
                                if "firewall challenge" in (res.save_error or "").lower():
                                    self.log_activity(
                                        f"[[{title}]]: Found +{res.citations_updated} citation(s) to archive (Saved to Version History; Live edit challenged by Justapedia firewall).",
                                        "warning",
                                    )
                                else:
                                    self.log_activity(
                                        f"Edit challenged on [[{title}]]: {res.save_error or 'MediaWiki rejected edit'}",
                                        "error",
                                    )
                            else:
                                self.log_activity(
                                    f"Scanned [[{title}]]: Verified (no changes needed).",
                                    "info",
                                )

                    except Exception as ex:
                        logger.error(f"Auto Mode error on article '{title}': {ex}")
                        self.log_activity(f"Error scanning [[{title}]]: {ex}", "error")

                    time.sleep(0.04)

            except Exception as e:
                logger.error(f"Auto Mode batch error: {e}")
                self.log_activity(f"Batch fetch error: {e}", "error")
                time.sleep(1.5)

        with self._lock:
            self.state = "stopped"
            self.current_article = "Completed"
        self.log_activity("Auto Mode finished execution.", "info")


# Global singleton controller
auto_controller = AutoModeController()
