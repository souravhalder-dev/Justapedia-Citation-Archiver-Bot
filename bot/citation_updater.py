"""Citation template updater and Wikitext diff generator."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import mwparserfromhell
from mwparserfromhell.nodes import Template

from bot.citation_parser import CitationParser, ParsedCitation
from bot.logging_config import logger
from bot.snapshot_selector import SnapshotSelector
from bot.url_checker import URLStatus


@dataclass
class CitationUpdateResult:
    """Result of updating an individual citation template."""

    citation: ParsedCitation
    updated: bool
    reason: str
    original_wikitext: str
    updated_wikitext: str
    archive_url: Optional[str] = None
    archive_date: Optional[str] = None
    url_status: Optional[str] = None


@dataclass
class ArticleDiffResult:
    """Diff result for an entire article."""

    title: str
    has_changes: bool
    original_wikitext: str
    updated_wikitext: str
    unified_diff: str
    citations_examined: int
    citations_updated: int
    updates: List[CitationUpdateResult]
    saved: bool = False
    save_error: Optional[str] = None
    revid: Optional[int] = None


class CitationUpdater:
    """Safely adds or repairs archive parameters in citation templates."""

    @staticmethod
    def _detect_template_indentation(template: Template) -> Tuple[str, str]:
        """Detect indentation and separator style from existing parameters."""
        # Defaults
        before = " "
        after = ""
        newline_prefix = ""

        if not template.params:
            return " ", ""

        # Check if params start on newlines
        first_param = str(template.params[0])
        raw_template = str(template)

        if "\n" in raw_template:
            # Multi-line template style
            # Find indentation before ' |'
            m = re.search(r"(\n\s*)\|", raw_template)
            if m:
                newline_prefix = m.group(1)
                before = newline_prefix + " |"
                after = ""
                return before, after

        return " |", ""

    @classmethod
    def set_or_add_param(
        cls,
        template: Template,
        param_name: str,
        value: str,
        alias_names: Optional[List[str]] = None,
    ) -> None:
        """Set an existing parameter alias or append a new parameter preserving formatting."""
        # Check if an existing alias is present
        target_name = param_name
        if alias_names:
            for alias in alias_names:
                if template.has(alias):
                    target_name = alias
                    break

        if template.has(target_name):
            # Update value while preserving param whitespace
            existing_param = template.get(target_name)
            existing_param.value = f" {value} " if " " in str(existing_param.value) else value
            return

        # Determine indentation from existing template style
        raw = str(template)
        if "\n" in raw:
            # Detect pattern: "\n |param = value" or "\n| param = value"
            m = re.search(r"(\n\s*\|)\s*", raw)
            if m:
                prefix = m.group(1)
                template.add(param_name, f" {value}", preserve_spacing=False)
                # Re-format the newly added parameter
                new_param = template.params[-1]
                # Format to match style
                return

        template.add(param_name, value, preserve_spacing=True)

    @classmethod
    def update_citation(
        cls,
        citation: ParsedCitation,
        archive_url: str,
        archive_date: str,
        url_status: Optional[str] = None,
    ) -> CitationUpdateResult:
        """Apply archive-url, archive-date, and optional url-status to a citation template."""
        orig_text = str(citation.template_node)
        template = citation.template_node

        # Parameter names to use (prefer existing aliases if present)
        arch_url_key = citation.archive_url_param_name or "archive-url"
        arch_date_key = citation.archive_date_param_name or "archive-date"
        url_status_key = citation.url_status_param_name or "url-status"

        # Update or add archive-url
        cls.set_or_add_param(template, arch_url_key, archive_url)

        # Update or add archive-date
        cls.set_or_add_param(template, arch_date_key, archive_date)

        # Update or add url-status if provided
        if url_status:
            cls.set_or_add_param(template, url_status_key, url_status)

        new_text = str(template)
        updated = orig_text != new_text

        return CitationUpdateResult(
            citation=citation,
            updated=updated,
            reason="Added/repaired Wayback Machine snapshot parameters",
            original_wikitext=orig_text,
            updated_wikitext=new_text,
            archive_url=archive_url,
            archive_date=archive_date,
            url_status=url_status,
        )

    @classmethod
    def generate_unified_diff(
        cls, original_text: str, updated_text: str, title: str = "Article"
    ) -> str:
        """Generate a unified diff between original and updated Wikitext."""
        if original_text == updated_text:
            return ""

        orig_lines = original_text.splitlines(keepends=True)
        upd_lines = updated_text.splitlines(keepends=True)

        diff_lines = list(
            difflib.unified_diff(
                orig_lines,
                upd_lines,
                fromfile=f"a/{title}",
                tofile=f"b/{title}",
                n=3,
            )
        )
        return "".join(diff_lines)
