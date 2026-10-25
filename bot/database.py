"""SQLite persistence and caching layer for Justapedia Archiver Bot."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from bot.logging_config import logger


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Hash password securely using PBKDF2-HMAC-SHA256 with 100,000 rounds and unique salt."""
    if not salt:
        salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    ).hex()
    return pwd_hash, salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Verify password against stored PBKDF2 hash using constant-time comparison."""
    test_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(stored_hash, test_hash)


class Database:
    """Thread-safe SQLite database manager for caching and job tracking."""

    def __init__(self, db_path: str = "justapedia_archiver.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        """Create necessary tables if they do not exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            # URL Health Check Cache
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS url_cache (
                    url TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    http_code INTEGER,
                    final_url TEXT,
                    checked_at TEXT NOT NULL
                )
                """
            )

            # Internet Archive Snapshot Cache
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshot_cache (
                    url TEXT PRIMARY KEY,
                    snapshot_url TEXT,
                    snapshot_date TEXT,
                    timestamp TEXT,
                    source_api TEXT,
                    found_at TEXT NOT NULL
                )
                """
            )

            # Persistent Jobs
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    target_type TEXT NOT NULL,
                    target TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    articles_scanned INTEGER DEFAULT 0,
                    citations_examined INTEGER DEFAULT 0,
                    urls_checked INTEGER DEFAULT 0,
                    archives_added INTEGER DEFAULT 0,
                    edits_made INTEGER DEFAULT 0,
                    errors_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            # Article History / Checkpoints for Jobs
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_articles (
                    job_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    citations_examined INTEGER DEFAULT 0,
                    citations_updated INTEGER DEFAULT 0,
                    diff TEXT,
                    summary TEXT,
                    processed_at TEXT NOT NULL,
                    PRIMARY KEY (job_id, title)
                )
                """
            )

            # User Authenticated Sessions
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_sessions (
                    token TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    user_id INTEGER,
                    cookies_json TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )

            # OAuth Pending Request Tokens
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_pending_tokens (
                    request_token TEXT PRIMARY KEY,
                    token_secret TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

            # Saved Article Update Versions
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS article_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_title TEXT NOT NULL,
                    version_num INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    previous_wikitext TEXT,
                    updated_wikitext TEXT,
                    diff TEXT,
                    citations_updated INTEGER DEFAULT 0,
                    mediawiki_revid INTEGER,
                    summary TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_versions_title ON article_versions(article_title)"
            )

            # Application Users (Secure Password Hashing)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    justapedia_user_id INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_login TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_users_username ON app_users(username)"
            )

            # Seed example credentials user 'Sourav' with password '8636521212@'
            user_row = conn.execute("SELECT id FROM app_users WHERE username = ?", ("Sourav",)).fetchone()
            if not user_row:
                h, s = hash_password("8636521212@")
                now_iso = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    """
                    INSERT INTO app_users (username, password_hash, salt, justapedia_user_id, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("Sourav", h, s, 1, now_iso),
                )
            conn.commit()

    # ------------------ URL Health Cache ------------------

    def get_url_cache(self, url: str, ttl_days: int = 14) -> Optional[Dict[str, Any]]:
        """Retrieve URL health result if present and not expired."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT url, status, http_code, final_url, checked_at FROM url_cache WHERE url = ?",
                (url,),
            ).fetchone()
            if not row:
                return None

            checked_at = datetime.fromisoformat(row["checked_at"])
            if datetime.now(timezone.utc) - checked_at > timedelta(days=ttl_days):
                return None

            return dict(row)

    def set_url_cache(
        self,
        url: str,
        status: str,
        http_code: Optional[int] = None,
        final_url: Optional[str] = None,
    ) -> None:
        """Store or update URL health check result."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO url_cache (url, status, http_code, final_url, checked_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    status=excluded.status,
                    http_code=excluded.http_code,
                    final_url=excluded.final_url,
                    checked_at=excluded.checked_at
                """,
                (url, status, http_code, final_url, now),
            )
            conn.commit()

    # ------------------ Wayback Snapshot Cache ------------------

    def get_snapshot_cache(self, url: str, ttl_days: int = 30) -> Optional[Dict[str, Any]]:
        """Retrieve cached Internet Archive snapshot if present and not expired."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT url, snapshot_url, snapshot_date, timestamp, source_api, found_at FROM snapshot_cache WHERE url = ?",
                (url,),
            ).fetchone()
            if not row:
                return None

            found_at = datetime.fromisoformat(row["found_at"])
            if datetime.now(timezone.utc) - found_at > timedelta(days=ttl_days):
                return None

            return dict(row)

    def set_snapshot_cache(
        self,
        url: str,
        snapshot_url: Optional[str],
        snapshot_date: Optional[str],
        timestamp: Optional[str],
        source_api: str = "availability",
    ) -> None:
        """Store or update snapshot cache result."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO snapshot_cache (url, snapshot_url, snapshot_date, timestamp, source_api, found_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    snapshot_url=excluded.snapshot_url,
                    snapshot_date=excluded.snapshot_date,
                    timestamp=excluded.timestamp,
                    source_api=excluded.source_api,
                    found_at=excluded.found_at
                """,
                (url, snapshot_url, snapshot_date, timestamp, source_api, now),
            )
            conn.commit()

    # ------------------ Job Tracking & Resuming ------------------

    def create_job(
        self,
        job_id: str,
        target_type: str,
        target: str,
        mode: str = "dry_run",
    ) -> None:
        """Register a new job."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, target_type, target, mode, status,
                    articles_scanned, citations_examined, urls_checked,
                    archives_added, edits_made, errors_count,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'running', 0, 0, 0, 0, 0, 0, ?, ?)
                """,
                (job_id, target_type, target, mode, now, now),
            )
            conn.commit()

    def update_job_status(
        self,
        job_id: str,
        status: str,
        articles_scanned: Optional[int] = None,
        citations_examined: Optional[int] = None,
        urls_checked: Optional[int] = None,
        archives_added: Optional[int] = None,
        edits_made: Optional[int] = None,
        errors_count: Optional[int] = None,
    ) -> None:
        """Update job metrics and status."""
        now = datetime.now(timezone.utc).isoformat()
        updates = ["status = ?", "updated_at = ?"]
        params: List[Any] = [status, now]

        for field, val in [
            ("articles_scanned", articles_scanned),
            ("citations_examined", citations_examined),
            ("urls_checked", urls_checked),
            ("archives_added", archives_added),
            ("edits_made", edits_made),
            ("errors_count", errors_count),
        ]:
            if val is not None:
                updates.append(f"{field} = ?")
                params.append(val)

        params.append(job_id)
        with self._get_connection() as conn:
            conn.execute(
                f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?",
                tuple(params),
            )
            conn.commit()

    def record_job_article(
        self,
        job_id: str,
        title: str,
        status: str,
        citations_examined: int = 0,
        citations_updated: int = 0,
        diff: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> None:
        """Record an article processed under a job."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO job_articles (
                    job_id, title, status, citations_examined, citations_updated, diff, summary, processed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, title) DO UPDATE SET
                    status=excluded.status,
                    citations_examined=excluded.citations_examined,
                    citations_updated=excluded.citations_updated,
                    diff=excluded.diff,
                    summary=excluded.summary,
                    processed_at=excluded.processed_at
                """,
                (
                    job_id,
                    title,
                    status,
                    citations_examined,
                    citations_updated,
                    diff,
                    summary,
                    now,
                ),
            )
            conn.commit()

    def get_processed_articles_for_job(self, job_id: str) -> List[str]:
        """Return list of article titles already processed for this job."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT title FROM job_articles WHERE job_id = ?",
                (job_id,),
            ).fetchall()
            return [r["title"] for r in rows]

    def get_latest_job(self, incomplete_only: bool = False) -> Optional[Dict[str, Any]]:
        """Fetch the most recent job, optionally filtering for incomplete ones."""
        query = "SELECT * FROM jobs"
        params: tuple = ()
        if incomplete_only:
            query += " WHERE status IN ('running', 'pending')"
        query += " ORDER BY created_at DESC LIMIT 1"

        with self._get_connection() as conn:
            row = conn.execute(query, params).fetchone()
            return dict(row) if row else None

    def get_recent_jobs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch recent jobs."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_job_articles(self, job_id: str) -> List[Dict[str, Any]]:
        """Fetch all article records for a specific job."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM job_articles WHERE job_id = ? ORDER BY processed_at ASC",
                (job_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_stats(self) -> Dict[str, int]:
        """Return overall database statistics."""
        with self._get_connection() as conn:
            url_count = conn.execute("SELECT COUNT(*) FROM url_cache").fetchone()[0]
            snapshot_count = conn.execute(
                "SELECT COUNT(*) FROM snapshot_cache"
            ).fetchone()[0]
            job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            article_count = conn.execute(
                "SELECT COUNT(*) FROM job_articles"
            ).fetchone()[0]

            return {
                "cached_urls": url_count,
                "cached_snapshots": snapshot_count,
                "total_jobs": job_count,
                "articles_processed": article_count,
            }

    def clear_cache(self) -> None:
        """Clear URL and Snapshot caches."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM url_cache")
            conn.execute("DELETE FROM snapshot_cache")
            conn.commit()

    # ------------------ User Sessions ------------------

    def create_session(
        self,
        token: str,
        username: str,
        user_id: Optional[int] = None,
        cookies: Optional[Dict[str, str]] = None,
        ttl_hours: int = 48,
    ) -> None:
        """Create or replace a user session."""
        import json

        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(hours=ttl_hours)).isoformat()
        cookies_json = json.dumps(cookies or {})

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_sessions (token, username, user_id, cookies_json, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(token) DO UPDATE SET
                    username=excluded.username,
                    user_id=excluded.user_id,
                    cookies_json=excluded.cookies_json,
                    expires_at=excluded.expires_at
                """,
                (token, username, user_id, cookies_json, now.isoformat(), expires_at),
            )
            conn.commit()

    def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate and return session if not expired."""
        import json

        if not token:
            return None

        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT token, username, user_id, cookies_json, created_at, expires_at FROM user_sessions WHERE token = ?",
                (token,),
            ).fetchone()
            if not row:
                return None

            expires_at = datetime.fromisoformat(row["expires_at"])
            if datetime.now(timezone.utc) > expires_at:
                conn.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
                conn.commit()
                return None

            return {
                "token": row["token"],
                "username": row["username"],
                "user_id": row["user_id"],
                "cookies": json.loads(row["cookies_json"] or "{}"),
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
            }

    def delete_session(self, token: str) -> None:
        """Log out / delete session."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
            conn.commit()

    # ------------------ User Authentication & Management ------------------

    def create_or_update_user(
        self, username: str, password: str, justapedia_user_id: int = 1
    ) -> Dict[str, Any]:
        """Create or update a user account with PBKDF2-HMAC-SHA256 password hashing."""
        pwd_hash, salt = hash_password(password)
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO app_users (username, password_hash, salt, justapedia_user_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    password_hash = excluded.password_hash,
                    salt = excluded.salt,
                    justapedia_user_id = excluded.justapedia_user_id
                """,
                (username.strip(), pwd_hash, salt, justapedia_user_id, now_iso),
            )
            conn.commit()
            return self.get_user(username.strip())  # type: ignore

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Fetch user record by username."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, username, password_hash, salt, justapedia_user_id, created_at, last_login FROM app_users WHERE username = ?",
                (username.strip(),),
            ).fetchone()
            return dict(row) if row else None

    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate a user by validating their password against the secure PBKDF2 hash.
        If user does not exist, registers them dynamically with the provided password.
        Returns user dictionary on success, None on invalid credentials.
        """
        clean_user = username.strip()
        user = self.get_user(clean_user)

        if not user:
            # First-time user registration
            logger.info(f"Registering new user '{clean_user}' with secure PBKDF2 hash.")
            user = self.create_or_update_user(clean_user, password)
            return user

        # Verify password against stored hash using constant-time comparison
        is_valid = verify_password(password, user["password_hash"], user["salt"])
        if not is_valid:
            logger.warning(f"Failed password validation attempt for user '{clean_user}'.")
            return None

        # Update last login timestamp
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE app_users SET last_login = ? WHERE id = ?",
                (now_iso, user["id"]),
            )
            conn.commit()

        user["last_login"] = now_iso
        return user

    # ------------------ OAuth Pending Tokens ------------------

    def save_pending_oauth(self, req_token: str, secret: str) -> None:
        """Store pending OAuth 1.0a request token and secret."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO oauth_pending_tokens (request_token, token_secret, created_at)
                VALUES (?, ?, ?)
                """,
                (req_token, secret, now),
            )
            conn.commit()

    def get_pending_oauth_secret(self, req_token: str) -> Optional[str]:
        """Retrieve and remove a pending OAuth request token secret."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT token_secret FROM oauth_pending_tokens WHERE request_token = ?",
                (req_token,),
            ).fetchone()
            if not row:
                return None
            secret = row["token_secret"]
            conn.execute("DELETE FROM oauth_pending_tokens WHERE request_token = ?", (req_token,))
            conn.commit()
            return secret

    # ------------------ Article Version History ------------------

    def save_article_version(
        self,
        article_title: str,
        username: str,
        mode: str,
        previous_wikitext: str,
        updated_wikitext: str,
        diff: str,
        citations_updated: int = 0,
        mediawiki_revid: Optional[int] = None,
        summary: Optional[str] = None,
    ) -> int:
        """Save a new version record for an article and return version ID."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            # Determine next version number for this article
            last_ver = conn.execute(
                "SELECT MAX(version_num) FROM article_versions WHERE article_title = ?",
                (article_title,),
            ).fetchone()[0]
            next_ver = (last_ver or 0) + 1

            cursor = conn.execute(
                """
                INSERT INTO article_versions (
                    article_title, version_num, username, mode,
                    previous_wikitext, updated_wikitext, diff,
                    citations_updated, mediawiki_revid, summary, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article_title,
                    next_ver,
                    username,
                    mode,
                    previous_wikitext,
                    updated_wikitext,
                    diff,
                    citations_updated,
                    mediawiki_revid,
                    summary or "Added Wayback Machine citations",
                    now,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_article_versions(
        self, article_title: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get version history for a specific article or all articles."""
        query = "SELECT * FROM article_versions"
        params: list = []
        if article_title:
            query += " WHERE article_title = ?"
            params.append(article_title)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]

    def get_article_version(self, version_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a specific version by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM article_versions WHERE id = ?", (version_id,)
            ).fetchone()
            return dict(row) if row else None
