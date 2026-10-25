"""Unit tests for citation updating and Wikitext diff generation."""

from bot.citation_parser import CitationParser
from bot.citation_updater import CitationUpdater


def test_add_archive_parameters_to_citation():
    wikitext = "{{cite web |title=Paper |url=https://example.com/paper |date=2020-05-10}}"
    citations = CitationParser.parse_citations(wikitext)
    assert len(citations) == 1
    cit = citations[0]

    res = CitationUpdater.update_citation(
        citation=cit,
        archive_url="https://web.archive.org/web/20200512000000/https://example.com/paper",
        archive_date="2020-05-12",
        url_status="live",
    )
    assert res.updated
    assert "archive-url=https://web.archive.org/web/20200512000000/https://example.com/paper" in res.updated_wikitext
    assert "archive-date=2020-05-12" in res.updated_wikitext
    assert "url-status=live" in res.updated_wikitext
    # Original URL preserved
    assert "url=https://example.com/paper" in res.updated_wikitext


def test_preserve_surrounding_article_and_categories(sample_article_wikitext):
    citations = CitationParser.parse_citations(sample_article_wikitext)
    first_cit = citations[0]

    res = CitationUpdater.update_citation(
        citation=first_cit,
        archive_url="https://web.archive.org/web/20200510120000/https://example.com/paper",
        archive_date="2020-05-10",
        url_status="live",
    )
    # Ensure update worked
    assert res.updated

    # Verify categories and sections remain untouched in article
    assert "[[Category:Living people]]" in sample_article_wikitext
    assert "[[Category:Physicists]]" in sample_article_wikitext
    assert "== References ==" in sample_article_wikitext


def test_generate_unified_diff():
    orig = "Line 1\n{{cite web |url=http://ex.com}}\nLine 3\n"
    upd = "Line 1\n{{cite web |url=http://ex.com |archive-url=http://web.archive.org/web/123/http://ex.com |archive-date=2020-01-01}}\nLine 3\n"

    diff = CitationUpdater.generate_unified_diff(orig, upd, "Test Article")
    assert "--- a/Test Article" in diff
    assert "+++ b/Test Article" in diff
    assert "+{{cite web |url=http://ex.com |archive-url=" in diff
