"""Internet Archive Wayback Machine client implementing Availability and CDX APIs."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import requests
from requests.adapters import HTTPAdapter

from bot.config import config
from bot.database import Database
from bot.logging_config import logger


@dataclass
class ArchiveSnapshot:
    """Represents a validated Wayback Machine capture."""

    original_url: str
    archive_url: str
    timestamp: str  # YYYYMMDDhhmmss
    status_code: Optional[int] = 200
    mime_type: Optional[str] = "text/html"
    digest: Optional[str] = None
    source_api: str = "availability"  # "availability" or "cdx"
    is_cached: bool = False


class ArchiveClient:
    """Client for querying the Internet Archive Wayback Machine."""

    def __init__(
        self,
        db: Optional[Database] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        backoff_factor: Optional[float] = None,
    ) -> None:
        self.db = db or Database(config.db_path)
        self.timeout = timeout or config.request_timeout
        self.max_retries = max_retries or config.max_retries
        self.backoff_factor = backoff_factor or config.backoff_factor
        self._mem_cache: Dict[str, Optional[ArchiveSnapshot]] = {}
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=40, pool_maxsize=60)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(
            {
                "User-Agent": config.user_agent,
                "Accept": "application/json",
            }
        )

    def find_snapshots_parallel(
        self, queries: List[Tuple[str, Optional[str]]], max_workers: int = 20
    ) -> Dict[str, Optional[ArchiveSnapshot]]:
        """Query multiple snapshots concurrently for high update throughput."""
        results: Dict[str, Optional[ArchiveSnapshot]] = {}
        if not queries:
            return results

        uncached = []
        for url, ts in queries:
            clean = url.strip()
            # 1. Fast in-memory cache check
            if clean in self._mem_cache:
                results[clean] = self._mem_cache[clean]
                continue

            # 2. SQLite cache check
            cached = self.db.get_snapshot_cache(clean, ttl_days=config.snapshot_cache_ttl_days) if self.db else None
            if cached and cached.get("snapshot_url"):
                snap = ArchiveSnapshot(
                    original_url=clean,
                    archive_url=cached["snapshot_url"],
                    timestamp=cached.get("timestamp") or "",
                    status_code=200,
                    source_api=cached.get("source_api", "cache"),
                    is_cached=True,
                )
                self._mem_cache[clean] = snap
                results[clean] = snap
            else:
                uncached.append((clean, ts))

        if not uncached:
            return results

        workers = min(max_workers, len(uncached), 24)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_url = {
                executor.submit(self.find_best_snapshot, url, ts, True): url
                for url, ts in uncached
            }
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    res = future.result()
                    results[url] = res
                    self._mem_cache[url] = res
                except Exception as e:
                    logger.debug(f"Parallel snapshot fetch error for {url}: {e}")
                    results[url] = None
                    self._mem_cache[url] = None

        return results

    def _execute_request_with_retry(
        self, url: str, params: Dict[str, Any]
    ) -> Optional[requests.Response]:
        """Execute HTTP request with exponential backoff for 429/5xx and timeouts."""
        for attempt in range(self.max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code == 200:
                    return resp
                if resp.status_code in (429, 502, 503, 504):
                    wait = min(0.3 * (2**attempt), 0.6)
                    logger.debug(
                        f"Internet Archive responded with HTTP {resp.status_code}. Retrying in {wait:.1f}s (Attempt {attempt+1}/{self.max_retries})"
                    )
                    time.sleep(wait)
                    continue
                # Other status codes
                logger.debug(f"IA request to {url} returned status {resp.status_code}")
                return resp
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                wait = min(0.3 * (2**attempt), 0.6)
                logger.debug(
                    f"Network error querying Internet Archive: {e}. Retrying in {wait:.1f}s (Attempt {attempt+1}/{self.max_retries})"
                )
                time.sleep(wait)
            except Exception as ex:
                logger.debug(f"Unexpected error querying {url}: {ex}")
                return None

        return None

    def query_availability(
        self, url: str, timestamp: Optional[str] = None
    ) -> Optional[ArchiveSnapshot]:
        """Strategy 1: Availability API lookup (https://archive.org/wayback/available)."""
        clean_url = url.strip()
        params: Dict[str, Any] = {"url": clean_url}
        if timestamp:
            params["timestamp"] = timestamp

        resp = self._execute_request_with_retry(
            config.wayback_availability_url, params=params
        )
        if not resp:
            return None

        try:
            data = resp.json()
        except Exception:
            logger.warning(f"Malformed JSON response from Availability API for {clean_url}")
            return None

        snapshots = data.get("archived_snapshots", {})
        closest = snapshots.get("closest")
        if not closest or not isinstance(closest, dict):
            return None

        # Validate that the snapshot is marked available and returned a 2xx status
        is_available = closest.get("available") is True
        status_str = str(closest.get("status", ""))
        snapshot_url = closest.get("url")
        snapshot_ts = closest.get("timestamp")

        if not is_available or not snapshot_url or not snapshot_ts:
            return None

        # Enforce HTTPS for web.archive.org URLs
        if snapshot_url.startswith("http://web.archive.org"):
            snapshot_url = "https://" + snapshot_url[len("http://") :]

        status_code = int(status_str) if status_str.isdigit() else 200

        # Discard non-200 snapshots from availability
        if status_code < 200 or status_code >= 400:
            return None

        return ArchiveSnapshot(
            original_url=clean_url,
            archive_url=snapshot_url,
            timestamp=snapshot_ts,
            status_code=status_code,
            source_api="availability",
        )

    def query_cdx(
        self,
        url: str,
        target_timestamp: Optional[str] = None,
        limit: int = 20,
    ) -> List[ArchiveSnapshot]:
        """Strategy 2: CDX Server API lookup (https://web.archive.org/cdx/search/cdx)."""
        clean_url = url.strip()
        params: Dict[str, Any] = {
            "url": clean_url,
            "output": "json",
            "fl": "timestamp,original,statuscode,mimetype,digest",
            "filter": ["statuscode:200", "mimetype:text/html"],
            "limit": str(limit),
        }

        # If a target timestamp is given, sort/query around that date
        if target_timestamp:
            params["closest"] = target_timestamp
            params["sort"] = "closest"

        resp = self._execute_request_with_retry(config.wayback_cdx_url, params=params)
        if not resp:
            return []

        try:
            rows = resp.json()
        except Exception:
            logger.warning(f"Malformed JSON response from CDX API for {clean_url}")
            return []

        if not rows or len(rows) < 2:
            return []

        header = rows[0]
        results: List[ArchiveSnapshot] = []

        try:
            ts_idx = header.index("timestamp")
            orig_idx = header.index("original")
            status_idx = header.index("statuscode")
            mime_idx = header.index("mimetype")
            digest_idx = header.index("digest")
        except ValueError:
            return []

        for row in rows[1:]:
            try:
                ts = str(row[ts_idx]).strip()
                orig = str(row[orig_idx]).strip()
                st = int(row[status_idx]) if str(row[status_idx]).isdigit() else 200
                mime = str(row[mime_idx]).strip()
                digest = str(row[digest_idx]).strip()

                # Basic validation
                if len(ts) < 8 or st != 200:
                    continue

                archive_url = f"https://web.archive.org/web/{ts}/{orig}"
                results.append(
                    ArchiveSnapshot(
                        original_url=orig,
                        archive_url=archive_url,
                        timestamp=ts,
                        status_code=st,
                        mime_type=mime,
                        digest=digest,
                        source_api="cdx",
                    )
                )
            except Exception as e:
                logger.debug(f"Error parsing CDX row {row}: {e}")
                continue

        return results

    def find_best_snapshot(
        self,
        url: str,
        target_timestamp: Optional[str] = None,
        bypass_cache: bool = False,
    ) -> Optional[ArchiveSnapshot]:
        """Find best snapshot using Strategy 1 (Availability) with Strategy 2 (CDX) as fallback/precision."""
        clean_url = url.strip()

        # Check in-memory cache
        if not bypass_cache and clean_url in self._mem_cache:
            return self._mem_cache[clean_url]

        # Check DB snapshot cache
        if not bypass_cache and self.db:
            cached = self.db.get_snapshot_cache(
                clean_url, ttl_days=config.snapshot_cache_ttl_days
            )
            if cached and cached.get("snapshot_url"):
                return ArchiveSnapshot(
                    original_url=clean_url,
                    archive_url=cached["snapshot_url"],
                    timestamp=cached.get("timestamp") or "",
                    status_code=200,
                    source_api=cached.get("source_api", "cache"),
                    is_cached=True,
                )

        snapshot: Optional[ArchiveSnapshot] = None

        # Strategy 1: Availability API
        try:
            snapshot = self.query_availability(clean_url, timestamp=target_timestamp)
        except Exception as e:
            logger.warning(f"Availability API error for {clean_url}: {e}")

        # Strategy 2: If Availability API returned nothing or when a specific target timestamp is sought, try CDX
        if not snapshot:
            try:
                cdx_results = self.query_cdx(
                    clean_url, target_timestamp=target_timestamp, limit=10
                )
                if cdx_results:
                    snapshot = cdx_results[0]
            except Exception as e:
                logger.warning(f"CDX API query error for {clean_url}: {e}")

        # Cache result in SQLite if found
        if snapshot and self.db:
            self.db.set_snapshot_cache(
                url=clean_url,
                snapshot_url=snapshot.archive_url,
                snapshot_date=None,  # Will be computed during snapshot selection
                timestamp=snapshot.timestamp,
                source_api=snapshot.source_api,
            )

        self._mem_cache[clean_url] = snapshot
        return snapshot
