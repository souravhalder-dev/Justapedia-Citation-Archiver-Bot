"""Original URL health checker module for Justapedia Archiver Bot."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional
from urllib.parse import urlparse
import requests
from requests.adapters import HTTPAdapter

from bot.config import config
from bot.database import Database
from bot.logging_config import logger


class URLStatus(str, Enum):
    """Classification of URL health."""

    WORKING = "working"
    LIKELY_DEAD = "likely_dead"
    INCONCLUSIVE = "inconclusive"
    UNKNOWN = "unknown"


@dataclass
class URLCheckResult:
    """Detailed result of checking an external URL."""

    url: str
    status: URLStatus
    http_code: Optional[int] = None
    final_url: Optional[str] = None
    error_message: Optional[str] = None
    is_cached: bool = False


class URLChecker:
    """Conservative URL health checker with HEAD/GET fallback and caching."""

    def __init__(
        self,
        db: Optional[Database] = None,
        timeout: Optional[int] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        self.db = db or Database(config.db_path)
        self.timeout = timeout or config.url_check_timeout
        self.user_agent = user_agent or config.user_agent
        self.rate_limit_delay = config.url_check_rate_limit
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=40, pool_maxsize=60)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def check_urls_parallel(
        self, urls: List[str], max_workers: int = 12
    ) -> Dict[str, URLCheckResult]:
        """Check multiple URLs concurrently to achieve > 20 articles/minute processing speed."""
        unique_urls = list(set(u.strip() for u in urls if u and u.strip()))
        results: Dict[str, URLCheckResult] = {}
        if not unique_urls:
            return results

        # Resolve cached items first
        uncached = []
        for u in unique_urls:
            cached = self.db.get_url_cache(u, ttl_days=config.url_cache_ttl_days) if self.db else None
            if cached:
                results[u] = URLCheckResult(
                    url=u,
                    status=URLStatus(cached["status"]),
                    http_code=cached.get("http_code"),
                    final_url=cached.get("final_url"),
                    is_cached=True,
                )
            else:
                uncached.append(u)

        if not uncached:
            return results

        workers = min(max_workers, len(uncached), 20)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_url = {executor.submit(self.check_url, u, True): u for u in uncached}
            for future in as_completed(future_to_url):
                u = future_to_url[future]
                try:
                    res = future.result()
                    results[u] = res
                except Exception as e:
                    results[u] = URLCheckResult(
                        url=u,
                        status=URLStatus.INCONCLUSIVE,
                        error_message=str(e),
                    )

        return results

    def is_valid_url(self, url: str) -> bool:
        """Verify URL has valid structure and HTTP/HTTPS scheme."""
        if not url or not isinstance(url, str):
            return False
        clean_url = url.strip()
        try:
            parsed = urlparse(clean_url)
            return parsed.scheme.lower() in ("http", "https") and bool(parsed.netloc)
        except Exception:
            return False

    def check_url(self, url: str, bypass_cache: bool = False) -> URLCheckResult:
        """Check URL health using conservative inspection."""
        clean_url = url.strip()

        if not self.is_valid_url(clean_url):
            return URLCheckResult(
                url=clean_url,
                status=URLStatus.UNKNOWN,
                error_message="Invalid URL structure or scheme",
            )

        # 1. Check cache
        if not bypass_cache and self.db:
            cached = self.db.get_url_cache(clean_url, ttl_days=config.url_cache_ttl_days)
            if cached:
                return URLCheckResult(
                    url=clean_url,
                    status=URLStatus(cached["status"]),
                    http_code=cached.get("http_code"),
                    final_url=cached.get("final_url"),
                    is_cached=True,
                )

        # Rate limit throttling
        if self.rate_limit_delay > 0:
            time.sleep(self.rate_limit_delay)

        # 2. Perform Request (HEAD first, GET fallback)
        res = self._probe_url(clean_url)

        # 3. Cache result
        if self.db and res.status != URLStatus.UNKNOWN:
            self.db.set_url_cache(
                url=clean_url,
                status=res.status.value,
                http_code=res.http_code,
                final_url=res.final_url,
            )

        return res

    def _probe_url(self, url: str) -> URLCheckResult:
        """Probe URL using HEAD with fallback to streaming GET."""
        try:
            # First attempt: HEAD request
            response = self.session.head(
                url,
                timeout=self.timeout,
                allow_redirects=True,
            )

            # If server forbids or does not allow HEAD (405 Method Not Allowed, 501 Not Implemented), retry with GET
            if response.status_code in (405, 501):
                return self._probe_with_get(url)

            return self._classify_status(url, response.status_code, response.url)

        except requests.exceptions.SSLError:
            # SSL errors could be expired certs or firewall: inconclusive
            return URLCheckResult(
                url=url,
                status=URLStatus.INCONCLUSIVE,
                error_message="SSL Certificate validation error",
            )
        except requests.exceptions.Timeout:
            return URLCheckResult(
                url=url,
                status=URLStatus.INCONCLUSIVE,
                error_message="Request connection/read timed out",
            )
        except requests.exceptions.ConnectionError as ce:
            msg = str(ce).lower()
            # Check for domain resolution failures (NameResolutionError / Failed to resolve)
            if "nameresolutionerror" in msg or "failed to resolve" in msg or "getaddrinfo failed" in msg:
                return URLCheckResult(
                    url=url,
                    status=URLStatus.LIKELY_DEAD,
                    error_message="DNS name resolution failed",
                )
            return URLCheckResult(
                url=url,
                status=URLStatus.INCONCLUSIVE,
                error_message="Network connection error",
            )
        except Exception as e:
            logger.debug(f"HEAD check error for {url}: {e}")
            return self._probe_with_get(url)

    def _probe_with_get(self, url: str) -> URLCheckResult:
        """Fallback probe using streaming GET to avoid downloading body content."""
        try:
            with self.session.get(
                url,
                timeout=self.timeout,
                allow_redirects=True,
                stream=True,
            ) as response:
                status_code = response.status_code
                final_url = str(response.url)
                return self._classify_status(url, status_code, final_url)
        except requests.exceptions.SSLError:
            return URLCheckResult(
                url=url,
                status=URLStatus.INCONCLUSIVE,
                error_message="SSL Certificate error on GET",
            )
        except requests.exceptions.Timeout:
            return URLCheckResult(
                url=url,
                status=URLStatus.INCONCLUSIVE,
                error_message="GET request timed out",
            )
        except requests.exceptions.ConnectionError as ce:
            msg = str(ce).lower()
            if "nameresolutionerror" in msg or "failed to resolve" in msg or "getaddrinfo failed" in msg:
                return URLCheckResult(
                    url=url,
                    status=URLStatus.LIKELY_DEAD,
                    error_message="DNS resolution failed on GET",
                )
            return URLCheckResult(
                url=url,
                status=URLStatus.INCONCLUSIVE,
                error_message="Connection failure on GET",
            )
        except Exception as ex:
            return URLCheckResult(
                url=url,
                status=URLStatus.INCONCLUSIVE,
                error_message=f"GET probing error: {ex}",
            )

    def _classify_status(
        self, url: str, status_code: int, final_url: Optional[str]
    ) -> URLCheckResult:
        """Classify HTTP status codes conservatively according to policy."""
        # 2xx / 3xx are working
        if 200 <= status_code < 400:
            return URLCheckResult(
                url=url,
                status=URLStatus.WORKING,
                http_code=status_code,
                final_url=final_url,
            )

        # 404 Not Found and 410 Gone are likely dead
        if status_code in (404, 410):
            return URLCheckResult(
                url=url,
                status=URLStatus.LIKELY_DEAD,
                http_code=status_code,
                final_url=final_url,
            )

        # 403 Forbidden, 429 Too Many Requests, 5xx server errors: inconclusive
        # The site might be blocking bot user agents, rate limiting, or temporarily down.
        if status_code in (401, 403, 429) or 500 <= status_code < 600:
            return URLCheckResult(
                url=url,
                status=URLStatus.INCONCLUSIVE,
                http_code=status_code,
                final_url=final_url,
                error_message=f"HTTP {status_code} response (treated as inconclusive)",
            )

        return URLCheckResult(
            url=url,
            status=URLStatus.INCONCLUSIVE,
            http_code=status_code,
            final_url=final_url,
            error_message=f"HTTP {status_code} status",
        )
