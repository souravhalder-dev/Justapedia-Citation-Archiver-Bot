"""Snapshot selection and date formatting logic for Wayback Machine captures."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from dateutil import parser as date_parser

from bot.archive_client import ArchiveSnapshot
from bot.logging_config import logger


class SnapshotSelector:
    """Selects the most suitable Wayback Machine snapshot and formats archive dates."""

    # Regex to extract timestamp from a standard Wayback URL: /web/(\d{4,14})[a-z_]*/
    WAYBACK_URL_REGEX = re.compile(
        r"https?://web\.archive\.org/web/(\d{4,14})(?:[a-z]{2}_)?/(https?://.+)",
        re.IGNORECASE,
    )

    MONTH_NAMES = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]

    @classmethod
    def parse_citation_date_to_timestamp(cls, date_str: Optional[str]) -> Optional[str]:
        """Convert a citation date string into a YYYYMMDD timestamp string."""
        if not date_str or not isinstance(date_str, str):
            return None

        clean = date_str.strip()
        # Remove wiki links if present: [[2020-06-15]] or [[15 June]] [[2020]]
        clean = re.sub(r"\[\[([^\|\]]+\|)?([^\]]+)\]\]", r"\2", clean).strip()

        # Try 4-digit year only
        if re.fullmatch(r"\d{4}", clean):
            return f"{clean}0101"

        try:
            dt = date_parser.parse(clean, fuzzy=True)
            return dt.strftime("%Y%m%d")
        except Exception:
            # Fallback regex for YYYY-MM-DD or DD-MM-YYYY
            m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", clean)
            if m:
                y, mon, d = m.groups()
                return f"{int(y):04d}{int(mon):02d}{int(d):02d}"
            return None

    @classmethod
    def detect_date_style(cls, date_str: Optional[str]) -> str:
        """Detect date format style: 'iso', 'mdy', or 'dmy'."""
        if not date_str:
            return "iso"
        clean = date_str.strip()
        # ISO format: 2020-06-15
        if re.search(r"^\d{4}-\d{2}-\d{2}$", clean):
            return "iso"
        # Month D, YYYY: June 15, 2020
        month_pattern = "|".join(cls.MONTH_NAMES)
        if re.search(rf"^({month_pattern})\s+\d{{1,2}},\s+\d{{4}}$", clean, re.IGNORECASE):
            return "mdy"
        # D Month YYYY: 15 June 2020
        if re.search(rf"^\d{{1,2}}\s+({month_pattern})\s+\d{{4}}$", clean, re.IGNORECASE):
            return "dmy"
        return "iso"

    @classmethod
    def format_timestamp_to_date(
        cls,
        timestamp: str,
        style: str = "iso",
    ) -> Optional[str]:
        """Convert a 8..14 digit Wayback timestamp (YYYYMMDDhhmmss) into a formatted date string."""
        if not timestamp or len(timestamp) < 8:
            return None

        try:
            year = int(timestamp[0:4])
            month = int(timestamp[4:6])
            day = int(timestamp[6:8])
            dt = datetime(year, month, day)
        except Exception:
            return None

        if style == "mdy":
            month_name = cls.MONTH_NAMES[dt.month - 1]
            return f"{month_name} {dt.day}, {dt.year}"
        elif style == "dmy":
            month_name = cls.MONTH_NAMES[dt.month - 1]
            return f"{dt.day} {month_name} {dt.year}"
        else:
            # Default ISO: YYYY-MM-DD
            return dt.strftime("%Y-%m-%d")

    @classmethod
    def extract_timestamp_and_url_from_archive_url(
        cls, archive_url: str
    ) -> Optional[Tuple[str, str]]:
        """Extract the (timestamp, original_url) from an existing Wayback Machine URL."""
        if not archive_url:
            return None
        match = cls.WAYBACK_URL_REGEX.search(archive_url.strip())
        if match:
            return match.group(1), match.group(2)
        return None

    @classmethod
    def select_best_snapshot(
        cls,
        snapshots: List[ArchiveSnapshot],
        original_url: str,
        target_timestamp: Optional[str] = None,
    ) -> Optional[ArchiveSnapshot]:
        """Prioritize snapshots based on status 200, original URL match, and publication date proximity."""
        if not snapshots:
            return None

        candidates = [s for s in snapshots if s.status_code == 200]
        if not candidates:
            # If no 200 status, discard to avoid saving error captures
            return None

        # If a publication timestamp is known, find snapshot with minimal timestamp difference
        if target_timestamp and len(target_timestamp) >= 8:
            try:
                target_date = datetime.strptime(target_timestamp[:8], "%Y%m%d")

                def score_snapshot(snap: ArchiveSnapshot) -> float:
                    try:
                        snap_date = datetime.strptime(snap.timestamp[:8], "%Y%m%d")
                        diff = abs((snap_date - target_date).total_seconds())
                        # Penalize captures prior to publication
                        if snap_date < target_date:
                            diff += 86400 * 30  # +30 days penalty
                        return diff
                    except Exception:
                        return float("inf")

                candidates.sort(key=score_snapshot)
                return candidates[0]
            except Exception as e:
                logger.debug(f"Failed to sort by timestamp: {e}")

        # Otherwise pick the earliest snapshot with status 200 (closest to when content was fresh)
        candidates.sort(key=lambda s: s.timestamp)
        return candidates[0]
