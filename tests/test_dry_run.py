"""Unit tests verifying dry-run safety and execution flow."""

from unittest.mock import MagicMock
from bot.archive_client import ArchiveSnapshot
from bot.article_scanner import ArticleScanner
from bot.reporting import ScanReport
from bot.url_checker import URLCheckResult, URLStatus


def test_dry_run_never_saves_edits(temp_db, sample_article_wikitext):
    mock_wiki = MagicMock()
    mock_wiki.get_page.return_value = (sample_article_wikitext, "2026-01-01T00:00:00Z", 100)

    mock_archive = MagicMock()
    mock_archive.find_best_snapshot.return_value = ArchiveSnapshot(
        original_url="https://example.com/paper",
        archive_url="https://web.archive.org/web/20200510120000/https://example.com/paper",
        timestamp="20200510120000",
        status_code=200,
    )

    mock_checker = MagicMock()
    mock_checker.check_url.return_value = URLCheckResult(
        url="https://example.com/paper",
        status=URLStatus.WORKING,
        http_code=200,
    )

    scanner = ArticleScanner(
        wiki_client=mock_wiki,
        archive_client=mock_archive,
        url_checker=mock_checker,
        db=temp_db,
        dry_run=True,  # DRY RUN
    )

    report = ScanReport(job_id="test", target_type="article", target="Jane Doe", mode="dry_run")
    result = scanner.scan_article("Jane Doe", report)

    # Changes were found and diff was generated
    assert result.has_changes
    assert len(result.unified_diff) > 0

    # But save_page was NEVER called
    mock_wiki.save_page.assert_not_called()


def test_live_editing_saves_when_apply_enabled(temp_db, sample_article_wikitext):
    mock_wiki = MagicMock()
    mock_wiki.get_page.return_value = (sample_article_wikitext, "2026-01-01T00:00:00Z", 100)
    mock_wiki.save_page.return_value = (True, "Saved rev 200")

    mock_archive = MagicMock()
    mock_archive.find_best_snapshot.return_value = ArchiveSnapshot(
        original_url="https://example.com/paper",
        archive_url="https://web.archive.org/web/20200510120000/https://example.com/paper",
        timestamp="20200510120000",
        status_code=200,
    )

    mock_checker = MagicMock()
    mock_checker.check_url.return_value = URLCheckResult(
        url="https://example.com/paper",
        status=URLStatus.WORKING,
        http_code=200,
    )

    scanner = ArticleScanner(
        wiki_client=mock_wiki,
        archive_client=mock_archive,
        url_checker=mock_checker,
        db=temp_db,
        dry_run=False,  # LIVE EDIT
        max_edits=5,
    )

    report = ScanReport(job_id="test_live", target_type="article", target="Jane Doe", mode="live_edit")
    result = scanner.scan_article("Jane Doe", report)

    assert result.has_changes
    # save_page WAS called
    mock_wiki.save_page.assert_called_once()
    assert report.metrics.articles_updated == 1
