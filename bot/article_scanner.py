"""Article scanner and citation archiving orchestrator for Justapedia with batch parallelism and version tracking."""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple
import mwparserfromhell

from bot.archive_client import ArchiveClient, ArchiveSnapshot
from bot.citation_parser import CitationParser, ParsedCitation
from bot.citation_updater import ArticleDiffResult, CitationUpdater
from bot.config import config
from bot.database import Database
from bot.logging_config import logger
from bot.mediawiki_client import MediaWikiClient
from bot.reporting import BotMetrics, CitationReportItem, ScanReport
from bot.snapshot_selector import SnapshotSelector
from bot.url_checker import URLChecker, URLCheckResult, URLStatus


class ArticleScanner:
    """Coordinates page retrieval, citation inspection, health checking, archive retrieval, version saving, and updating."""

    def __init__(
        self,
        wiki_client: Optional[MediaWikiClient] = None,
        archive_client: Optional[ArchiveClient] = None,
        url_checker: Optional[URLChecker] = None,
        db: Optional[Database] = None,
        dry_run: bool = True,
        max_edits: Optional[int] = None,
        acting_user: Optional[str] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.db = db or Database(config.db_path)
        self.wiki_client = wiki_client or MediaWikiClient()
        self.archive_client = archive_client or ArchiveClient(db=self.db)
        self.url_checker = url_checker or URLChecker(db=self.db)
        self.dry_run = dry_run
        self.max_edits = max_edits
        self.acting_user = acting_user or self.wiki_client.username or "Anonymous"
        self.on_progress = on_progress

    def scan_article(
        self,
        title: str,
        report: ScanReport,
        preloaded_content: Optional[Tuple[Optional[str], Optional[str], Optional[int]]] = None,
    ) -> ArticleDiffResult:
        """Scan a single article and determine citation updates."""
        report.metrics.articles_scanned += 1

        if preloaded_content is not None:
            wikitext, basetimestamp, revid = preloaded_content
        else:
            wikitext, basetimestamp, revid = self.wiki_client.get_page(title)

        if not wikitext:
            logger.warning(f"Could not retrieve content for '{title}' (skipping)")
            report.metrics.citations_skipped += 1
            return ArticleDiffResult(
                title=title,
                has_changes=False,
                original_wikitext="",
                updated_wikitext="",
                unified_diff="",
                citations_examined=0,
                citations_updated=0,
                updates=[],
            )

        citations = CitationParser.parse_citations(wikitext)
        report.metrics.citations_examined += len(citations)

        updates = []
        citations_updated_count = 0

        # Fast parallel check for all external citation URLs in this article
        external_urls = [c.url for c in citations if c.url]
        try:
            url_health_map = self.url_checker.check_urls_parallel(external_urls) or {}
        except Exception:
            url_health_map = {}

        # Parse wikitext AST
        wikicode = mwparserfromhell.parse(wikitext)

        # Prepare list of snapshots to fetch in parallel
        snapshots_needed: List[Tuple[str, Optional[str]]] = []
        for cit in citations:
            if not cit.url:
                continue
            if not cit.archive_url:
                target_ts = SnapshotSelector.parse_citation_date_to_timestamp(
                    cit.date or cit.access_date
                )
                snapshots_needed.append((cit.url, target_ts))

        try:
            snapshot_map = self.archive_client.find_snapshots_parallel(snapshots_needed) or {}
        except Exception:
            snapshot_map = {}

        for cit in citations:
            orig_url = cit.url
            if not orig_url:
                continue

            target_ts = SnapshotSelector.parse_citation_date_to_timestamp(
                cit.date or cit.access_date
            )

            # Retrieve health (prefer pre-checked map or fall back to single check)
            url_res = url_health_map.get(orig_url)
            if not url_res or not isinstance(url_res, URLCheckResult):
                url_res = self.url_checker.check_url(orig_url)
            report.metrics.urls_checked += 1

            if url_res.status == URLStatus.WORKING:
                report.metrics.working_urls += 1
            elif url_res.status == URLStatus.LIKELY_DEAD:
                report.metrics.potentially_dead_urls += 1
            elif url_res.status == URLStatus.INCONCLUSIVE:
                report.metrics.inconclusive_urls += 1

            detected_style = SnapshotSelector.detect_date_style(
                cit.date or cit.access_date or cit.archive_date
            )

            # Match AST template node in the main article tree
            node_in_tree = None
            for t in wikicode.filter_templates():
                if str(t) == cit.raw_wikitext:
                    node_in_tree = t
                    break

            if not node_in_tree:
                continue

            # Case 5: Citation already has both archive-url and archive-date
            if cit.archive_url and cit.archive_date:
                if url_res.status == URLStatus.LIKELY_DEAD and cit.url_status != "dead":
                    CitationUpdater.set_or_add_param(
                        node_in_tree,
                        cit.url_status_param_name or "url-status",
                        "dead",
                    )
                    citations_updated_count += 1
                    report.citations.append(
                        CitationReportItem(
                            article_title=title,
                            citation_title=cit.title,
                            original_url=orig_url,
                            url_health=url_res.status.value,
                            archive_url=cit.archive_url,
                            archive_date=cit.archive_date,
                            action_taken="updated_url_status",
                            reason="Set url-status=dead for dead link with existing archive",
                        )
                    )
                else:
                    report.metrics.existing_archives_preserved += 1
                    report.citations.append(
                        CitationReportItem(
                            article_title=title,
                            citation_title=cit.title,
                            original_url=orig_url,
                            url_health=url_res.status.value,
                            archive_url=cit.archive_url,
                            archive_date=cit.archive_date,
                            action_taken="preserved",
                            reason="Valid archive already present",
                        )
                    )
                continue

            # Case 2: Only archive-url is present, archive-date missing
            if cit.archive_url and not cit.archive_date:
                extracted = SnapshotSelector.extract_timestamp_and_url_from_archive_url(
                    cit.archive_url
                )
                if extracted:
                    ts, _ = extracted
                    formatted_date = SnapshotSelector.format_timestamp_to_date(
                        ts, style=detected_style
                    )
                    if formatted_date:
                        CitationUpdater.set_or_add_param(
                            node_in_tree,
                            cit.archive_date_param_name or "archive-date",
                            formatted_date,
                        )
                        report.metrics.archive_params_added += 1
                        citations_updated_count += 1
                        report.citations.append(
                            CitationReportItem(
                                article_title=title,
                                citation_title=cit.title,
                                original_url=orig_url,
                                url_health=url_res.status.value,
                                archive_url=cit.archive_url,
                                archive_date=formatted_date,
                                action_taken="repaired_archive_date",
                                reason="Extracted archive-date from existing archive-url",
                            )
                        )
                        continue

            # Look up snapshot from pre-fetched map or fallback to find_best_snapshot
            snapshot = snapshot_map.get(orig_url)
            if not snapshot or not isinstance(snapshot, ArchiveSnapshot):
                snapshot = self.archive_client.find_best_snapshot(
                    orig_url, target_timestamp=target_ts
                )

            if not snapshot:
                report.metrics.citations_skipped += 1
                report.citations.append(
                    CitationReportItem(
                        article_title=title,
                        citation_title=cit.title,
                        original_url=orig_url,
                        url_health=url_res.status.value,
                        archive_url=None,
                        archive_date=None,
                        action_taken="skipped",
                        reason="No valid snapshot available on Wayback Machine",
                    )
                )
                continue

            archive_date_str = SnapshotSelector.format_timestamp_to_date(
                snapshot.timestamp, style=detected_style
            )
            if not archive_date_str:
                report.metrics.citations_skipped += 1
                continue

            status_val = "dead" if url_res.status == URLStatus.LIKELY_DEAD else "live"

            CitationUpdater.set_or_add_param(
                node_in_tree,
                cit.archive_url_param_name or "archive-url",
                snapshot.archive_url,
            )
            CitationUpdater.set_or_add_param(
                node_in_tree,
                cit.archive_date_param_name or "archive-date",
                archive_date_str,
            )
            CitationUpdater.set_or_add_param(
                node_in_tree,
                cit.url_status_param_name or "url-status",
                status_val,
            )

            report.metrics.archives_found += 1
            report.metrics.archive_params_added += 2
            citations_updated_count += 1

            report.citations.append(
                CitationReportItem(
                    article_title=title,
                    citation_title=cit.title,
                    original_url=orig_url,
                    url_health=url_res.status.value,
                    archive_url=snapshot.archive_url,
                    archive_date=archive_date_str,
                    action_taken="added_archive",
                    reason=f"Added Wayback snapshot (URL health: {url_res.status.value})",
                )
            )

        updated_wikitext = str(wikicode)
        has_changes = wikitext != updated_wikitext
        unified_diff = (
            CitationUpdater.generate_unified_diff(wikitext, updated_wikitext, title=title)
            if has_changes
            else ""
        )

        if has_changes:
            report.article_diffs[title] = unified_diff

        # If live editing is requested and changes exist
        new_revid = None
        saved = False
        save_error: Optional[str] = None

        if has_changes:
            if not self.dry_run:
                if self.max_edits is not None and report.metrics.articles_updated >= self.max_edits:
                    logger.info(
                        f"Max edits limit ({self.max_edits}) reached. Skipping save for '{title}'"
                    )
                    save_error = "Max edits limit reached"
                else:
                    success, msg = self.wiki_client.save_page(
                        title=title,
                        new_wikitext=updated_wikitext,
                        basetimestamp=basetimestamp,
                        acting_user=self.acting_user,
                    )
                    new_revid = getattr(self.wiki_client, "last_revid", None)
                    saved = success
                    if success:
                        report.metrics.articles_updated += 1
                    else:
                        report.metrics.edit_failures += 1
                        save_error = msg
                        logger.error(f"Failed to edit '{title}': {msg}")
            else:
                save_error = "Dry Run (Preview Mode)"

        # Save Article Update Version in SQLite History (Requirement 1)
        if has_changes and self.db:
            try:
                self.db.save_article_version(
                    article_title=title,
                    username=self.acting_user,
                    mode="live_edit" if (not self.dry_run and saved) else "dry_run",
                    previous_wikitext=wikitext,
                    updated_wikitext=updated_wikitext,
                    diff=unified_diff,
                    citations_updated=citations_updated_count,
                    mediawiki_revid=new_revid,
                    summary=f"Added {citations_updated_count} archive citation(s) by {self.acting_user}",
                )
            except Exception as e:
                logger.debug(f"Failed to save version record for '{title}': {e}")

        diff_res = ArticleDiffResult(
            title=title,
            has_changes=has_changes,
            original_wikitext=wikitext,
            updated_wikitext=updated_wikitext,
            unified_diff=unified_diff,
            citations_examined=len(citations),
            citations_updated=citations_updated_count,
            updates=updates,
            saved=saved,
            save_error=save_error,
            revid=new_revid,
        )

        if self.on_progress:
            self.on_progress(
                {
                    "title": title,
                    "has_changes": has_changes,
                    "citations_examined": len(citations),
                    "citations_updated": citations_updated_count,
                    "articles_scanned": report.metrics.articles_scanned,
                    "diff": unified_diff,
                }
            )

        return diff_res

    def run_batch(
        self,
        titles: List[str],
        target_type: str = "batch",
        target_name: str = "manual_batch",
        job_id: Optional[str] = None,
        resume: bool = False,
    ) -> ScanReport:
        """Run scan or update across a batch of article titles using high-speed parallel prefetching."""
        jid = job_id or str(uuid.uuid4())[:8]
        mode_str = "dry_run" if self.dry_run else "live_edit"

        already_processed = set()
        if resume:
            already_processed = set(self.db.get_processed_articles_for_job(jid))
            logger.info(f"Resuming job {jid}. Skipping {len(already_processed)} previously processed articles.")
        else:
            self.db.create_job(
                job_id=jid,
                target_type=target_type,
                target=target_name,
                mode=mode_str,
            )

        report = ScanReport(
            job_id=jid,
            target_type=target_type,
            target=target_name,
            mode=mode_str,
        )

        pending_titles = [t for t in titles if t not in already_processed]

        # Process in chunks of 20 with batch MediaWiki prefetching (> 20 articles/min throughput)
        batch_chunk_size = 20
        for i in range(0, len(pending_titles), batch_chunk_size):
            chunk = pending_titles[i : i + batch_chunk_size]
            # Batch fetch all article wikitext in 1 network call
            preloaded_batch = self.wiki_client.get_pages_batch(chunk)

            for title in chunk:
                preloaded = preloaded_batch.get(title)
                try:
                    res = self.scan_article(title, report, preloaded_content=preloaded)

                    self.db.record_job_article(
                        job_id=jid,
                        title=title,
                        status="updated" if res.has_changes else "unchanged",
                        citations_examined=res.citations_examined,
                        citations_updated=res.citations_updated,
                        diff=res.unified_diff,
                        summary=f"Examined {res.citations_examined}, updated {res.citations_updated} by {self.acting_user}",
                    )

                    self.db.update_job_status(
                        job_id=jid,
                        status="running",
                        articles_scanned=report.metrics.articles_scanned,
                        citations_examined=report.metrics.citations_examined,
                        urls_checked=report.metrics.urls_checked,
                        archives_added=report.metrics.archive_params_added,
                        edits_made=report.metrics.articles_updated,
                        errors_count=report.metrics.edit_failures + report.metrics.api_failures,
                    )

                    if (
                        not self.dry_run
                        and self.max_edits is not None
                        and report.metrics.articles_updated >= self.max_edits
                    ):
                        logger.info(f"Reached max edits ({self.max_edits}). Stopping batch run.")
                        break

                except Exception as e:
                    logger.error(f"Error processing article '{title}': {e}", exc_info=True)
                    report.metrics.api_failures += 1
                    self.db.record_job_article(
                        job_id=jid,
                        title=title,
                        status="error",
                        summary=str(e),
                    )

        report.finish()
        self.db.update_job_status(
            job_id=jid,
            status="completed",
            articles_scanned=report.metrics.articles_scanned,
            citations_examined=report.metrics.citations_examined,
            urls_checked=report.metrics.urls_checked,
            archives_added=report.metrics.archive_params_added,
            edits_made=report.metrics.articles_updated,
            errors_count=report.metrics.edit_failures + report.metrics.api_failures,
        )

        return report
