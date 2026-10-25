"""Configuration module for Justapedia Wayback Machine Citation Archiver Bot."""

from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load from .env if present
load_dotenv()


class BotConfig(BaseSettings):
    """Bot operational and environmental settings."""

    # MediaWiki Configuration
    wiki_api_url: str = os.getenv("JUSTAPEDIA_API_URL", "https://justapedia.org/api.php")
    wiki_base_url: str = os.getenv("JUSTAPEDIA_BASE_URL", "https://justapedia.org")
    bot_username: str = os.getenv("JUSTAPEDIA_BOT_USERNAME", "")
    bot_password: str = os.getenv("JUSTAPEDIA_BOT_PASSWORD", "")
    session_cookie: str = os.getenv("JUSTAPEDIA_SESSION_COOKIE", "")
    edit_summary: str = os.getenv(
        "JUSTAPEDIA_EDIT_SUMMARY",
        "Bot: Added Wayback Machine archive information to citations",
    )

    # Justapedia OAuth 1.0a Consumer Credentials
    oauth_consumer_token: str = os.getenv(
        "JUSTAPEDIA_OAUTH_CONSUMER_TOKEN", "9b12e5b4377613f6b46d14f8a6c77798"
    )
    oauth_secret_token: str = os.getenv(
        "JUSTAPEDIA_OAUTH_SECRET_TOKEN", "0fb2bbb28cd108462f367149b56ab1748e460251"
    )

    # Developer Information
    developer_name: str = "Sourav Halder"
    developer_email: str = "skhsouravhalder@gmail.com"

    # Internet Archive Endpoints
    wayback_availability_url: str = os.getenv(
        "WAYBACK_AVAILABILITY_URL", "https://archive.org/wayback/available"
    )
    wayback_cdx_url: str = os.getenv(
        "WAYBACK_CDX_URL", "https://web.archive.org/cdx/search/cdx"
    )

    # Database & Storage
    db_path: str = os.getenv("DB_PATH", "justapedia_archiver.db")

    # Networking & High-Speed Rate Limiting (optimized for > 20 articles/min)
    user_agent: str = os.getenv(
        "BOT_USER_AGENT",
        "JustapediaWaybackBot/1.0 (+https://justapedia.org/wiki/Justapedia:Bots; mailto:skhsouravhalder@gmail.com)",
    )
    request_timeout: int = int(os.getenv("BOT_REQUEST_TIMEOUT", "4"))
    url_check_timeout: int = int(os.getenv("BOT_URL_CHECK_TIMEOUT", "2"))
    max_retries: int = int(os.getenv("BOT_MAX_RETRIES", "2"))
    backoff_factor: float = float(os.getenv("BOT_BACKOFF_FACTOR", "0.3"))
    edit_rate_limit: float = float(os.getenv("BOT_EDIT_RATE_LIMIT", "1.5"))  # Safe pacing between live edits
    url_check_rate_limit: float = float(os.getenv("BOT_URL_CHECK_RATE_LIMIT", "0.0"))
    parallel_workers: int = int(os.getenv("BOT_PARALLEL_WORKERS", "20"))

    # Caching TTL in days
    url_cache_ttl_days: int = int(os.getenv("BOT_URL_CACHE_TTL_DAYS", "14"))
    snapshot_cache_ttl_days: int = int(os.getenv("BOT_SNAPSHOT_CACHE_TTL_DAYS", "30"))

    # Default date format preference: "iso" (YYYY-MM-DD), "mdy" (Month D, YYYY), or "preserve"
    date_format_preference: str = os.getenv("BOT_DATE_FORMAT", "preserve")

    model_config = {"arbitrary_types_allowed": True}


# Global default instance
config = BotConfig()
