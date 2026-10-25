"""Reporting and metrics module for Justapedia Archiver Bot."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from bot.logging_config import logger


@dataclass
class BotMetrics:
    """Statistical summary counters for a scanning/editing run."""

    articles_scanned: int = 0
    citations_examined: int = 0
    urls_checked: int = 0
    working_urls: int = 0
    potentially_dead_urls: int = 0
    inconclusive_urls: int = 0
    archives_found: int = 0
    archive_params_added: int = 0
    existing_archives_preserved: int = 0
    citations_skipped: int = 0
    api_failures: int = 0
    edit_failures: int = 0
    articles_updated: int = 0


@dataclass
class CitationReportItem:
    """Record of a processed citation for reporting."""

    article_title: str
    citation_title: Optional[str]
    original_url: Optional[str]
    url_health: str
    archive_url: Optional[str]
    archive_date: Optional[str]
    action_taken: str  # e.g., "added_archive", "preserved", "skipped", "repaired"
    reason: str


@dataclass
class ScanReport:
    """Full execution report containing overall metrics and itemized article records."""

    job_id: str
    target_type: str
    target: str
    mode: str  # "dry_run" or "live_edit"
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    finished_at: Optional[str] = None
    metrics: BotMetrics = field(default_factory=BotMetrics)
    citations: List[CitationReportItem] = field(default_factory=list)
    article_diffs: Dict[str, str] = field(default_factory=dict)

    def finish(self) -> None:
        """Mark completion timestamp."""
        self.finished_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "job_id": self.job_id,
            "target_type": self.target_type,
            "target": self.target,
            "mode": self.mode,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "metrics": asdict(self.metrics),
            "citations_count": len(self.citations),
            "citations": [asdict(c) for c in self.citations],
            "articles_with_diffs": list(self.article_diffs.keys()),
        }

    def export_json(self, file_path: str | Path) -> None:
        """Export report to JSON format."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Exported JSON report to {path}")

    def export_csv(self, file_path: str | Path) -> None:
        """Export citation-level report items to CSV format."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Article Title",
                    "Citation Title",
                    "Original URL",
                    "URL Health",
                    "Archive URL",
                    "Archive Date",
                    "Action Taken",
                    "Reason",
                ]
            )
            for c in self.citations:
                writer.writerow(
                    [
                        c.article_title,
                        c.citation_title or "",
                        c.original_url or "",
                        c.url_health,
                        c.archive_url or "",
                        c.archive_date or "",
                        c.action_taken,
                        c.reason,
                    ]
                )
        logger.info(f"Exported CSV report to {path}")

    def get_summary_text(self) -> str:
        """Generate human-readable summary block."""
        m = self.metrics
        lines = [
            "============================================================",
            f"  JUSTAPEDIA WAYBACK ARCHIVER REPORT ({self.mode.upper()})",
            "============================================================",
            f"  Job ID:                      {self.job_id}",
            f"  Target:                      {self.target} ({self.target_type})",
            f"  Mode:                        {self.mode}",
            f"  Started:                     {self.started_at}",
            f"  Finished:                    {self.finished_at or 'In Progress'}",
            "------------------------------------------------------------",
            f"  Articles Scanned:            {m.articles_scanned}",
            f"  Articles Updated:            {m.articles_updated}",
            f"  Citations Examined:          {m.citations_examined}",
            f"  URLs Checked:                {m.urls_checked}",
            f"    - Working URLs:            {m.working_urls}",
            f"    - Likely Dead URLs:        {m.potentially_dead_urls}",
            f"    - Inconclusive URLs:       {m.inconclusive_urls}",
            f"  Archives Found:              {m.archives_found}",
            f"  Archive Parameters Added:    {m.archive_params_added}",
            f"  Existing Archives Preserved: {m.existing_archives_preserved}",
            f"  Citations Skipped:           {m.citations_skipped}",
            f"  API Failures:                {m.api_failures}",
            f"  Edit Failures:               {m.edit_failures}",
            "============================================================",
        ]
        return "\n".join(lines)
