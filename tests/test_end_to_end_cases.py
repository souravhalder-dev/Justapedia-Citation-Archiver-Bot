"""End-to-end scenario tests covering citation cases and url statuses."""

from unittest.mock import MagicMock
from bot.archive_client import ArchiveSnapshot
from bot.article_scanner import ArticleScanner
from bot.reporting import ScanReport
from bot.url_checker import URLCheckResult, URLStatus


def test_dead_url_with_snapshot_sets_url_status_dead(temp_db):
    wikitext = "{{cite web |title=Dead Link Article |url=https://deadsite.org/story |date=2019-04-12}}"

    mock_wiki = MagicMock()
    mock_wiki.get_page.return_value = (wikitext, "2026-01-01T00:00:00Z", 1)

    mock_archive = MagicMock()
    mock_archive.find_best_snapshot.return_value = ArchiveSnapshot(
        original_url="https://deadsite.org/story",
        archive_url="https://web.archive.org/web/20190415120000/https://deadsite.org/story",
        timestamp="20190415120000",
        status_code=200,
    )

    mock_checker = MagicMock()
    mock_checker.check_url.return_value = URLCheckResult(
        url="https://deadsite.org/story",
        status=URLStatus.LIKELY_DEAD,
        http_code=404,
    )

    scanner = ArticleScanner(
        wiki_client=mock_wiki,
        archive_client=mock_archive,
        url_checker=mock_checker,
        db=temp_db,
        dry_run=True,
    )

    report = ScanReport(job_id="test_dead", target_type="article", target="Dead Page", mode="dry_run")
    result = scanner.scan_article("Dead Page", report)

    assert result.has_changes
    assert "archive-url=https://web.archive.org/web/20190415120000/https://deadsite.org/story" in result.updated_wikitext
    assert "archive-date=2019-04-15" in result.updated_wikitext
    assert "url-status=dead" in result.updated_wikitext
    assert report.metrics.potentially_dead_urls == 1
    assert report.metrics.archives_found == 1


def test_working_url_without_archive_sets_url_status_live(temp_db):
    wikitext = "{{cite web |title=Live Site |url=https://live.org/news |date=2021-08-01}}"

    mock_wiki = MagicMock()
    mock_wiki.get_page.return_value = (wikitext, "2026-01-01T00:00:00Z", 1)

    mock_archive = MagicMock()
    mock_archive.find_best_snapshot.return_value = ArchiveSnapshot(
        original_url="https://live.org/news",
        archive_url="https://web.archive.org/web/20210805120000/https://live.org/news",
        timestamp="20210805120000",
        status_code=200,
    )

    mock_checker = MagicMock()
    mock_checker.check_url.return_value = URLCheckResult(
        url="https://live.org/news",
        status=URLStatus.WORKING,
        http_code=200,
    )

    scanner = ArticleScanner(
        wiki_client=mock_wiki,
        archive_client=mock_archive,
        url_checker=mock_checker,
        db=temp_db,
        dry_run=True,
    )

    report = ScanReport(job_id="test_live", target_type="article", target="Live Page", mode="dry_run")
    result = scanner.scan_article("Live Page", report)

    assert result.has_changes
    assert "archive-url=https://web.archive.org/web/20210805120000/https://live.org/news" in result.updated_wikitext
    assert "archive-date=2021-08-05" in result.updated_wikitext
    assert "url-status=live" in result.updated_wikitext


def test_url_without_snapshot_is_skipped_and_unchanged(temp_db):
    wikitext = "{{cite web |title=Obscure Site |url=https://unarchived-obscure-site.xyz |date=2022-01-01}}"

    mock_wiki = MagicMock()
    mock_wiki.get_page.return_value = (wikitext, "2026-01-01T00:00:00Z", 1)

    mock_archive = MagicMock()
    mock_archive.find_best_snapshot.return_value = None  # No snapshot available!

    mock_checker = MagicMock()
    mock_checker.check_url.return_value = URLCheckResult(
        url="https://unarchived-obscure-site.xyz",
        status=URLStatus.WORKING,
        http_code=200,
    )

    scanner = ArticleScanner(
        wiki_client=mock_wiki,
        archive_client=mock_archive,
        url_checker=mock_checker,
        db=temp_db,
        dry_run=True,
    )

    report = ScanReport(job_id="test_none", target_type="article", target="No Archive Page", mode="dry_run")
    result = scanner.scan_article("No Archive Page", report)

    assert not result.has_changes
    assert result.updated_wikitext == wikitext
    assert report.metrics.citations_skipped == 1
    assert report.metrics.archive_params_added == 0
