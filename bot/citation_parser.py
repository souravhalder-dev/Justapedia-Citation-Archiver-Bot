"""Wikitext citation template parser using mwparserfromhell."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import mwparserfromhell
from mwparserfromhell.nodes import Template

from bot.logging_config import logger


# Supported citation template prefixes and names
SUPPORTED_CITATION_TEMPLATES = {
    "cite web",
    "cite news",
    "cite journal",
    "cite magazine",
    "cite book",
    "cite report",
    "cite press release",
    "cite paper",
    "cite conference",
    "cite interview",
    "cite thesis",
    "cite speech",
    "cite video",
    "cite podcast",
    "cite episode",
    "cite tweet",
    "cite audio",
    "citation",
    "web reference",
}

# Parameter alias mappings
URL_PARAM_ALIASES = ["url", "URL", "Url"]
ARCHIVE_URL_PARAM_ALIASES = ["archive-url", "archiveurl", "archive_url", "ArchiveUrl"]
ARCHIVE_DATE_PARAM_ALIASES = ["archive-date", "archivedate", "archive_date", "ArchiveDate"]
URL_STATUS_PARAM_ALIASES = ["url-status", "dead-url", "deadurl", "url_status"]
DATE_PARAM_ALIASES = ["date", "publication-date", "year", "Date"]
ACCESS_DATE_PARAM_ALIASES = ["access-date", "accessdate", "access_date", "AccessDate"]
TITLE_PARAM_ALIASES = ["title", "Title"]


@dataclass
class ParsedCitation:
    """Represents a citation parsed from article Wikitext."""

    template_node: Template
    template_name: str
    url: Optional[str] = None
    url_param_name: Optional[str] = None
    archive_url: Optional[str] = None
    archive_url_param_name: Optional[str] = None
    archive_date: Optional[str] = None
    archive_date_param_name: Optional[str] = None
    url_status: Optional[str] = None
    url_status_param_name: Optional[str] = None
    date: Optional[str] = None
    access_date: Optional[str] = None
    title: Optional[str] = None
    raw_wikitext: str = ""
    case: int = 5  # 1 to 5 (defined in spec)
    case_description: str = ""

    @property
    def has_archive(self) -> bool:
        """True if both archive-url and archive-date are present and non-empty."""
        return bool(self.archive_url and self.archive_date)


class CitationParser:
    """Parses Wikitext to extract and classify citation templates."""

    @classmethod
    def normalize_template_name(cls, name: str) -> str:
        """Normalize template name: lower case, stripped, spaces collapsed."""
        clean = str(name).strip().lower()
        if clean.startswith("template:"):
            clean = clean[len("template:") :].strip()
        clean = re.sub(r"\s+", " ", clean)
        return clean

    @classmethod
    def is_citation_template(cls, template: Template) -> bool:
        """Check if node is a recognized citation template."""
        norm_name = cls.normalize_template_name(str(template.name))
        if norm_name in SUPPORTED_CITATION_TEMPLATES:
            return True
        # Also match templates starting with 'cite '
        if norm_name.startswith("cite "):
            return True
        return False

    @classmethod
    def get_param_value(cls, template: Template, aliases: List[str]) -> Tuple[Optional[str], Optional[str]]:
        """Get the stripped value and actual parameter name for the first matching alias."""
        for alias in aliases:
            if template.has(alias):
                try:
                    val = str(template.get(alias).value).strip()
                    return (val if val else None), alias
                except Exception:
                    continue
        return None, None

    @classmethod
    def parse_citations(cls, wikitext: str) -> List[ParsedCitation]:
        """Extract and classify all citations with external URLs in the wikitext."""
        if not wikitext or not isinstance(wikitext, str):
            return []

        try:
            parsed_code = mwparserfromhell.parse(wikitext)
        except Exception as e:
            logger.error(f"Failed to parse wikitext with mwparserfromhell: {e}")
            return []

        citations: List[ParsedCitation] = []

        for template in parsed_code.filter_templates():
            if not cls.is_citation_template(template):
                continue

            norm_name = cls.normalize_template_name(str(template.name))

            url, url_param = cls.get_param_value(template, URL_PARAM_ALIASES)
            archive_url, arch_url_param = cls.get_param_value(
                template, ARCHIVE_URL_PARAM_ALIASES
            )
            archive_date, arch_date_param = cls.get_param_value(
                template, ARCHIVE_DATE_PARAM_ALIASES
            )
            url_status, url_status_param = cls.get_param_value(
                template, URL_STATUS_PARAM_ALIASES
            )
            pub_date, _ = cls.get_param_value(template, DATE_PARAM_ALIASES)
            access_date, _ = cls.get_param_value(template, ACCESS_DATE_PARAM_ALIASES)
            title, _ = cls.get_param_value(template, TITLE_PARAM_ALIASES)

            # Ignore citations that do not have an external URL
            if not url and not archive_url:
                continue

            # Skip internal wiki links mistakenly placed in url (e.g. [[Some Article]])
            if url and (url.startswith("[[") or not re.match(r"^https?://", url, re.IGNORECASE)):
                continue

            # Classify into cases 1 to 5
            case, desc = cls._classify_case(url, archive_url, archive_date)

            citation = ParsedCitation(
                template_node=template,
                template_name=norm_name,
                url=url,
                url_param_name=url_param,
                archive_url=archive_url,
                archive_url_param_name=arch_url_param,
                archive_date=archive_date,
                archive_date_param_name=arch_date_param,
                url_status=url_status,
                url_status_param_name=url_status_param,
                date=pub_date,
                access_date=access_date,
                title=title,
                raw_wikitext=str(template),
                case=case,
                case_description=desc,
            )
            citations.append(citation)

        return citations

    @classmethod
    def _classify_case(
        cls,
        url: Optional[str],
        archive_url: Optional[str],
        archive_date: Optional[str],
    ) -> Tuple[int, str]:
        """Classify citation into one of the 5 project cases."""
        has_arch_url = bool(archive_url and archive_url.strip())
        has_arch_date = bool(archive_date and archive_date.strip())

        # Case 1: Citations with neither archive-url nor archive-date
        if not has_arch_url and not has_arch_date:
            return 1, "Citations with neither archive-url nor archive-date"

        # Case 2: Citations with missing archive information (one present, other missing)
        if (has_arch_url and not has_arch_date) or (not has_arch_url and has_arch_date):
            return 2, "Citations with missing partial archive information"

        # Case 4: Archive URL present but obviously invalid/malformed
        if has_arch_url and not re.match(r"^https?://", archive_url.strip(), re.IGNORECASE):
            return 4, "Citations with invalid archive URL"

        # Default Case 5: Valid archive info already present (Health check will test if url is dead for Case 3)
        return 5, "Citations with existing valid archive information"
